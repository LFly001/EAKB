"""
知识库分类路由 — /api/v1/categories
分类树 / 创建 / 更新 / 拖拽排序 / 删除 (全操作埋点操作日志)
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import SysUser
from app.schemas.category import (
    CategoryCreate,
    CategoryInfo,
    CategoryMoveRequest,
    CategoryUpdate,
)
from app.services.category_service import CategoryService
from app.services.log_service import LogService
from app.utils.response import success

router = APIRouter()

# 操作日志模块名
_LOG_MODULE = "knowledge"


# ==========================================
# GET /categories/ — 分类树
# ==========================================
@router.get("/", summary="分类树")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """全量分类树 (递归 children + 文档数量)"""
    tree = await CategoryService.get_tree(db)
    return success(data=[node.model_dump() for node in tree])


# ==========================================
# POST /categories/ — 创建分类
# ==========================================
@router.post("/", summary="创建分类")
async def create_category(
    req: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """创建分类 (支持指定父分类)"""
    category = await CategoryService.create(db, req, user)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="create_category",
        module=_LOG_MODULE,
        target_type="category",
        target_id=str(category.id),
        detail={"name": category.name, "parent_id": category.parent_id},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=CategoryInfo.model_validate(category).model_dump(),
        msg="分类创建成功",
    )


# ==========================================
# PUT /categories/{id} — 更新分类
# ==========================================
@router.put("/{category_id}", summary="更新分类")
async def update_category(
    category_id: int,
    req: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """更新分类信息 (仅更新传入字段)"""
    category = await CategoryService.update(db, category_id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="update_category",
        module=_LOG_MODULE,
        target_type="category",
        target_id=str(category_id),
        detail={"updated_fields": list(req.model_dump(exclude_unset=True).keys())},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=CategoryInfo.model_validate(category).model_dump(),
        msg="分类更新成功",
    )


# ==========================================
# PUT /categories/{id}/move — 拖拽排序
# ==========================================
@router.put("/{category_id}/move", summary="拖拽排序")
async def move_category(
    category_id: int,
    req: CategoryMoveRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """变更父分类 / 同级排序值 (前端树拖拽调用)"""
    category = await CategoryService.move(db, category_id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="move_category",
        module=_LOG_MODULE,
        target_type="category",
        target_id=str(category_id),
        detail={"parent_id": category.parent_id, "sort_order": category.sort_order},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=CategoryInfo.model_validate(category).model_dump(),
        msg="分类排序已更新",
    )


# ==========================================
# DELETE /categories/{id} — 删除分类
# ==========================================
@router.delete("/{category_id}", summary="删除分类")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """删除分类 (存在子分类或文档时拒绝)"""
    category = await CategoryService.delete(db, category_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="delete_category",
        module=_LOG_MODULE,
        target_type="category",
        target_id=str(category_id),
        detail={"name": category.name},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg=f"分类 '{category.name}' 已删除")
