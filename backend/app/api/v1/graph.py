"""
知识图谱路由 — /api/v1/graph (DESIGN 6.7)
实体列表/详情、图谱搜索/画布全景、图谱构建 (admin)
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import SysUser
from app.schemas.common import PageResponse
from app.schemas.graph import GraphBuildRequest
from app.services.graph_service import GraphService
from app.services.log_service import LogService
from app.utils.response import success

router = APIRouter()

_LOG_MODULE = "graph"


# ==========================================
# GET /graph/entities/ — 实体分页列表
# ==========================================
@router.get("/entities/", summary="实体分页列表")
async def list_entities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, description="实体名/别名关键词"),
    entity_type: str | None = Query(
        default=None, alias="type", description="实体类型过滤"
    ),
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """实体列表 (name/aliases 关键词 + 类型过滤, 按提及次数降序)"""
    items, total = await GraphService.list_entities(
        db, page, page_size, keyword, entity_type
    )
    return success(
        data=PageResponse.from_list(
            items=[item.model_dump() for item in items],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump()
    )


# ==========================================
# GET /graph/entities/{name} — 实体详情
# ==========================================
@router.get("/entities/{name}", summary="实体详情")
async def get_entity(
    name: str,
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """实体详情: 属性 + RELATED_TO 关联实体 + 提及文档"""
    detail = await GraphService.get_entity_detail(db, name)
    return success(data=detail.model_dump())


# ==========================================
# GET /graph/search — 图谱搜索 / 画布全景
# ==========================================
@router.get("/search", summary="图谱搜索/画布全景")
async def search_graph(
    keyword: str | None = Query(
        default=None, description="空=画布全景, 非空=匹配实体子图"
    ),
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """返回 nodes/edges/stats, 前端可视化与搜索共用此接口"""
    data = await GraphService.search_graph(db, keyword)
    return success(data=data.model_dump())


# ==========================================
# POST /graph/build — 触发图谱构建 (admin)
# ==========================================
@router.post("/build", summary="重建知识图谱 (admin)")
async def build_graph(
    background_tasks: BackgroundTasks,
    req: GraphBuildRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """全量重建 (body 空/缺省) 或单文档重建; 任务后台异步执行, 立即返回"""
    document_id = req.document_id if req else None
    if document_id is not None:
        # 提前校验返回 404/400, 后台任务内再次兜底
        await GraphService.validate_build_request(db, document_id)
    background_tasks.add_task(GraphService.run_build_pipeline, document_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="build_graph",
        module=_LOG_MODULE,
        target_type="document" if document_id else "graph",
        target_id=str(document_id) if document_id else "all",
        detail={
            "scope": "single" if document_id else "full",
            "document_id": document_id,
        },
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )
    return success(
        msg=f"图谱重建任务已下发 ({f'文档 {document_id}' if document_id else '全量'})"
    )
