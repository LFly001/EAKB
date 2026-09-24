"""
ESD 集成 — 内部检索接口测试 (POST /api/v1/rag/search)

覆盖: X-Internal-Key 鉴权 (缺头/错密钥/未配置 → 40100) / 正确密钥结构断言 /
      category_ids 非法 → 40000 / RagService.search 无 LLM 无落库
模式: 依赖覆盖 get_db → FakeDB + monkeypatch 服务层 (免真实 DB/Chroma/LLM)
"""

from typing import Any

import pytest
from httpx import AsyncClient

from app.dependencies import get_db, require_internal_key
from app.main import app
from app.schemas.rag import RagSearchRequest
from app.services.config_service import ConfigService
from app.services.rag_service import RagService
from app.utils.exceptions import UnauthorizedException
from tests.conftest import FakeDB, StubListResult

# 测试用内部密钥
TEST_INTERNAL_KEY = "test-internal-key-64-hex"


def _fake_chunks() -> list[dict]:
    """构造 _retrieve 桩返回的分块 (chroma 结构: chunk_id/text/score/metadata)"""
    return [
        {
            "chunk_id": "chunk-1",
            "text": "员工年假为每年 5 天。",
            "score": 0.92,
            "metadata": {
                "document_id": 11,
                "document_title": "年假制度",
                "file_name": "leave.pdf",
                "chunk_index": 0,
            },
        },
        {
            "chunk_id": "chunk-2",
            "text": "年假需提前 3 天在 OA 系统申请。",
            "score": 0.85,
            "metadata": {
                "document_id": 11,
                "document_title": "年假制度",
                "file_name": "leave.pdf",
                "chunk_index": 1,
            },
        },
    ]


async def _fake_rag_params(db: Any) -> dict[str, Any]:
    """get_rag_params 桩 — 静态方法被实例调用时传入 db"""
    return {
        "top_k": 5,
        "similarity_threshold": 0.75,
        "max_context_tokens": 4000,
        "graph_enhance_enabled": False,
        "graph_entity_top_k": 3,
    }


def _patch_config_key(monkeypatch: Any, expected: str | None) -> None:
    """monkeypatch ConfigService.get_value — 只服务 internal_api_key 读取"""

    async def _fake_get_value(db: Any, key: str, default: Any = None) -> Any:
        if key == "internal_api_key":
            return expected
        return default

    monkeypatch.setattr(ConfigService, "get_value", _fake_get_value)


class TestRequireInternalKeyUnit:
    """require_internal_key 依赖函数直测 (真逻辑 + FakeDB, 免 ASGI 层)"""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_missing_header_rejected(self, monkeypatch: Any) -> None:
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        with pytest.raises(UnauthorizedException) as exc:
            await require_internal_key(x_internal_key=None, db=FakeDB())
        assert exc.value.code == 40100

    @pytest.mark.asyncio(loop_scope="function")
    async def test_wrong_key_rejected(self, monkeypatch: Any) -> None:
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        with pytest.raises(UnauthorizedException):
            await require_internal_key(x_internal_key="wrong-key", db=FakeDB())

    @pytest.mark.asyncio(loop_scope="function")
    async def test_key_not_configured_fail_closed(self, monkeypatch: Any) -> None:
        """sys_config 无密钥 (expected=None) → fail-closed 拒绝"""
        _patch_config_key(monkeypatch, None)
        with pytest.raises(UnauthorizedException):
            await require_internal_key(x_internal_key=TEST_INTERNAL_KEY, db=FakeDB())

    @pytest.mark.asyncio(loop_scope="function")
    async def test_correct_key_passes(self, monkeypatch: Any) -> None:
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        # 不抛异常即通过
        await require_internal_key(x_internal_key=TEST_INTERNAL_KEY, db=FakeDB())


