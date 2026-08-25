"""
对话会话服务 — rag_conversation 增删改查
会话列表 / 新建 / 详情(含消息) / 删除 / 改标题 / 消息计数

规则 (DESIGN 6.6 / 已确认决策):
- 会话仅本人可见可操作, 他人会话按不存在处理 (404)
- 删除为物理删除, 消息由数据库 FK ON DELETE CASCADE 清理
- category_ids DB 存逗号分隔字符串, 业务层用 List[int] (转换在 schemas/conversation.py)
"""

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import RagConversation
from app.models.message import RagMessage
from app.schemas.common import PageQuery
from app.schemas.conversation import ConversationCreate, join_category_ids
from app.utils.exceptions import NotFoundException


class ConversationService:
    """对话会话业务服务"""

    # ==========================================
    # 查询
    # ==========================================

    @staticmethod
    async def list_conversations(
        db: AsyncSession,
        user_id: int,
        query: PageQuery,
    ) -> tuple[list[RagConversation], int]:
        """我的对话列表 — 按更新时间倒序 (keyword 模糊匹配标题)"""
        conditions = [RagConversation.user_id == user_id]
        if query.keyword:
            conditions.append(RagConversation.title.like(f"%{query.keyword}%"))

        total = (
            await db.execute(select(func.count(RagConversation.id)).where(*conditions))
        ).scalar() or 0

        result = await db.execute(
            select(RagConversation)
            .where(*conditions)
            .order_by(RagConversation.updated_at.desc(), RagConversation.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_owned(
        db: AsyncSession,
        user_id: int,
        conversation_id: int,
    ) -> RagConversation:
        """按 ID 查询本人会话 — 不存在/非本人 → 404"""
        result = await db.execute(
            select(RagConversation).where(
                RagConversation.id == conversation_id,
                RagConversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise NotFoundException("对话不存在或无权访问")
        return conversation

    @staticmethod
    async def get_detail(
        db: AsyncSession,
        user_id: int,
        conversation_id: int,
    ) -> tuple[RagConversation, list[RagMessage]]:
        """对话详情 — 会话信息 + 全部消息 (时间正序)"""
        conversation = await ConversationService.get_owned(db, user_id, conversation_id)
        result = await db.execute(
            select(RagMessage)
            .where(RagMessage.conversation_id == conversation_id)
            .order_by(RagMessage.created_at.asc(), RagMessage.id.asc())
        )
        return conversation, list(result.scalars().all())

    # ==========================================
    # 写操作
    # ==========================================

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        req: ConversationCreate,
    ) -> RagConversation:
        """新建对话 (标题默认「新对话」)"""
        conversation = RagConversation(
            user_id=user_id,
            title=(req.title or "").strip() or "新对话",
            template_id=req.template_id,
            category_ids=join_category_ids(req.category_ids),
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        logger.info(
            f"[对话] 创建成功: id={conversation.id}, title={conversation.title}, "
            f"user_id={user_id}"
        )
        return conversation

    @staticmethod
    async def delete(
        db: AsyncSession,
        user_id: int,
        conversation_id: int,
    ) -> RagConversation:
        """删除会话 (物理删除, 消息 FK CASCADE 级联清理)"""
        conversation = await ConversationService.get_owned(db, user_id, conversation_id)
        await db.delete(conversation)
        await db.commit()
        logger.info(
            f"[对话] 删除成功: id={conversation_id}, title={conversation.title}"
        )
        return conversation

    @staticmethod
    async def update_title(
        db: AsyncSession,
        user_id: int,
        conversation_id: int,
        title: str,
    ) -> RagConversation:
        """修改对话标题"""
        conversation = await ConversationService.get_owned(db, user_id, conversation_id)
        conversation.title = title.strip()
        await db.commit()
        await db.refresh(conversation)
        logger.info(f"[对话] 标题已更新: id={conversation_id} → {conversation.title}")
        return conversation

    @staticmethod
    async def increment_message_count(
        db: AsyncSession,
        conversation_id: int,
    ) -> None:
        """消息轮数 +1 (每轮问答保存助手消息后调用; 会话不存在时静默忽略)"""
        result = await db.execute(
            select(RagConversation).where(RagConversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            return
        conversation.message_count = (conversation.message_count or 0) + 1
        await db.commit()

    # ==========================================
    # 供 RAG 问答流使用
    # ==========================================

    @staticmethod
    async def resolve_for_chat(
        db: AsyncSession,
        user_id: int,
        conversation_id: int | None,
        question: str,
    ) -> RagConversation:
        """
        解析问答所属会话: 指定 ID 则校验归属; 否则自动新建 (标题取问题前 20 字)。
        """
        if conversation_id is not None:
            return await ConversationService.get_owned(db, user_id, conversation_id)

        title = question.replace("\n", " ").strip()[:20] or "新对话"
        return await ConversationService.create(
            db,
            user_id,
            ConversationCreate(title=title),
        )
