"""
提示词模板路由 — /api/v1/templates
模板 CRUD / 分类绑定解绑 / 按分类筛选 / 热门模板 / 变量渲染

规则:
- 系统预置模板 is_system=1 接口禁止删除 (403)
- 新增/编辑/删除/绑定/解绑均埋点操作日志
- 模板变量仅 {{question}}/{{context}}, 渲染接口供测试与 Phase 5 复用
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import SysUser
from app.schemas.common import PageResponse
from app.schemas.template import (
    TemplateBindRequest,
    TemplateCreate,
    TemplateInfo,
    TemplateQuery,
    TemplateRenderRequest,
    TemplateUpdate,
)
from app.services.log_service import LogService
from app.services.template_service import TemplateService
from app.utils.response import success

router = APIRouter()

# 操作日志模块名
_LOG_MODULE = "template"


# ==========================================
# GET /templates/ — 模板分页列表
# ==========================================
@router.get("/", summary="模板分页列表")
async def list_templates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=None, description="搜索关键词（名称/描述/标签）"),
    category_id: int = Query(
        default=None, description="分类过滤（绑定该分类或默认分类为该分类）"
    ),
    is_system: int = Query(
        default=None, ge=0, le=1, description="类型过滤: 1=系统 0=自定义"
    ),
    tag: str = Query(default=None, description="标签过滤"),
    status: int = Query(default=None, ge=0, le=1, description="状态过滤"),
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """模板列表 (分页 + 筛选)"""
    query = TemplateQuery(
        page=page,
        page_size=page_size,
        keyword=keyword,
        category_id=category_id,
        is_system=is_system,
        tag=tag,
        status=status,
    )
    items, total = await TemplateService.get_list(db, query)

    return success(
        data=PageResponse.from_list(
            items=[item.model_dump() for item in items],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    )


# ==========================================
# GET /templates/popular — 热门模板 (DESIGN.md 6.5, 注意: 必须注册在 /{template_id} 之前)
# ==========================================
@router.get("/popular", summary="热门模板")
async def popular_templates(
    limit: int = Query(default=10, ge=1, le=50),
    is_system: int = Query(
        default=None, ge=0, le=1, description="类型过滤: 1=系统 0=自定义"
    ),
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """热门模板 — 按使用次数倒序 (仅启用状态)"""
    items = await TemplateService.get_hot(db, limit=limit, is_system=is_system)
    return success(data=[item.model_dump() for item in items])


# ==========================================
# GET /templates/by-category/{category_id} — 按分类获取模板 (DESIGN.md 6.5)
# ==========================================
@router.get("/by-category/{category_id}", summary="按分类获取模板")
async def templates_by_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """按分类获取可用模板 (绑定该分类优先, 仅启用状态; Phase 5 问答自动匹配用)"""
    items = await TemplateService.get_by_category(db, category_id)
    return success(data=[item.model_dump() for item in items])


# ==========================================
# GET /templates/{id} — 模板详情
# ==========================================
@router.get("/{template_id}", summary="模板详情")
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """模板详情 (含完整内容 + 变量定义 + 绑定分类)"""
    info = await TemplateService.get_detail(db, template_id)
    return success(data=info.model_dump())


# ==========================================
# POST /templates/ — 创建模板
# ==========================================
@router.post("/", summary="创建模板")
async def create_template(
    req: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """创建用户自定义模板 (变量仅支持 {{question}}/{{context}})"""
    template = await TemplateService.create(db, req, user)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="create_template",
        module=_LOG_MODULE,
        target_type="template",
        target_id=str(template.id),
        detail={"name": template.name, "category_id": template.category_id},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=TemplateInfo.model_validate(template).model_dump(),
        msg="模板创建成功",
    )


# ==========================================
# PUT /templates/{id} — 更新模板
# ==========================================
@router.put("/{template_id}", summary="更新模板")
async def update_template(
    template_id: int,
    req: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """更新模板信息 (仅更新传入字段)"""
    await TemplateService.update(db, template_id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="update_template",
        module=_LOG_MODULE,
        target_type="template",
        target_id=str(template_id),
        detail={"updated_fields": list(req.model_dump(exclude_unset=True).keys())},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    info = await TemplateService.get_detail(db, template_id)
    return success(data=info.model_dump(), msg="模板更新成功")


# ==========================================
# DELETE /templates/{id} — 删除模板
# ==========================================
@router.delete("/{template_id}", summary="删除模板")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """删除模板 (系统预置模板 is_system=1 禁止删除)"""
    template = await TemplateService.delete(db, template_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="delete_template",
        module=_LOG_MODULE,
        target_type="template",
        target_id=str(template_id),
        detail={"name": template.name},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg=f"模板 '{template.name}' 已删除")


# ==========================================
# POST /templates/{id}/categories — 批量绑定分类 (追加)
# ==========================================
@router.post("/{template_id}/categories", summary="绑定知识库分类")
async def bind_template_categories(
    template_id: int,
    req: TemplateBindRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """批量绑定分类 (追加语义, 重复绑定自动忽略)"""
    category_ids = await TemplateService.bind_categories(db, template_id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="bind_template_categories",
        module=_LOG_MODULE,
        target_type="template",
        target_id=str(template_id),
        detail={"category_ids": category_ids},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data={"template_id": template_id, "category_ids": category_ids},
        msg="分类绑定成功",
    )


# ==========================================
# PUT /templates/{id}/categories — 设置分类 (整体替换)
# ==========================================
@router.put("/{template_id}/categories", summary="设置知识库分类")
async def set_template_categories(
    template_id: int,
    req: TemplateBindRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """设置分类绑定 (整体替换, 空列表=清空全部绑定)"""
    category_ids = await TemplateService.set_categories(db, template_id, req)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="set_template_categories",
        module=_LOG_MODULE,
        target_type="template",
        target_id=str(template_id),
        detail={"category_ids": category_ids},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data={"template_id": template_id, "category_ids": category_ids},
        msg="分类绑定已更新",
    )


# ==========================================
# DELETE /templates/{id}/categories/{category_id} — 解绑单个分类
# ==========================================
@router.delete("/{template_id}/categories/{category_id}", summary="解绑知识库分类")
async def unbind_template_category(
    template_id: int,
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """解绑单个分类 (幂等, 未绑定时不报错)"""
    await TemplateService.unbind_category(db, template_id, category_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="unbind_template_category",
        module=_LOG_MODULE,
        target_type="template",
        target_id=str(template_id),
        detail={"category_id": category_id},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg="分类已解绑")


# ==========================================
# POST /templates/{id}/render — 模板渲染 (预览/测试)
# ==========================================
@router.post("/{template_id}/render", summary="模板渲染")
async def render_template(
    template_id: int,
    req: TemplateRenderRequest,
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """渲染模板 — 填充 {{question}}/{{context}} 生成完整 Prompt (预览测试用)"""
    result = await TemplateService.render(db, template_id, req)
    return success(data=result.model_dump(), msg="渲染成功")
