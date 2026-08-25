"""
用户管理路由 (管理员) — /api/v1/users
用户列表 / 详情 / 创建 / 更新 / 启用禁用 / 删除
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_admin
from app.models.user import SysUser
from app.schemas.user import (
    UserBatchRequest,
    UserCreateRequest,
    UserInfo,
    UserQuery,
    UserStatusRequest,
    UserUpdateRequest,
)
from app.services.log_service import LogService
from app.services.user_service import UserService
from app.utils.response import fail, success

router = APIRouter()


# ==========================================
# POST /users/batch — 批量启用/禁用/删除 (管理员, Phase 7)
# ==========================================
@router.post("/batch", summary="批量用户操作")
async def batch_users(
    req: UserBatchRequest,
    db: AsyncSession = Depends(get_db),
    admin: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """批量操作: enable/disable/delete (Phase 8: 一次查询+一次提交, 不存在的 ID 跳过并返回)"""
    if req.action not in ("enable", "disable", "delete"):
        return fail(40000, "action 仅支持 enable / disable / delete")

    # 去重 + 禁止操作自己的账号 (删除/禁用自己会导致会话失效)
    user_ids = list(dict.fromkeys(req.user_ids))
    if admin.id in user_ids:
        return fail(40000, "不能批量操作自己的账号")

    processed, missing = await UserService.batch_operate(db, req.action, user_ids)

    action_text = (
        "启用"
        if req.action == "enable"
        else "禁用"
        if req.action == "disable"
        else "删除"
    )
    await LogService.create(
        db,
        user_id=admin.id,
        username=admin.username,
        action=f"batch_{req.action}_user",
        module="user",
        target_type="user",
        # target_id 列宽 100, 截断防超长; 完整名单在 detail.users
        target_id=",".join(map(str, user_ids))[:100],
        detail={"count": len(processed), "users": processed, "skipped_ids": missing},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    msg = f"批量{action_text}完成: {len(processed)} 个用户"
    if missing:
        msg += f"，{len(missing)} 个用户不存在已跳过"
    return success(
        data={"count": len(processed), "users": processed, "skipped_ids": missing},
        msg=msg,
    )


# ==========================================
# GET /users/ — 用户列表 (管理员)
# ==========================================
@router.get("/", summary="用户列表")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=None, description="搜索关键词"),
    role: str = Query(default=None, description="角色过滤"),
    status: int = Query(default=None, description="状态过滤"),
    db: AsyncSession = Depends(get_db),
    _admin: SysUser = Depends(require_admin),
):
    """管理员查询用户列表 (分页 + 筛选)"""
    query = UserQuery(
        page=page,
        page_size=page_size,
        keyword=keyword,
        role=role,
        status=status,
    )
    items, total = await UserService.get_list(db, query)

    from app.schemas.common import PageResponse

    return success(
        data=PageResponse.from_list(
            items=[UserInfo.model_validate(u).model_dump() for u in items],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    )


# ==========================================
# GET /users/{user_id} — 用户详情 (管理员)
# ==========================================
@router.get("/{user_id}", summary="用户详情")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: SysUser = Depends(require_admin),
):
    """管理员查看用户详情"""
    user = await UserService.get_by_id(db, user_id)
    return success(data=UserInfo.model_validate(user).model_dump())


# ==========================================
# POST /users/ — 创建用户 (管理员)
# ==========================================
@router.post("/", summary="创建用户")
async def create_user(
    req: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """管理员创建新用户"""
    user = await UserService.create(db, req)

    await LogService.create(
        db,
        user_id=admin.id,
        username=admin.username,
        action="create_user",
        module="user",
        target_type="user",
        target_id=str(user.id),
        detail={"created_user": user.username, "role": user.role},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=UserInfo.model_validate(user).model_dump(),
        msg="用户创建成功",
    )


# ==========================================
# PUT /users/{user_id} — 更新用户 (管理员)
# ==========================================
@router.put("/{user_id}", summary="更新用户信息")
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """管理员更新用户信息 (角色、状态、部门等)"""
    user = await UserService.update(db, user_id, req)

    await LogService.create(
        db,
        user_id=admin.id,
        username=admin.username,
        action="update_user",
        module="user",
        target_type="user",
        target_id=str(user_id),
        detail={"updated_fields": list(req.model_dump(exclude_unset=True).keys())},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=UserInfo.model_validate(user).model_dump(),
        msg="用户信息更新成功",
    )


# ==========================================
# PUT /users/{user_id}/status — 启用/禁用 (管理员)
# ==========================================
@router.put("/{user_id}/status", summary="启用/禁用用户")
async def toggle_user_status(
    user_id: int,
    req: UserStatusRequest,
    db: AsyncSession = Depends(get_db),
    admin: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """管理员启用或禁用用户"""
    user = await UserService.toggle_status(db, user_id, req.status)

    await LogService.create(
        db,
        user_id=admin.id,
        username=admin.username,
        action="toggle_user_status",
        module="user",
        target_type="user",
        target_id=str(user_id),
        detail={"new_status": req.status},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    status_text = "启用" if req.status == 1 else "禁用"
    return success(
        data=UserInfo.model_validate(user).model_dump(),
        msg=f"用户已{status_text}",
    )


# ==========================================
# DELETE /users/{user_id} — 删除用户 (管理员)
# ==========================================
@router.delete("/{user_id}", summary="删除用户")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """管理员删除用户 (物理删除，请慎用)"""
    # 禁止删除自己
    if user_id == admin.id:
        return fail(40000, "不能删除自己的账号")

    user = await UserService.get_by_id(db, user_id)
    await UserService.delete(db, user_id)

    await LogService.create(
        db,
        user_id=admin.id,
        username=admin.username,
        action="delete_user",
        module="user",
        target_type="user",
        target_id=str(user_id),
        detail={"deleted_user": user.username},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg=f"用户 '{user.username}' 已删除")
