"""
认证服务层
注册 / 登录 / 登出 / 个人信息 / 修改密码
"""

from datetime import datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import SysUser
from app.schemas.auth import RegisterRequest
from app.schemas.user import ProfileUpdateRequest, UserInfo
from app.utils.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)


class AuthService:
    """用户认证服务"""

    # ==========================================
    # 注册
    # ==========================================
    @staticmethod
    async def register(db: AsyncSession, req: RegisterRequest) -> SysUser:
        """用户注册: 查重 → 密码哈希 → 入库"""
        # 检查用户名是否已存在
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
            role="employee",  # 注册用户默认为普通员工
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"[Auth] 用户注册成功: {user.username} (id={user.id})")
        return user

    # ==========================================
    # 登录
    # ==========================================
    @staticmethod
    async def login(
        db: AsyncSession, username: str, password: str
    ) -> tuple[str, str, SysUser]:
        """登录: 查询用户 → 校验密码 → 更新最后登录时间 → 签发 Token"""
        # 查询用户
        result = await db.execute(select(SysUser).where(SysUser.username == username))
        user = result.scalar_one_or_none()

        if not user:
            raise UnauthorizedException("用户名或密码错误")

        # 检查用户状态
        if user.status != 1:
            raise UnauthorizedException("账号已被禁用，请联系管理员")

        # 校验密码
        if not verify_password(password, user.password_hash):
            raise UnauthorizedException("用户名或密码错误")

        # 更新最后登录时间
        user.last_login_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)

        # 签发 Token
        access_token = create_access_token(
            user_id=user.id, username=user.username, role=user.role
        )
        refresh_token = create_refresh_token(user_id=user.id, username=user.username)

        logger.info(f"[Auth] 用户登录成功: {user.username} (role={user.role})")
        return access_token, refresh_token, user

    # ==========================================
    # 刷新 Token
    # ==========================================
    @staticmethod
    async def refresh_access_token(
        db: AsyncSession, refresh_token_str: str
    ) -> tuple[str, str]:
        """用 Refresh Token 换取新的 Access Token + Refresh Token"""
        payload = decode_refresh_token(refresh_token_str)
        if not payload:
            raise UnauthorizedException("Refresh Token 无效或已过期")

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException("Refresh Token 缺少用户标识")

        # 确认用户仍然存在且状态正常
        result = await db.execute(select(SysUser).where(SysUser.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user or user.status != 1:
            raise UnauthorizedException("用户不存在或已禁用")

        new_access = create_access_token(
            user_id=user.id, username=user.username, role=user.role
        )
        new_refresh = create_refresh_token(user_id=user.id, username=user.username)
        return new_access, new_refresh

    # ==========================================
    # 获取当前用户
    # ==========================================
    @staticmethod
    async def get_current_user(db: AsyncSession, user_id: int) -> SysUser:
        """根据 ID 获取用户信息"""
        result = await db.execute(select(SysUser).where(SysUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")
        if user.status != 1:
            raise UnauthorizedException("账号已被禁用")
        return user

    # ==========================================
    # 修改密码
    # ==========================================
    @staticmethod
    async def change_password(
        db: AsyncSession, user_id: int, old_password: str, new_password: str
    ) -> None:
        """修改密码: 校验旧密码 → 哈希新密码 → 更新"""
        result = await db.execute(select(SysUser).where(SysUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")

        # 校验旧密码
        if not verify_password(old_password, user.password_hash):
            raise BadRequestException("旧密码错误")

        # 更新新密码
        user.password_hash = hash_password(new_password)
        await db.commit()
        logger.info(f"[Auth] 用户修改密码: {user.username}")

    # ==========================================
    # 更新个人信息
    # ==========================================
    @staticmethod
    async def update_profile(
        db: AsyncSession, user_id: int, req: ProfileUpdateRequest
    ) -> SysUser:
        """更新当前用户的个人信息"""
        result = await db.execute(select(SysUser).where(SysUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("用户不存在")

        if req.email is not None:
            user.email = req.email
        if req.phone is not None:
            user.phone = req.phone
        if req.real_name is not None:
            user.real_name = req.real_name

        await db.commit()
        await db.refresh(user)
        logger.info(f"[Auth] 用户更新个人信息: {user.username}")
        return user

    # ==========================================
    # 辅助方法 — ORM → Pydantic
    # ==========================================
    @staticmethod
    def user_to_info(user: SysUser) -> UserInfo:
        """SysUser ORM 对象 → UserInfo Pydantic Schema"""
        return UserInfo.model_validate(user)
