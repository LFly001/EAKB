"""
全局依赖注入
提供: 数据库会话、当前用户鉴权、分页参数、角色校验
"""

import hmac
from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.security import decode_access_token
from app.models.user import SysUser
from app.services.config_service import ConfigService
from app.utils.exceptions import UnauthorizedException

# ==========================================
# 数据库会话依赖
# ==========================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库异步会话 (每个请求一个会话，异常自动回滚)"""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==========================================
# JWT 鉴权依赖
# ==========================================

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> SysUser:
    """
    从 JWT Token 解析并返回当前登录用户 ORM 对象。
    未登录 / Token 无效 → 401
    用户被禁用 → 401
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(status_code=401, detail="Token 缺少用户标识")

    # 从数据库查询用户
    result = await db.execute(select(SysUser).where(SysUser.id == int(user_id_str)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    if user.status != 1:
        raise HTTPException(status_code=401, detail="账号已被禁用")

    return user


async def require_admin(
    current_user: SysUser = Depends(get_current_user),
) -> SysUser:
    """管理员权限校验 — 非 admin 角色 → 403"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# ==========================================
# 内部服务密钥鉴权 (POST /api/v1/rag/search, 供 ESD 知识 agent 调用)
# ==========================================


async def require_internal_key(
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    内部服务密钥校验 — DESIGN 8.1。

    X-Internal-Key 头与 sys_config internal_api_key 比较,
    hmac.compare_digest 防时序攻击; 缺头 / 密钥未配置 / 不匹配 → 40100 (fail-closed)。
    """
    expected = await ConfigService.get_value(db, "internal_api_key", None)
    if (
        not x_internal_key
        or not expected
        or not hmac.compare_digest(x_internal_key, str(expected))
    ):
        raise UnauthorizedException("内部服务密钥无效")


# ==========================================
# 分页参数依赖
# ==========================================


async def pagination_params(
    page: int = 1,
    page_size: int = 20,
):
    """通用分页参数，可从查询参数直接注入"""
    page = max(page, 1)
    if page_size < 1:
        page_size = 20
    page_size = min(page_size, 100)
    return {"page": page, "page_size": page_size}
