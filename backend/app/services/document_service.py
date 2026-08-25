"""
知识库文档服务 — 核心业务
上传校验 / MinIO 持久化 / 列表筛选 / 软删除 / 向量化触发 / 分块记录
"""

import asyncio
import hashlib
import re

from fastapi import UploadFile
from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.chroma_client import delete_by_document_id
from app.models.category import KbCategory
from app.models.document import KbDocument
from app.models.document_chunk import KbDocumentChunk
from app.models.user import SysUser
from app.schemas.document import (
    BatchVectorizeRequest,
    DocumentChunkInfo,
    DocumentInfo,
    DocumentQuery,
    VectorizeResult,
)
from app.services.category_service import CategoryService
from app.services.config_service import ConfigService
from app.services.minio_service import MinioService
from app.utils.exceptions import (
    BadRequestException,
    ConflictException,
    FileTooLargeException,
    NotFoundException,
    UnsupportedFileTypeException,
)

# 允许的文档标题长度等常量
_MAX_UPLOAD_FILE_COUNT = 20


class DocumentService:
    """知识库文档业务服务"""

    # ==========================================
    # 上传
    # ==========================================

    @staticmethod
    async def upload_files(
        db: AsyncSession,
        *,
        files: list[UploadFile],
        category_id: int,
        user: SysUser,
        title: str | None = None,
        description: str | None = None,
        tags: str | None = None,
    ) -> list[KbDocument]:
        """
        多文件批量上传, 三阶段:
        A. 整体校验 (分类存在 / 数量 / 后缀白名单 / 大小上限 / SHA256 去重)
           — 任一文件不合法则整体拒绝, 不产生脏数据
        B. 全部文件 MinIO 持久化
        C. MySQL 统一写入元数据 (vector_status=pending)
        """
        await CategoryService.get_by_id(db, category_id)

        if not files:
            raise BadRequestException("未选择上传文件")
        if len(files) > _MAX_UPLOAD_FILE_COUNT:
            raise BadRequestException(f"单次最多上传 {_MAX_UPLOAD_FILE_COUNT} 个文件")

        allowed_exts = settings.allowed_extensions_list
        # 上传大小上限实时读 sys_config (Phase 7, 表无值回退 .env)
        upload_max_size_mb = await ConfigService.get_upload_max_size_mb(db)
        upload_max_size_bytes = upload_max_size_mb * 1024 * 1024

        # ---- A. 整体校验 ----
        validated: list[dict] = []
        seen_hashes: set = set()
        for file in files:
            file_name = file.filename or ""
            match = re.search(r"\.([a-zA-Z0-9]+)$", file_name)
            ext = match.group(1).lower() if match else ""

            if ext not in allowed_exts:
                raise UnsupportedFileTypeException(
                    f"文件 '{file_name}' 类型不支持，允许: {', '.join(allowed_exts)}"
                )

            content = await file.read()
            if not content:
                raise BadRequestException(f"文件 '{file_name}' 内容为空")
            if len(content) > upload_max_size_bytes:
                raise FileTooLargeException(
                    f"文件 '{file_name}' 超过 {upload_max_size_mb}MB 限制"
                )

            # SHA256 去重: 先查库 (仅未删除文档, limit 1 防脏数据), 再查本批次
            file_hash = hashlib.sha256(content).hexdigest()
            dup = (
                await db.execute(
                    select(KbDocument)
                    .where(
                        KbDocument.file_hash == file_hash,
                        KbDocument.status != -1,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if dup is not None:
                raise ConflictException(
                    f"文件 '{file_name}' 已存在 (文档ID: {dup.id}, 标题: {dup.title})"
                )
            if file_hash in seen_hashes:
                raise ConflictException(
                    f"文件 '{file_name}' 与本次上传的其他文件内容重复"
                )
            seen_hashes.add(file_hash)

            # title 仅对单文件上传生效; 多文件时使用文件名去后缀
            doc_title = (
                title
                if (len(files) == 1 and title)
                else re.sub(rf"\.{ext}$", "", file_name)
            )
            validated.append(
                {
                    "file_name": file_name,
                    "ext": ext,
                    "content": content,
                    "file_hash": file_hash,
                    "object_path": MinioService.build_object_path(ext),
                    "title": doc_title,
                }
            )

        # ---- B. MinIO 持久化 ----
        # 部分失败时回滚已上传对象 (尽力而为), 避免产生孤儿文件
        uploaded_paths: list[str] = []
        try:
            for item in validated:
                await asyncio.to_thread(
                    MinioService.upload,
                    item["object_path"],
                    item["content"],
                    MinioService.get_content_type(item["ext"])
                    or "application/octet-stream",
                )
                uploaded_paths.append(item["object_path"])
        except Exception:
            for path in uploaded_paths:
                await asyncio.to_thread(MinioService.delete, path)
            raise

        # ---- C. MySQL 元数据 ----
        docs: list[KbDocument] = []
        for item in validated:
            doc = KbDocument(
                title=item["title"],
                category_id=category_id,
                file_name=item["file_name"],
                file_type=item["ext"],
                file_size=len(item["content"]),
                file_path=item["object_path"],
                file_hash=item["file_hash"],
                vector_status="pending",
                chunk_count=0,
                description=description,
                tags=tags,
                status=1,
                uploaded_by=user.id,
            )
            db.add(doc)
            docs.append(doc)

        await db.commit()
        for doc in docs:
            await db.refresh(doc)
            logger.info(
                f"[文档] 上传成功: {doc.file_name} (id={doc.id}, "
                f"category_id={category_id}, size={doc.file_size})"
            )

        return docs

    # ==========================================
    # 列表 / 详情
    # ==========================================

    @staticmethod
    async def get_list(
        db: AsyncSession,
        query: DocumentQuery,
    ) -> tuple[list[DocumentInfo], int]:
        """文档分页列表 (默认排除已删除)"""
        conditions = [KbDocument.status != -1]

        if query.keyword:
            like = f"%{query.keyword}%"
            conditions.append(
                or_(
                    KbDocument.title.like(like),
                    KbDocument.file_name.like(like),
                    KbDocument.tags.like(like),
                )
            )

        if query.category_id is not None:
            # 分类过滤包含子分类文档
            subtree_ids = await CategoryService.get_subtree_ids(db, query.category_id)
            conditions.append(KbDocument.category_id.in_(subtree_ids))

        if query.vector_status is not None:
            conditions.append(KbDocument.vector_status == query.vector_status.value)
        if query.file_type:
            conditions.append(KbDocument.file_type == query.file_type.lower())
        if query.status is not None:
            conditions.append(KbDocument.status == query.status)

        # 总数
        total = (
            await db.execute(select(func.count(KbDocument.id)).where(*conditions))
        ).scalar() or 0

        # 分页数据
        result = await db.execute(
            select(KbDocument)
            .where(*conditions)
            .order_by(KbDocument.created_at.desc(), KbDocument.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        docs = list(result.scalars().all())

        infos = await DocumentService._to_infos(db, docs)
        return infos, total

    @staticmethod
    async def get_detail(
        db: AsyncSession,
        document_id: int,
        increment_view: bool = False,
    ) -> DocumentInfo:
        """文档详情 (详情接口调用时 +1 浏览次数)"""
        doc = await DocumentService._get_visible_doc(db, document_id)

        if increment_view:
            doc.view_count += 1
            await db.commit()
            await db.refresh(doc)

        infos = await DocumentService._to_infos(db, [doc])
        return infos[0]

    # ==========================================
    # 下载
    # ==========================================

    @staticmethod
    async def get_download_url(
        db: AsyncSession,
        document_id: int,
    ) -> tuple[KbDocument, str]:
        """生成预签名下载 URL (+1 下载次数)"""
        doc = await DocumentService._get_visible_doc(db, document_id)

        url = await asyncio.to_thread(MinioService.get_presigned_url, doc.file_path)

        doc.download_count += 1
        await db.commit()
        await db.refresh(doc)
        logger.info(f"[文档] 下载: id={document_id}, count={doc.download_count}")
        return doc, url

    # ==========================================
    # 软删除
    # ==========================================

    @staticmethod
    async def soft_delete(db: AsyncSession, document_id: int) -> KbDocument:
        """
        软删除: status=-1 (禁止物理删除)。
        同步清理 Chroma 中该文档的分块向量 (RAG 不再命中已删文档),
        分块记录保留在 MySQL 用于审计。
        """
        doc = await DocumentService._get_visible_doc(db, document_id)

        doc.status = -1
        await db.commit()
        await db.refresh(doc)

        # 清理向量 (尽力而为, 失败仅告警)
        await asyncio.to_thread(delete_by_document_id, document_id)

        # 清理图谱 (Phase 6): 删除 Document 节点及 MENTIONS/BELONGS_TO/SIMILAR_TO 边
        # (尽力而为, 失败仅告警, 与 Chroma 清理同风格)
        try:
            from app.services.graph_service import GraphService

            await GraphService.cleanup_document_graph(document_id)
        except Exception as e:
            logger.warning(f"[图谱] 文档 {document_id} 图谱清理失败: {e}")

        logger.info(f"[文档] 软删除: id={document_id}, title={doc.title}")
        return doc

    # ==========================================
    # 向量化触发 (同步仅下发, 实际任务由 API 层调度后台执行)
    # ==========================================

    @staticmethod
    async def trigger_vectorize(
        db: AsyncSession,
        document_id: int,
    ) -> KbDocument:
        """单文档向量化触发: 置 pending, 清空上次错误信息"""
        doc = await DocumentService._get_visible_doc(db, document_id)

        if doc.vector_status == "processing":
            raise ConflictException("文档正在向量化处理中，请稍后")
        if doc.vector_status == "pending":
            raise ConflictException("向量化任务已在队列中，请稍后")

        doc.vector_status = "pending"
        doc.error_message = None
        await db.commit()
        await db.refresh(doc)
        logger.info(f"[文档] 触发向量化: id={document_id}")
        return doc

    @staticmethod
    async def batch_trigger_vectorize(
        db: AsyncSession,
        req: BatchVectorizeRequest,
    ) -> list[VectorizeResult]:
        """
        批量向量化触发 (Phase 8 优化):
        一次 IN 查询取回全部文档, 内存判断状态, 单次提交 —
        替换原逐文档查询 + 逐文档提交 (N 次往返)。
        冲突 (处理中/已排队) 与不存在的文档跳过并记录原因, 语义与原实现一致。
        """
        ids = list(dict.fromkeys(req.document_ids))

        result = await db.execute(select(KbDocument).where(KbDocument.id.in_(ids)))
        doc_map = {doc.id: doc for doc in result.scalars().all()}

        results: list[VectorizeResult] = []
        for document_id in ids:
            doc = doc_map.get(document_id)
            if doc is None or doc.status == -1:
                results.append(
                    VectorizeResult(
                        document_id=document_id,
                        triggered=False,
                        message="文档不存在或已删除",
                    )
                )
                continue
            if doc.vector_status == "processing":
                results.append(
                    VectorizeResult(
                        document_id=document_id,
                        triggered=False,
                        message="文档正在向量化处理中，请稍后",
                    )
                )
                continue
            if doc.vector_status == "pending":
                results.append(
                    VectorizeResult(
                        document_id=document_id,
                        triggered=False,
                        message="向量化任务已在队列中，请稍后",
                    )
                )
                continue

            doc.vector_status = "pending"
            doc.error_message = None
            results.append(VectorizeResult(document_id=document_id, triggered=True))
            logger.info(f"[文档] 触发向量化: id={document_id}")

        await db.commit()
        return results

    # ==========================================
    # 分块记录
    # ==========================================

    @staticmethod
    async def get_chunks(
        db: AsyncSession,
        document_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DocumentChunkInfo], int]:
        """文档分块列表 (按 chunk_index 排序分页)"""
        await DocumentService._get_visible_doc(db, document_id)

        total = (
            await db.execute(
                select(func.count(KbDocumentChunk.id)).where(
                    KbDocumentChunk.document_id == document_id
                )
            )
        ).scalar() or 0

        result = await db.execute(
            select(KbDocumentChunk)
            .where(KbDocumentChunk.document_id == document_id)
            .order_by(KbDocumentChunk.chunk_index.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        chunks = list(result.scalars().all())
        return [DocumentChunkInfo.model_validate(c) for c in chunks], total

    # ==========================================
    # 内部辅助
    # ==========================================

    @staticmethod
    async def _get_visible_doc(db: AsyncSession, document_id: int) -> KbDocument:
        """查询未删除文档, 不存在/已删除 → 404"""
        result = await db.execute(
            select(KbDocument).where(KbDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None or doc.status == -1:
            raise NotFoundException("文档不存在或已删除")
        return doc

    @staticmethod
    async def _to_infos(
        db: AsyncSession,
        docs: list[KbDocument],
    ) -> list[DocumentInfo]:
        """ORM → DocumentInfo, 补充 category_name / uploader_name 冗余字段"""
        if not docs:
            return []

        category_ids = {d.category_id for d in docs}
        user_ids = {d.uploaded_by for d in docs if d.uploaded_by is not None}

        category_map: dict[int, str] = {}
        if category_ids:
            cats = (
                await db.execute(
                    select(KbCategory.id, KbCategory.name).where(
                        KbCategory.id.in_(category_ids)
                    )
                )
            ).all()
            category_map = {cid: name for cid, name in cats}

        user_map: dict[int, str] = {}
        if user_ids:
            users = (
                await db.execute(
                    select(SysUser.id, SysUser.username).where(SysUser.id.in_(user_ids))
                )
            ).all()
            user_map = {uid: uname for uid, uname in users}

        infos: list[DocumentInfo] = []
        for doc in docs:
            info = DocumentInfo.model_validate(doc)
            info.category_name = category_map.get(doc.category_id)
            info.uploader_name = (
                user_map.get(doc.uploaded_by) if doc.uploaded_by is not None else None
            )
            infos.append(info)

        return infos
