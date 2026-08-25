"""
Phase 8 RAG 问答接口测试 (端点级)
覆盖: chat-stream SSE 帧格式 (meta/sources/delta/done) / 未登录 401 / 对话列表鉴权
模式: 依赖覆盖 + monkeypatch 服务层 (免真实 DB/Chroma/LLM);
      检索组装 / 无匹配策略等纯逻辑见 test_rag.py
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sse_starlette.sse import EventSourceResponse

from app.models.conversation import RagConversation
from app.services.conversation_service import ConversationService
from app.services.rag_service import RagService, sse_event
from tests.conftest import make_fake_user


def _fake_conversation(conv_id: int = 1) -> RagConversation:
    return RagConversation(
        id=conv_id,
        user_id=2,
        title="测试对话",
        message_count=1,
        status="active",
    )


class TestChatStream:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_chat_stream_sse_frames(
        self, async_client: AsyncClient, override_auth: Any, monkeypatch: Any
    ) -> None:
        """SSE 流按 meta → sources → delta → done 顺序输出 (服务层打桩)"""
        override_auth(make_fake_user(user_id=2, username="lisi", role="employee"))

        async def _fake_stream_chat(
            db: Any, user: Any, req: Any, ip_address: str | None = None
        ) -> EventSourceResponse:
            async def _gen():
                yield sse_event("meta", {"conversation_id": 1, "message_id": 10})
                yield sse_event("sources", {"sources": []})
                yield sse_event("delta", {"content": "你好，这是测试回答。"})
                yield sse_event(
                    "done",
                    {"conversation_id": 1, "message_id": 10, "token_usage": {}},
                )

            return EventSourceResponse(_gen())

        monkeypatch.setattr(RagService, "stream_chat", _fake_stream_chat)

        resp = await async_client.post(
            "/api/v1/rag/chat-stream",
            json={"question": "年假怎么申请？", "conversation_id": 1},
        )
        assert resp.status_code == 200
        text = resp.text
        # sse-starlette 帧格式: event: <name> \n data: <json> \n\n
        assert "event: meta" in text
        assert "event: sources" in text
        assert "event: delta" in text
        assert "event: done" in text
        assert "你好，这是测试回答。" in text
        assert '"conversation_id": 1' in text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_chat_stream_requires_auth(self, async_client: AsyncClient) -> None:
        """未登录调用 chat-stream → 40100"""
        resp = await async_client.post(
            "/api/v1/rag/chat-stream", json={"question": "测试问题"}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100

    @pytest.mark.asyncio(loop_scope="function")
    async def test_chat_stream_invalid_request(
        self, async_client: AsyncClient, override_auth: Any
    ) -> None:
        """空问题 → 42200 参数校验"""
        override_auth(make_fake_user(user_id=2, role="employee"))
        resp = await async_client.post("/api/v1/rag/chat-stream", json={"question": ""})
        assert resp.status_code == 422
        assert resp.json()["code"] == 42200


class TestConversations:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_list_conversations(
        self, async_client: AsyncClient, override_auth: Any, monkeypatch: Any
    ) -> None:
        """对话列表 → 200 + 分页结构 (服务层打桩)"""
        override_auth(make_fake_user(user_id=2, username="lisi", role="employee"))

        async def _fake_list(db: Any, user_id: int, query: Any) -> Any:
            assert user_id == 2
            return [_fake_conversation(1), _fake_conversation(2)], 2

        monkeypatch.setattr(ConversationService, "list_conversations", _fake_list)

        resp = await async_client.get("/api/v1/rag/conversations/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_list_conversations_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """未登录访问对话列表 → 40100"""
        resp = await async_client.get("/api/v1/rag/conversations/")
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100
