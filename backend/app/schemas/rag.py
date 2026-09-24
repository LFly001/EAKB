"""
RAG 智能问答 Pydantic 模型
流式问答入参 (ChatStreamRequest) / 反馈入参 (MessageFeedbackRequest)
SSE 事件负载结构 (ChatMetaEvent/ChatSourcesEvent/ChatDoneEvent, 前后端契约见 docs/api-reference.md)
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ==========================================
# 入参
# ==========================================


class ChatStreamRequest(BaseModel):
    """流式问答请求体 (POST /api/v1/rag/chat-stream)"""

    question: str = Field(min_length=1, max_length=4000, description="用户问题")
    conversation_id: int | None = Field(
        default=None, description="会话ID（不传自动新建，标题取问题前20字）"
    )
    template_id: int | None = Field(
        default=None, description="提示词模板ID（优先于对话/分类自动匹配）"
    )
    category_ids: list[int] | None = Field(
        default=None,
        description="本次提问限定分类（显式传入时覆盖对话范围并回写；空列表=不限）",
    )

    model_config = ConfigDict(extra="forbid")


class MessageFeedbackRequest(BaseModel):
    """回答反馈请求 (POST /api/v1/rag/messages/{id}/feedback)"""

    feedback: Literal["positive", "negative"] = Field(
        description="positive=点赞 negative=点踩"
    )
    comment: str | None = Field(default=None, max_length=1000, description="反馈备注")

    model_config = ConfigDict(extra="forbid")


# ==========================================
# 内部检索接口 (POST /api/v1/rag/search, 供 ESD 知识 agent 调用)
# ==========================================


class RagSearchRequest(BaseModel):
    """无状态检索请求 — 无 LLM、无落库, X-Internal-Key 鉴权"""

    question: str = Field(min_length=1, max_length=4000, description="检索查询")
    category_ids: list[int] | None = Field(
        default=None, description="限定分类（空列表=不限）"
    )

    model_config = ConfigDict(extra="forbid")


class RagSearchResponse(BaseModel):
    """检索结果 — 分块列表 + 按文档聚合的来源引用 + 本次检索参数"""

    chunks: list[dict] = Field(default_factory=list, description="检索分块")
    sources: list[dict] = Field(default_factory=list, description="来源引用")
    top_k: int = Field(description="检索返回条数")
    similarity_threshold: float = Field(description="相似度阈值")


# ==========================================
# SSE 事件负载 (data 字段 JSON 结构)
# ==========================================


class ChatMetaEvent(BaseModel):
    """meta 事件 — 流开始, 携带会话/消息标识"""

    conversation_id: int
    user_message_id: int
    template_id: int | None = None
    template_name: str | None = None


class ChatSourcesEvent(BaseModel):
    """sources 事件 — 检索完成后推送来源引用"""

    sources: list[dict] = Field(default_factory=list)
    retrieved_chunks: list[dict] = Field(default_factory=list)


class ChatDoneEvent(BaseModel):
    """done 事件 — 生成完成, 携带助手消息ID与统计"""

    conversation_id: int
    message_id: int
    token_usage: dict | None = None
    response_time_ms: int | None = None
