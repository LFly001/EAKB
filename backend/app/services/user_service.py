"""
用户管理服务层 (管理员操作)
用户列表、创建、更新、启用/禁用
"""

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import SysUser
from app.schemas.user import (
    UserCreateRequest,
    UserQuery,
    UserUpdateRequest,
)
from app.utils.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)


class UserService:
    """用户管理服务 — 仅管理员调用"""

    # ==========================================
    # 用户列表 (分页 + 筛选)
    # ==========================================
    @staticmethod
    async def get_list(db: AsyncSession, query: UserQuery) -> tuple[list[SysUser], int]:
        """管理员查询用户列表"""
        conditions = []

        # 关键词搜索 (用户名 / 姓名 / 部门)
        if query.keyword:
            keyword = f"%{query.keyword}%"
            conditions.append(
                or_(
                    SysUser.username.like(keyword),
                    SysUser.real_name.like(keyword),
                    SysUser.department.like(keyword),
                )
            )

        # 角色过滤
        if query.role:
            conditions.append(SysUser.role == query.role)

        # 状态过滤
        if query.status is not None:
            conditions.append(SysUser.status == query.status)

        # 总数
        count_stmt = select(func.count()).select_from(SysUser)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = (await db.execute(count_stmt)).scalar() or 0

        # 分页列表 (按创建时间倒序)
        stmt = (
            select(SysUser)
            .where(*conditions)
            .order_by(SysUser.created_at.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # ==========================================
    # 用户详情
    # ==========================================
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> SysUser:
        result = await db.execute(select(SysUser).where(SysUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException(f"用户不存在 (id={user_id})")
        return user

    # ==========================================
    # 管理员创建用户
    # ==========================================
    @staticmethod
    async def create(db: AsyncSession, req: UserCreateRequest) -> SysUser:
        # 检查用户名唯一
        existing = await db.execute(
            select(SysUser).where(SysUser.username == req.username)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(f"用户名 '{req.username}' 已存在")

        user = SysUser(
            username=req.username,
            password_hash=hash_password(req.password),
            email=req.email,
            phone=req.phone,
            real_name=req.real_name,
            department=req.department,
            position=req.position,
            role=req.role,
            status=req.status,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"[User] 管理员创建用户: {user.username} (role={user.role})")
        return user

    # ==========================================
    # 更新用户
    # ==========================================
    @staticmethod
    async def update(db: AsyncSession, user_id: int, req: UserUpdateRequest) -> SysUser:
        user = await UserService.get_by_id(db, user_id)

        # 只更新传入的字段
        update_fields = req.model_dump(exclude_unset=True)
        for field, value in update_fields.items():
            setattr(user, field, value)

        await db.commit()
        await db.refresh(user)
        logger.info(f"[User] 管理员更新用户: {user.username}")
        return user

    # ==========================================
    # 启用 / 禁用
    # ==========================================
    @staticmethod
    async def toggle_status(db: AsyncSession, user_id: int, status: int) -> SysUser:
        if status not in (0, 1):
            raise BadRequestException("状态值只能为 0(禁用) 或 1(启用)")

        user = await UserService.get_by_id(db, user_id)
        user.status = status
        await db.commit()
        await db.refresh(user)
        action = "启用" if status == 1 else "禁用"
        logger.info(f"[User] 管理员{action}用户: {user.username}")
        return user

    # ==========================================
    # 删除用户 (物理删除，管理员慎用)
    # ==========================================
    @staticmethod
    async def delete(db: AsyncSession, user_id: int) -> None:
        user = await UserService.get_by_id(db, user_id)
        await db.delete(user)
        await db.commit()
        logger.warning(f"[User] 管理员删除用户: {user.username} (id={user_id})")

    # ==========================================
    # 批量操作 (Phase 8 优化: 一次查询 + 一次提交, 替换路由内逐用户循环)
    # ==========================================
    @staticmethod
    async def batch_operate(
        db: AsyncSession,
        action: str,
        user_ids: list[int],
    ) -> tuple[list[str], list[int]]:
        """
        批量启用/禁用/删除用户。

        Args:
            action: enable / disable / delete (路由层已校验)
            user_ids: 已去重、已排除操作者本人的用户 ID 列表 (路由层已校验)

        Returns:
            (成功处理的用户名列表, 未找到的用户 ID 列表)
        """
        result = await db.execute(select(SysUser).where(SysUser.id.in_(user_ids)))
        users = list(result.scalars().all())
        user_map = {u.id: u for u in users}
        missing = [uid for uid in user_ids if uid not in user_map]

        processed: list[str] = []
        if action == "delete":
            for user in users:
                processed.append(user.username)
                await db.delete(user)
        else:
            status = 1 if action == "enable" else 0
            for user in users:
                user.status = status
                processed.append(user.username)

        await db.commit()

        action_text = (
            "删除" if action == "delete" else ("启用" if action == "enable" else "禁用")
        )
        logger.info(
            f"[User] 批量{action_text}用户: {len(processed)} 个成功, "
            f"{len(missing)} 个不存在, ids={user_ids}"
        )
        return processed, missing
