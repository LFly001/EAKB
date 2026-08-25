"""
Phase 8 文档上传与向量化流程测试
覆盖: 上传三阶段校验 (后缀/大小/SHA256 去重) / 批量向量化触发 (一次查询单次提交)
模式: 服务层逻辑测试 + 假会话 (免真实 MySQL/MinIO); 完整流水线在 VM 按
      docs/phase8-test-guide.md 手工自测 (真实 Chroma/MinIO/LLM)
"""

import io
from typing import Any

import pytest
from starlette.datastructures import UploadFile

from app.models.document import KbDocument
from app.schemas.document import BatchVectorizeRequest
from app.services.category_service import CategoryService
from app.services.config_service import ConfigService
from app.services.document_service import DocumentService
from app.services.minio_service import MinioService
from app.utils.exceptions import (
    ConflictException,
    FileTooLargeException,
    UnsupportedFileTypeException,
)
from tests.conftest import FakeDB, StubListResult, StubScalarResult, make_fake_user


def _upload_file(name: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name)


def _doc(
    doc_id: int,
    vector_status: str = "completed",
    status: int = 1,
    title: str = "测试文档",
) -> KbDocument:
    return KbDocument(
        id=doc_id,
        title=title,
        category_id=1,
        file_name=f"{title}.txt",
        file_type="txt",
        file_size=100,
        file_path=f"documents/2026/08/{doc_id}.txt",
        file_hash=f"hash-{doc_id}",
        vector_status=vector_status,
        chunk_count=0,
        status=status,
        uploaded_by=1,
    )


# ==========================================
# 上传三阶段校验
# ==========================================


class TestUploadValidation:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_upload_success_flow(self, monkeypatch: Any) -> None:
        """两文件上传成功: MinIO 各上传一次, 元数据 pending 落库"""
        uploaded: list[str] = []

        def _fake_upload(path: str, data: bytes, content_type: str) -> str:
            uploaded.append(path)
            return path

        async def _fake_category(db: Any, category_id: int) -> Any:
            return None

        async def _fake_max_size(db: Any) -> int:
            return 50

        monkeypatch.setattr(MinioService, "upload", _fake_upload)
        monkeypatch.setattr(CategoryService, "get_by_id", _fake_category)
        monkeypatch.setattr(ConfigService, "get_upload_max_size_mb", _fake_max_size)

        db = FakeDB([StubScalarResult(None), StubScalarResult(None)])
        files = [
            _upload_file("手册.pdf", b"%PDF-1.4 fake pdf content"),
            _upload_file("说明.txt", b"plain text content"),
        ]
        docs = await DocumentService.upload_files(
            db, files=files, category_id=1, user=make_fake_user(role="admin")
        )

        assert len(docs) == 2
        assert len(uploaded) == 2
        assert all(d.vector_status == "pending" for d in docs)
        assert all(d.status == 1 for d in docs)
        assert db.committed == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_upload_unsupported_extension(self, monkeypatch: Any) -> None:
        """可执行文件 → 41500"""

        async def _fake_category(db: Any, category_id: int) -> Any:
            return None

        monkeypatch.setattr(CategoryService, "get_by_id", _fake_category)

        db = FakeDB()
        with pytest.raises(UnsupportedFileTypeException) as exc_info:
            await DocumentService.upload_files(
                db,
                files=[_upload_file("evil.exe", b"MZ...")],
                category_id=1,
                user=make_fake_user(),
            )
        assert exc_info.value.code == 41500

    @pytest.mark.asyncio(loop_scope="function")
    async def test_upload_file_too_large(self, monkeypatch: Any) -> None:
        """超过 sys_config 上限 → 41300"""

        async def _fake_max_size(db: Any) -> int:
            return 1  # 1MB

        async def _fake_category(db: Any, category_id: int) -> Any:
            return None

        monkeypatch.setattr(ConfigService, "get_upload_max_size_mb", _fake_max_size)
        monkeypatch.setattr(CategoryService, "get_by_id", _fake_category)

        db = FakeDB()
        big = b"x" * (2 * 1024 * 1024)  # 2MB
        with pytest.raises(FileTooLargeException) as exc_info:
            await DocumentService.upload_files(
                db,
                files=[_upload_file("big.txt", big)],
                category_id=1,
                user=make_fake_user(),
            )
        assert exc_info.value.code == 41300

    @pytest.mark.asyncio(loop_scope="function")
    async def test_upload_duplicate_in_batch(self, monkeypatch: Any) -> None:
        """批次内两个相同内容文件 → 40900 整体拒绝"""

        async def _fake_category(db: Any, category_id: int) -> Any:
            return None

        monkeypatch.setattr(CategoryService, "get_by_id", _fake_category)

        db = FakeDB([StubScalarResult(None)])
        same = b"identical content"
        with pytest.raises(ConflictException) as exc_info:
            await DocumentService.upload_files(
                db,
                files=[_upload_file("a.txt", same), _upload_file("b.txt", same)],
                category_id=1,
                user=make_fake_user(),
            )
        assert exc_info.value.code == 40900

    @pytest.mark.asyncio(loop_scope="function")
    async def test_upload_duplicate_in_db(self, monkeypatch: Any) -> None:
        """与库中已有文档 SHA256 相同 → 40900"""

        async def _fake_category(db: Any, category_id: int) -> Any:
            return None

        # 大小上限读取也会查询同一假会话, 不打桩会消耗掉去重查询的桩结果
        async def _fake_max_size(db: Any) -> int:
            return 50

        monkeypatch.setattr(CategoryService, "get_by_id", _fake_category)
        monkeypatch.setattr(ConfigService, "get_upload_max_size_mb", _fake_max_size)

        db = FakeDB([StubScalarResult(_doc(7))])  # 去重查询命中已有文档
        with pytest.raises(ConflictException) as exc_info:
            await DocumentService.upload_files(
                db,
                files=[_upload_file("dup.txt", b"dup")],
                category_id=1,
                user=make_fake_user(),
            )
        assert exc_info.value.code == 40900


