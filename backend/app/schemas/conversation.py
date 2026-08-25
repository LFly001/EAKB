"""
RAG 对话会话 Pydantic 模型
入参校验 (创建/改标题) + 出参序列化 (ConversationInfo/ConversationDetail/MessageInfo)

注意: DB 中 category_ids 为逗号分隔字符串 (DESIGN 4.1.7 VARCHAR(500)),
接口层统一暴露为 List[int], 序列化时自动转换。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ==========================================
# category_ids 字符串 ⇄ 列表转换
# ==========================================


def parse_category_ids(raw: str | None) -> list[int]:
    """ "1,2,3" → [1, 2, 3]; 空/非法值静默忽略"""
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def join_category_ids(ids: list[int] | None) -> str | None:
    """[1, 2, 3] → "1,2,3"; 空列表/None → None (不限范围)"""
    if not ids:
        return None
    return ",".join(str(i) for i in ids)


# ==========================================
# 入参
# ==========================================


class ConversationCreate(BaseModel):
    """新建对话请求"""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="对话标题（默认「新对话」）",
    )
    template_id: int | None = Field(default=None, description="使用的提示词模板ID")
    category_ids: list[int] | None = Field(
        default=None, description="限定知识库分类ID列表（默认不限）"
    )

    model_config = ConfigDict(extra="forbid")


class ConversationTitleUpdate(BaseModel):
    """修改对话标题请求"""

    title: str = Field(min_length=1, max_length=100, description="新标题")

    model_config = ConfigDict(extra="forbid")


# ==========================================
# 出参
# ==========================================


class MessageInfo(BaseModel):
    """对话消息 (DESIGN 4.1.8)"""

    id: int
    conversation_id: int
    role: str
    question: str | None = None
    answer: str | None = None
    prompt_full: str | None = None
    retrieved_chunks: list[dict] = Field(
        default_factory=list, description="检索到的分块"
    )
    sources: list[dict] = Field(default_factory=list, description="来源文档")
    model_name: str | None = None
    token_usage: dict | None = None
    response_time_ms: int | None = None
    feedback: str | None = None
    feedback_comment: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("retrieved_chunks", "sources", mode="before")
    @classmethod
    def _json_default_list(cls, v):
        """DB JSON 为 NULL 时序列化为空列表, 前端无需判空"""
        return v or []


class ConversationInfo(BaseModel):
    """对话会话摘要"""

    id: int
    title: str
    template_id: int | None = None
    category_ids: list[int] = Field(default_factory=list, description="限定分类ID列表")
    message_count: int = 0
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ended_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("category_ids", mode="before")
    @classmethod
    def _parse_category_ids(cls, v):
        """DB 逗号分隔字符串 → List[int]"""
        if isinstance(v, str):
            return parse_category_ids(v)
        return v or []


class ConversationDetail(ConversationInfo):
    """对话详情 — 会话信息 + 全部消息 (时间正序)"""

    messages: list[MessageInfo] = Field(default_factory=list, description="消息列表")
