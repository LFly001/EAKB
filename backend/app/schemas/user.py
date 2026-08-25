"""
用户管理 Pydantic Schema
用户信息 CRUD、列表查询、管理员操作
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ==========================================
# 用户信息 (响应用)
# ==========================================
class UserInfo(BaseModel):
    """用户信息 — API 出参 (不含密码)"""

    id: int
    username: str
    email: str | None = None
    phone: str | None = None
    real_name: str | None = None
    department: str | None = None
    position: str | None = None
    avatar_url: str | None = None
    role: str
    status: int
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ==========================================
# 用户列表查询
# ==========================================
class UserQuery(BaseModel):
    """用户列表查询参数"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(
        default=None, description="搜索关键词 (用户名/姓名/部门)"
    )
    role: str | None = Field(default=None, description="角色过滤: admin/employee")
    status: int | None = Field(default=None, description="状态过滤: 1=启用 0=禁用")


# ==========================================
# 管理员 — 创建用户
# ==========================================
class UserCreateRequest(BaseModel):
    """管理员创建用户"""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    real_name: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)
    role: str = Field(default="employee", description="角色: admin/employee")
    status: int = Field(default=1, description="状态: 1=启用 0=禁用")


# ==========================================
# 管理员 — 更新用户
# ==========================================
class UserUpdateRequest(BaseModel):
    """更新用户信息 (管理员)"""

    email: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    real_name: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, description="角色")
    status: int | None = Field(default=None, description="状态")


# ==========================================
# 当前用户 — 更新个人信息
# ==========================================
class ProfileUpdateRequest(BaseModel):
    """当前用户更新个人信息"""

    email: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    real_name: str | None = Field(default=None, max_length=50)


# ==========================================
# 用户状态切换
# ==========================================
class UserStatusRequest(BaseModel):
    """启用/禁用用户"""

    status: int = Field(ge=0, le=1, description="1=启用 0=禁用")


# ==========================================
# 批量用户操作 (Phase 7)
# ==========================================
class UserBatchRequest(BaseModel):
    """批量启用 / 禁用 / 删除用户"""

    user_ids: list[int] = Field(
        min_length=1, max_length=100, description="目标用户ID列表"
    )
    action: str = Field(description="批量操作: enable/disable/delete")
