"""
认证模块路由 — /api/v1/auth
注册 / 登录 / 登出 / 个人信息 / 修改密码 / 刷新Token
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import SysUser
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)
from app.schemas.user import ProfileUpdateRequest, UserInfo
from app.services.auth_service import AuthService
from app.services.log_service import LogService
from app.utils.response import success

router = APIRouter()


# ==========================================
# POST /auth/register — 用户注册
# ==========================================
@router.post("/register", summary="用户注册")
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    http_req: Request = None,
):
    """新用户注册，默认为 employee 角色"""
    user = await AuthService.register(db, req)

    # 操作日志
    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="register",
        module="auth",
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=UserInfo.model_validate(user).model_dump(),
        msg="注册成功",
    )


# ==========================================
# POST /auth/login — 登录
# ==========================================
@router.post("/login", summary="用户登录")
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
    http_req: Request = None,
):
    """用户名 + 密码登录，返回 JWT Token"""
    access_token, refresh_token, user = await AuthService.login(
        db, req.username, req.password
    )

    # 操作日志
    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="login",
        module="auth",
        target_type="user",
        target_id=str(user.id),
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": UserInfo.model_validate(user).model_dump(),
        },
        msg="登录成功",
    )


# ==========================================
# POST /auth/refresh — 刷新 Token
# ==========================================
@router.post("/refresh", summary="刷新 Token")
async def refresh_token(
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """用 Refresh Token 换取新的 Access Token + Refresh Token"""
    access_token, refresh_token = await AuthService.refresh_access_token(
        db, req.refresh_token
    )
    return success(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
        msg="Token 刷新成功",
    )


# ==========================================
# GET /auth/me — 获取当前用户信息
# ==========================================
@router.get("/me", summary="获取当前用户信息")
async def get_me(
    current_user: SysUser = Depends(get_current_user),
):
    """获取当前登录用户信息"""
    return success(
        data=UserInfo.model_validate(current_user).model_dump(),
    )


# ==========================================
# PUT /auth/me — 更新个人信息
# ==========================================
@router.put("/me", summary="更新个人信息")
async def update_me(
    req: ProfileUpdateRequest,
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    http_req: Request = None,
):
    """更新当前用户的邮箱、手机、姓名"""
    user = await AuthService.update_profile(db, current_user.id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="update_profile",
        module="auth",
        target_type="user",
        target_id=str(user.id),
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=UserInfo.model_validate(user).model_dump(),
        msg="个人信息更新成功",
    )


# ==========================================
# PUT /auth/password — 修改密码
# ==========================================
@router.put("/password", summary="修改密码")
async def change_password(
    req: ChangePasswordRequest,
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    http_req: Request = None,
):
    """修改当前用户密码 (需校验旧密码)"""
    await AuthService.change_password(
        db, current_user.id, req.old_password, req.new_password
    )

    await LogService.create(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="change_password",
        module="auth",
        target_type="user",
        target_id=str(current_user.id),
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg="密码修改成功")


# ==========================================
# POST /auth/logout — 注销
# ==========================================
@router.post("/logout", summary="注销")
async def logout(
    current_user: SysUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    http_req: Request = None,
):
    """用户注销 (前端清除 Token 即可，后端记录日志)"""
    await LogService.create(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="logout",
        module="auth",
        target_type="user",
        target_id=str(current_user.id),
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg="注销成功")
