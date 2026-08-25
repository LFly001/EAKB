"""
数据看板服务 (Phase 7)
聚合统计: 用户总数 / 文档总量 / 问答会话 / 今日问答量 / 向量化文档数 / 今日操作数
Phase 8 优化: 6 次串行 count 合并为 4 次查询 —
  ① 用户总数
  ② 文档总量 + 向量化文档数 (条件聚合, 一次扫描 kb_document)
  ③ 会话总数
  ④ 今日问答量 + 今日操作数 (UNION ALL 一次往返)
各查询仍串行执行 (同一 AsyncSession 复用单连接, 并发 execute 会乱序)
"""

from datetime import datetime, time
from typing import Any

from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import RagConversation
from app.models.document import KbDocument
from app.models.message import RagMessage
from app.models.operation_log import SysOperationLog
from app.models.user import SysUser
from app.schemas.admin import DashboardStats


class DashboardService:
    """看板统计服务 — 仅管理员接口调用"""

    @staticmethod
    async def _count(db: AsyncSession, stmt: Any) -> int:
        """执行 count 查询并安全取值"""
        result = await db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def get_stats(db: AsyncSession) -> DashboardStats:
        """聚合看板统计 (Phase 8: 4 次查询)"""
        today_start = datetime.combine(datetime.now().date(), time.min)

        # ---- ① 用户总数 ----
        stmt_user = select(func.count()).select_from(SysUser)

        # ---- ② 文档总量 + 向量化数 (条件聚合, 一次扫描) ----
        stmt_document = (
            select(
                func.count().label("document_count"),
                func.sum(
                    case((KbDocument.vector_status == "completed", 1), else_=0)
                ).label("vectorized_count"),
            )
            .select_from(KbDocument)
            .where(KbDocument.status != -1)  # 排除软删文档
        )

        # ---- ③ 会话总数 ----
        stmt_conversation = select(func.count()).select_from(RagConversation)

        # ---- ④ 今日问答量 + 今日操作数 (UNION ALL 合并为一次往返) ----
        stmt_today = union_all(
            select(literal("question").label("kind"), func.count().label("cnt"))
            .select_from(RagMessage)
            .where(
                RagMessage.role == "user",
                RagMessage.created_at >= today_start,
            ),
            select(literal("operation").label("kind"), func.count().label("cnt"))
            .select_from(SysOperationLog)
            .where(SysOperationLog.created_at >= today_start),
        )

        # ---- 串行执行 (同一会话同一连接, 逐个查询) ----
        user_count = await DashboardService._count(db, stmt_user)
        doc_row = (await db.execute(stmt_document)).one()
        # SUM 经 aiomysql 可能返回 Decimal, 统一转 int 供 pydantic 校验
        document_count = int(doc_row[0] or 0)
        vectorized_count = int(doc_row[1] or 0)  # sum() 在无匹配行时为 NULL
        conversation_count = await DashboardService._count(db, stmt_conversation)
        today_map = {
            kind: cnt or 0 for kind, cnt in (await db.execute(stmt_today)).all()
        }
        today_question_count = today_map.get("question", 0)
        today_operation_count = today_map.get("operation", 0)

        return DashboardStats(
            user_count=user_count,
            document_count=document_count,
            conversation_count=conversation_count,
            today_question_count=today_question_count,
            vectorized_document_count=vectorized_count,
            today_operation_count=today_operation_count,
        )
