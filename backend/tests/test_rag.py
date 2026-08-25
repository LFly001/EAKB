"""
Phase 5 RAG 智能问答模块测试
覆盖: 检索结果组装 / 无匹配策略 / Schema 校验 / SSE 事件格式 / 鉴权边界

说明: 采用纯逻辑 + monkeypatch 模式, 无需真实 MySQL/Chroma/LLM。
完整链路 (SSE 流式/检索/落库) 在 VM 环境按 docs/phase5-test-guide.md 手工自测。
"""

import json

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.models.message import RagMessage
from app.schemas.conversation import (
    ConversationInfo,
    MessageInfo,
    join_category_ids,
    parse_category_ids,
)
from app.schemas.rag import ChatStreamRequest, MessageFeedbackRequest
from app.services.rag_service import (
    NO_MATCH_REPLY,
    build_context,
    build_history,
    build_retrieved_chunks,
    build_sources,
    estimate_usage,
    split_fallback_reply,
    sse_event,
)

# ==========================================
# 检索结果组装
# ==========================================


def _chunk(chunk_id: str, doc_id: int, title: str, text: str, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "score": score,
        "distance": round(2 * (1 - score), 4),
        "metadata": {
            "document_id": doc_id,
            "document_title": title,
            "file_name": f"{title}.pdf",
            "chunk_index": 0,
        },
    }


class TestBuildSources:
    def test_dedupe_by_document_and_max_score(self):
        """同一文档多个分块 → 聚合成一条来源, relevance_score 取最高分"""
        chunks = [
            _chunk("c1", 1, "员工手册", "请假流程…", 0.92),
            _chunk("c2", 1, "员工手册", "加班规定…", 0.81),
            _chunk("c3", 2, "考勤制度", "打卡规则…", 0.75),
        ]
        sources = build_sources(chunks)
        assert len(sources) == 2
        assert sources[0]["document_id"] == 1
        assert sources[0]["title"] == "员工手册"
        assert sources[0]["file_name"] == "员工手册.pdf"
        assert sources[0]["relevance_score"] == 0.92  # 取最高分
        assert sources[1]["document_id"] == 2
        assert sources[1]["relevance_score"] == 0.75

    def test_empty_chunks(self):
        assert build_sources([]) == []

    def test_chunk_without_document_id_skipped(self):
        chunk = _chunk("c1", 1, "员工手册", "请假流程…", 0.92)
        del chunk["metadata"]["document_id"]
        assert build_sources([chunk]) == []


class TestBuildRetrievedChunks:
    def test_fields(self):
        """retrieved_chunks 结构与 DESIGN 4.1.8 对齐"""
        chunks = [_chunk("doc_1_chunk_0", 1, "员工手册", "请假流程…", 0.92)]
        result = build_retrieved_chunks(chunks)
        assert result[0] == {
            "chunk_id": "doc_1_chunk_0",
            "document_id": 1,
            "title": "员工手册",
            "text": "请假流程…",
            "score": 0.92,
        }


class TestBuildContext:
    def test_join_blocks(self):
        """多个分块以分隔符拼接, 带文档标题标注"""
        chunks = [
            _chunk("c1", 1, "员工手册", "请假流程：提前一天申请。", 0.92),
            _chunk("c2", 1, "员工手册", "加班需直属主管审批。", 0.81),
        ]
        context = build_context(chunks, 4096)
        assert "员工手册" in context
        assert "请假流程" in context and "加班" in context
        assert "---" in context

    def test_truncate_by_max_tokens(self):
        """超出 max_context_tokens 的分块被整块截断, 首个分块始终保留"""
        chunks = [
            _chunk("c1", 1, "文档A", "首块内容。" * 10, 0.92),
            _chunk("c2", 1, "文档A", "二块内容。" * 100, 0.81),
        ]
        context = build_context(chunks, max_context_tokens=30)
        assert "首块内容" in context
        assert "二块内容" not in context


class TestEstimateUsage:
    def test_usage_estimate(self):
        usage = estimate_usage("问题内容", "回答内容")
        assert (
            usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        )
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0


# ==========================================
# 无匹配固定回复 (禁止编造策略)
# ==========================================


class TestNoMatchReply:
    def test_reply_nonempty(self):
        assert len(NO_MATCH_REPLY) > 0
        assert "未找到" in NO_MATCH_REPLY

    def test_split_fallback_reply(self):
        """固定回复按分片模拟流式, 拼接后与原文一致"""
        pieces = split_fallback_reply(NO_MATCH_REPLY, size=80)
        assert len(pieces) > 1
        assert "".join(pieces) == NO_MATCH_REPLY

    def test_split_short_text(self):
        assert split_fallback_reply("短文本") == ["短文本"]


# ==========================================
# 多轮历史组装 (Phase 8 修正: 无效轮次连带丢弃配对用户问题)
# ==========================================


