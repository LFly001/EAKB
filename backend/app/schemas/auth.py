"""
认证模块 Pydantic Schema
注册 / 登录 / Token / 修改密码
"""

import re

from pydantic import BaseModel, Field, field_validator


# ==========================================
# 注册
# ==========================================
class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(
        min_length=3,
        max_length=50,
        description="用户名（工号）",
        examples=["zhangsan"],
    )
    password: str = Field(
        min_length=6,
        max_length=128,
        description="密码 (6-128位)",
        examples=["Abc123456"],
    )
    confirm_password: str = Field(description="确认密码")
    email: str | None = Field(default=None, max_length=100, description="邮箱")
    phone: str | None = Field(default=None, max_length=20, description="手机号")
    real_name: str | None = Field(default=None, max_length=50, description="真实姓名")

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("两次密码输入不一致")
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v


# ==========================================
# 登录
# ==========================================
class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(min_length=1, description="用户名")
    password: str = Field(min_length=1, description="密码")


# ==========================================
# Token 响应
# ==========================================
class TokenResponse(BaseModel):
    """JWT Token 响应"""

    access_token: str = Field(description="访问令牌 (短期)")
    refresh_token: str = Field(description="刷新令牌 (长期)")
    token_type: str = Field(default="bearer", description="Token 类型")


class LoginResponse(BaseModel):
    """登录完整响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserInfo"  # 前向引用


# ==========================================
# 修改密码
# ==========================================
class ChangePasswordRequest(BaseModel):
    """修改密码请求"""

    old_password: str = Field(min_length=1, description="旧密码")
    new_password: str = Field(
        min_length=6, max_length=128, description="新密码 (6-128位)"
    )
    confirm_password: str = Field(description="确认新密码")

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("两次新密码输入不一致")
        return v


# ==========================================
# 刷新 Token
# ==========================================
class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""

    refresh_token: str = Field(min_length=1, description="Refresh Token")


# ==========================================
# 用户信息 (前向引用延迟解析)
# ==========================================
from app.schemas.user import UserInfo

LoginResponse.model_rebuild()