# ==========================================
# 批量向量化触发 (Phase 8 优化: 一次查询 + 单次提交)
# ==========================================


class TestBatchTriggerVectorize:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_batch_mixed_statuses(self) -> None:
        """completed 触发 / processing 与 pending 跳过 / 不存在跳过, 单次提交"""
        docs = [
            _doc(1, vector_status="completed"),
            _doc(2, vector_status="processing"),
            _doc(3, vector_status="pending"),
            _doc(4, vector_status="failed"),
        ]
        db = FakeDB([StubListResult(docs)])
        req = BatchVectorizeRequest(document_ids=[1, 2, 3, 4, 99])

        results = await DocumentService.batch_trigger_vectorize(db, req)

        by_id = {r.document_id: r for r in results}
        assert by_id[1].triggered is True
        assert by_id[2].triggered is False and "处理中" in by_id[2].message
        assert by_id[3].triggered is False and "队列中" in by_id[3].message
        assert by_id[4].triggered is True  # failed 可重试
        assert by_id[99].triggered is False and "不存在" in by_id[99].message
        # 仅一次提交 (原实现逐文档 commit)
        assert db.committed == 1
        # 已触发文档状态置 pending 且清空错误信息
        assert docs[0].vector_status == "pending"
        assert docs[0].error_message is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_batch_skips_soft_deleted(self) -> None:
        """已软删文档跳过并记录原因"""
        db = FakeDB([StubListResult([_doc(1, status=-1)])])
        req = BatchVectorizeRequest(document_ids=[1])

        results = await DocumentService.batch_trigger_vectorize(db, req)
        assert results[0].triggered is False
        assert "不存在或已删除" in results[0].message

    @pytest.mark.asyncio(loop_scope="function")
    async def test_batch_dedupes_ids(self) -> None:
        """重复 ID 去重, 只处理一次"""
        docs = [_doc(1, vector_status="completed")]
        db = FakeDB([StubListResult(docs)])
        req = BatchVectorizeRequest(document_ids=[1, 1, 1])

        results = await DocumentService.batch_trigger_vectorize(db, req)
        assert len(results) == 1
        assert results[0].triggered is True