class TestBuildHistory:
    def _msg(
        self,
        role: str,
        question: str | None = None,
        answer: str | None = None,
        chunks: list | None = None,
    ) -> RagMessage:
        return RagMessage(
            id=1,
            conversation_id=1,
            role=role,
            question=question,
            answer=answer,
            retrieved_chunks=chunks,
        )

    def test_valid_round_kept(self):
        rows = [
            self._msg("user", question="年假怎么申请"),
            self._msg("assistant", answer="提前一天申请。", chunks=[{"score": 0.9}]),
        ]
        history = build_history(rows)
        assert history == [
            {"role": "user", "content": "年假怎么申请"},
            {"role": "assistant", "content": "提前一天申请。"},
        ]

    def test_no_match_round_dropped_with_user_question(self):
        """无匹配固定回复轮次: 助手与其配对的用户问题一并丢弃"""
        rows = [
            self._msg("user", question="三角洲是什么？"),
            self._msg("assistant", answer=NO_MATCH_REPLY, chunks=[]),
            self._msg("user", question="宪法第一条如何描述"),
            self._msg("assistant", answer="第一条是……", chunks=[{"score": 0.9}]),
        ]
        history = build_history(rows)
        assert history == [
            {"role": "user", "content": "宪法第一条如何描述"},
            {"role": "assistant", "content": "第一条是……"},
        ]

    def test_failed_round_dropped_with_user_question(self):
        """生成失败轮次 (answer 为空): 配对用户问题一并丢弃"""
        rows = [
            self._msg("user", question="上一个失败的问题"),
            self._msg("assistant", answer=None, chunks=None),
            self._msg("user", question="正常问题"),
            self._msg("assistant", answer="正常回答", chunks=[{"score": 0.8}]),
        ]
        history = build_history(rows)
        assert history == [
            {"role": "user", "content": "正常问题"},
            {"role": "assistant", "content": "正常回答"},
        ]

    def test_trailing_orphan_user_dropped(self):
        """尾部未配对的用户消息直接丢弃"""
        rows = [self._msg("user", question="无回答的问题")]
        assert build_history(rows) == []


# ==========================================
# 分类范围转换
# ==========================================


class TestCategoryIds:
    def test_parse(self):
        assert parse_category_ids("1,2,3") == [1, 2, 3]
        assert parse_category_ids(" 1 , 2 ") == [1, 2]
        assert parse_category_ids(None) == []
        assert parse_category_ids("") == []

    def test_parse_ignore_invalid(self):
        assert parse_category_ids("1,abc,3") == [1, 3]

    def test_join(self):
        assert join_category_ids([1, 2, 3]) == "1,2,3"
        assert join_category_ids([]) is None
        assert join_category_ids(None) is None

    def test_roundtrip(self):
        assert parse_category_ids(join_category_ids([3, 1])) == [3, 1]


# ==========================================
# Schema 校验
# ==========================================


class TestSchemas:
    def test_chat_stream_request_ok(self):
        req = ChatStreamRequest(
            question="年假怎么申请？",
            conversation_id=1,
            template_id=2,
            category_ids=[1, 2],
        )
        assert req.question == "年假怎么申请？"
        assert req.category_ids == [1, 2]

    def test_chat_stream_request_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            ChatStreamRequest(question="")

    def test_chat_stream_request_forbid_extra(self):
        with pytest.raises(ValidationError):
            ChatStreamRequest(question="x", unknown_field=1)

    def test_feedback_request_ok(self):
        req = MessageFeedbackRequest(feedback="positive", comment="很好")
        assert req.feedback == "positive"

    def test_feedback_request_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            MessageFeedbackRequest(feedback="neutral")

    def test_conversation_info_parse_category_ids(self):
        """DB 逗号分隔字符串 → 接口 List[int]"""
        info = ConversationInfo.model_validate(
            {
                "id": 1,
                "title": "测试",
                "category_ids": "1,2,3",
                "message_count": 0,
                "status": "active",
            }
        )
        assert info.category_ids == [1, 2, 3]

    def test_message_info_null_json_defaults(self):
        """retrieved_chunks/sources 为 NULL 时序列化为空列表"""
        info = MessageInfo.model_validate(
            {"id": 1, "conversation_id": 1, "role": "assistant", "answer": "x"}
        )
        assert info.retrieved_chunks == []
        assert info.sources == []


# ==========================================
# SSE 事件格式
# ==========================================


class TestSseEvent:
    def test_event_format(self):
        """sse-starlette 事件 dict: data 为 JSON 字符串, event 为事件类型"""
        event = sse_event("delta", {"content": "你好"})
        assert event["event"] == "delta"
        assert json.loads(event["data"]) == {"content": "你好"}


# ==========================================
# 鉴权边界 (无 Token 一律 401, 不依赖真实数据库)
# ==========================================


class TestAuthBoundary:
    @pytest.mark.asyncio
    async def test_chat_stream_requires_auth(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/v1/rag/chat-stream",
            json={"question": "测试问题"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == 40100  # 项目统一错误码 (401*100)

    @pytest.mark.asyncio
    async def test_conversation_list_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/rag/conversations/")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_conversation_detail_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/rag/conversations/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_conversation_requires_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/v1/rag/conversations/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_title_requires_auth(self, async_client: AsyncClient):
        response = await async_client.put(
            "/api/v1/rag/conversations/1/title", json={"title": "新标题"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_feedback_requires_auth(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/v1/rag/messages/1/feedback", json={"feedback": "positive"}
        )
        assert response.status_code == 401
