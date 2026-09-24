"""
RAG 智能问答路由 — /api/v1/rag
流式问答 (SSE) / 对话会话增删改查 / 消息反馈

对齐 DESIGN.md 6.6:
- POST   /chat-stream                 流式问答 (SSE, 统一走此接口)
- GET    /conversations/              我的对话列表 (分页)
- POST   /conversations/              新建对话
- GET    /conversations/{id}          对话详情（含消息）
- DELETE /conversations/{id}          删除对话
- PUT    /conversations/{id}/title    修改对话标题
- POST   /messages/{id}/feedback      回答点赞/点踩反馈

SSE 事件协议详见 docs/api-reference.md (meta/sources/delta/done/error)
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_internal_key
from app.models.user import SysUser
from app.schemas.common import PageQuery, PageResponse
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationInfo,
    ConversationTitleUpdate,
    MessageInfo,
)
from app.schemas.rag import (
    ChatStreamRequest,
    MessageFeedbackRequest,
    RagSearchRequest,
)
from app.services.conversation_service import ConversationService
from app.services.log_service import LogService
from app.services.rag_service import RagService
from app.utils.response import success

router = APIRouter()

# 操作日志模块名
_LOG_MODULE = "rag"


# ==========================================
# POST /chat-stream — SSE 流式问答 (DESIGN 6.6)
# ==========================================
@router.post("/chat-stream", summary="流式问答 (SSE)")
async def chat_stream(
    req: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """
    发起流式问答。请求体:
    { question, conversation_id?, template_id?, category_ids? }

    事件流: meta → sources → delta* → done; 失败发 error 事件。
    无匹配知识库内容时返回固定提示 (不调用 LLM)。
    """
    return await RagService.stream_chat(
        db,
        user,
        req,
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )


# ==========================================
# POST /search — 内部无状态检索 (ESD 集成, DESIGN 8.1)
# ==========================================
@router.post("/search", summary="内部检索 (ESD 集成)")
async def search(
    req: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_key),
):
    """
    无状态向量检索 — 供 ESD 知识 agent 调用。

    鉴权: X-Internal-Key 头 (内部服务密钥, 不走 JWT)。
    行为: 复用问答检索环节, 返回分块+来源, 无 LLM 调用、无消息落库。
    """
    resp = await RagService.search(db, req)
    return success(data=resp.model_dump())


# ==========================================
# 对话会话 (DESIGN 6.6)
# ==========================================


@router.get("/conversations/", summary="我的对话列表")
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, description="标题关键词"),
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
):
    """我的对话列表 (分页, 按更新时间倒序)"""
    items, total = await ConversationService.list_conversations(
        db, user.id, PageQuery(page=page, page_size=page_size, keyword=keyword)
    )
    return success(
        data=PageResponse.from_list(
            items=[
                ConversationInfo.model_validate(item).model_dump() for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    )


@router.post("/conversations/", summary="新建对话")
async def create_conversation(
    req: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """新建对话 (标题默认「新对话」)"""
    conversation = await ConversationService.create(db, user.id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="create_conversation",
        module=_LOG_MODULE,
        target_type="conversation",
        target_id=str(conversation.id),
        detail={"title": conversation.title},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=ConversationInfo.model_validate(conversation).model_dump(),
        msg="对话创建成功",
    )


@router.get("/conversations/{conversation_id}", summary="对话详情（含消息）")
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
):
    """对话详情 — 会话信息 + 全部消息 (时间正序)"""
    conversation, messages = await ConversationService.get_detail(
        db, user.id, conversation_id
    )
    detail = ConversationDetail(
        **ConversationInfo.model_validate(conversation).model_dump(),
        messages=[MessageInfo.model_validate(m) for m in messages],
    )
    return success(data=detail.model_dump())


@router.delete("/conversations/{conversation_id}", summary="删除对话")
async def delete_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """删除对话 (物理删除, 消息级联清理; 仅限本人对话)"""
    conversation = await ConversationService.delete(db, user.id, conversation_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="delete_conversation",
        module=_LOG_MODULE,
        target_type="conversation",
        target_id=str(conversation_id),
        detail={"title": conversation.title},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg=f"对话 '{conversation.title}' 已删除")


@router.put("/conversations/{conversation_id}/title", summary="修改对话标题")
async def update_conversation_title(
    conversation_id: int,
    req: ConversationTitleUpdate,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """修改对话标题 (仅限本人对话)"""
    conversation = await ConversationService.update_title(
        db, user.id, conversation_id, req.title
    )

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="rename_conversation",
        module=_LOG_MODULE,
        target_type="conversation",
        target_id=str(conversation_id),
        detail={"title": conversation.title},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=ConversationInfo.model_validate(conversation).model_dump(),
        msg="标题已更新",
    )


# ==========================================
# 消息反馈 (DESIGN 6.6)
# ==========================================


@router.post("/messages/{message_id}/feedback", summary="回答点赞/点踩反馈")
async def submit_feedback(
    message_id: int,
    req: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """对助手回答提交点赞/点踩反馈 (可带备注; 仅限本人会话消息)"""
    message = await RagService.submit_feedback(db, user.id, message_id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="message_feedback",
        module=_LOG_MODULE,
        target_type="message",
        target_id=str(message_id),
        detail={"feedback": req.feedback, "comment": req.comment},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=MessageInfo.model_validate(message).model_dump(), msg="反馈已提交"
    )
