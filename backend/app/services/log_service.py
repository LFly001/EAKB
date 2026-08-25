"""
操作日志服务
所有用户操作自动埋点写入 sys_operation_log
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_log import SysOperationLog


class LogService:
    """操作日志服务 — 全模块操作记录"""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: int | None = None,
        username: str | None = None,
        action: str,
        module: str = "auth",
        target_type: str | None = None,
        target_id: str | None = None,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        error_info: str | None = None,
    ) -> SysOperationLog:
        """写入一条操作日志"""
        log_entry = SysOperationLog(
            user_id=user_id,
            username=username,
            action=action,
            module=module,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_info=error_info,
        )
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        return log_entry

    @staticmethod
    async def get_list(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
        username: str | None = None,
        module: str | None = None,
        action: str | None = None,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[SysOperationLog], int]:
        """查询操作日志列表 (管理员使用, 分页 + 模块/用户/时间范围筛选)"""
        from sqlalchemy import func, select

        conditions = []
        if user_id:
            conditions.append(SysOperationLog.user_id == user_id)
        if username:
            conditions.append(SysOperationLog.username.like(f"%{username}%"))
        if module:
            conditions.append(SysOperationLog.module == module)
        if action:
            conditions.append(SysOperationLog.action == action)
        if status:
            conditions.append(SysOperationLog.status == status)
        if start_time:
            conditions.append(SysOperationLog.created_at >= start_time)
        if end_time:
            conditions.append(SysOperationLog.created_at <= end_time)

        # 总数
        count_stmt = select(func.count()).select_from(SysOperationLog)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = (await db.execute(count_stmt)).scalar() or 0

        # 分页
        stmt = (
            select(SysOperationLog)
            .where(*conditions)
            .order_by(SysOperationLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        return items, total