class TestRagSearchEndpoint:
    """端点级测试 — get_db 覆盖为 FakeDB, 真实 require_internal_key + 服务层打桩"""

    @pytest.fixture
    def override_db(self) -> Any:
        def _override(fake_db: FakeDB) -> None:
            async def _fake_get_db():
                yield fake_db

            app.dependency_overrides[get_db] = _fake_get_db

        yield _override
        app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_missing_key_40100(
        self, async_client: AsyncClient, override_db: Any, monkeypatch: Any
    ) -> None:
        override_db(FakeDB())
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        resp = await async_client.post("/api/v1/rag/search", json={"question": "年假"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100

    @pytest.mark.asyncio(loop_scope="function")
    async def test_wrong_key_40100(
        self, async_client: AsyncClient, override_db: Any, monkeypatch: Any
    ) -> None:
        override_db(FakeDB())
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        resp = await async_client.post(
            "/api/v1/rag/search",
            json={"question": "年假"},
            headers={"X-Internal-Key": "wrong-key"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100

    @pytest.mark.asyncio(loop_scope="function")
    async def test_search_ok_structure(
        self, async_client: AsyncClient, override_db: Any, monkeypatch: Any
    ) -> None:
        """正确密钥 → 200, data 含 chunks/sources/top_k/similarity_threshold"""
        override_db(FakeDB())
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        monkeypatch.setattr(ConfigService, "get_rag_params", _fake_rag_params)

        async def _fake_retrieve(
            question: str, category_ids: list[int], rag_params: dict[str, Any]
        ) -> list[dict]:
            return _fake_chunks()

        monkeypatch.setattr(RagService, "_retrieve", _fake_retrieve)

        resp = await async_client.post(
            "/api/v1/rag/search",
            json={"question": "年假怎么申请"},
            headers={"X-Internal-Key": TEST_INTERNAL_KEY},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["top_k"] == 5
        assert data["similarity_threshold"] == 0.75
        # chunks 结构 (build_retrieved_chunks 输出)
        assert len(data["chunks"]) == 2
        assert data["chunks"][0]["chunk_id"] == "chunk-1"
        assert data["chunks"][0]["document_id"] == 11
        assert data["chunks"][0]["title"] == "年假制度"
        assert data["chunks"][0]["score"] == 0.92
        # sources 按文档聚合去重, relevance_score 取最高分
        assert len(data["sources"]) == 1
        assert data["sources"][0]["document_id"] == 11
        assert data["sources"][0]["relevance_score"] == 0.92

    @pytest.mark.asyncio(loop_scope="function")
    async def test_invalid_category_ids_40000(
        self, async_client: AsyncClient, override_db: Any, monkeypatch: Any
    ) -> None:
        """category_ids 不存在 → 40000 (复用 _validate_category_ids)"""
        # FakeDB.execute 返回空列表桩 → 分类全部缺失
        override_db(FakeDB(execute_results=[StubListResult([])]))
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        monkeypatch.setattr(ConfigService, "get_rag_params", _fake_rag_params)

        resp = await async_client.post(
            "/api/v1/rag/search",
            json={"question": "年假", "category_ids": [999]},
            headers={"X-Internal-Key": TEST_INTERNAL_KEY},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 40000

    @pytest.mark.asyncio(loop_scope="function")
    async def test_invalid_body_42200(
        self, async_client: AsyncClient, override_db: Any, monkeypatch: Any
    ) -> None:
        """空问题 → 42200 参数校验"""
        # 请求体校验失败在 require_internal_key 之前拦截, 但覆盖 get_db 避免真实连接
        override_db(FakeDB())
        _patch_config_key(monkeypatch, TEST_INTERNAL_KEY)
        resp = await async_client.post(
            "/api/v1/rag/search",
            json={"question": ""},
            headers={"X-Internal-Key": TEST_INTERNAL_KEY},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 42200


class TestRagSearchService:
    """RagService.search 单元测试 — 无 LLM 无落库"""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_search_no_llm_no_persist(self, monkeypatch: Any) -> None:
        """search 仅做检索组装: 分类校验 + _retrieve + chunks/sources 构建"""
        monkeypatch.setattr(ConfigService, "get_rag_params", _fake_rag_params)

        async def _fake_retrieve(
            question: str, category_ids: list[int], rag_params: dict[str, Any]
        ) -> list[dict]:
            return _fake_chunks()

        monkeypatch.setattr(RagService, "_retrieve", _fake_retrieve)

        db = FakeDB()
        resp = await RagService.search(db, RagSearchRequest(question="年假怎么申请"))
        assert resp.top_k == 5
        assert resp.similarity_threshold == 0.75
        assert len(resp.chunks) == 2
        assert len(resp.sources) == 1
        # 无落库行为: 纯查询链路不触发 commit
        assert db.committed == 0
