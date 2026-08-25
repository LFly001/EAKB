"""
管理后台路由 (Phase 7) — /api/v1/admin (DESIGN 6.8)
数据看板 / 操作日志 / 系统配置 — 全部接口仅 admin 角色可访问
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_admin
from app.models.user import SysUser
from app.schemas.admin import ConfigItem, ConfigUpdateRequest, OperationLogInfo
from app.schemas.common import PageResponse
from app.services.config_service import ConfigService
from app.services.dashboard_service import DashboardService
from app.services.log_service import LogService
from app.utils.response import success

router = APIRouter()

_LOG_MODULE = "system"


# ==========================================
# GET /admin/dashboard — 数据看板统计
# ==========================================
@router.get("/dashboard", summary="看板统计数据 (admin)")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _admin: SysUser = Depends(require_admin),
):
    """聚合统计: 用户/文档/会话/今日问答/向量化/今日操作"""
    stats = await DashboardService.get_stats(db)
    return success(data=stats.model_dump())


# ==========================================
# GET /admin/logs — 操作日志分页查询 (审计, 仅查询)
# ==========================================
@router.get("/logs", summary="操作日志分页 (admin)")
async def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    username: str | None = Query(default=None, description="操作人用户名(模糊)"),
    module: str | None = Query(default=None, description="操作模块"),
    action: str | None = Query(default=None, description="操作类型"),
    status: str | None = Query(default=None, description="执行结果: success/failed"),
    start_time: datetime | None = Query(
        default=None, description="操作时间起 (ISO8601)"
    ),
    end_time: datetime | None = Query(default=None, description="操作时间止 (ISO8601)"),
    db: AsyncSession = Depends(get_db),
    _admin: SysUser = Depends(require_admin),
):
    """操作日志分页 + 多条件筛选; 仅查询, 不提供删除接口 (审计保留)"""
    items, total = await LogService.get_list(
        db,
        page=page,
        page_size=page_size,
        username=username,
        module=module,
        action=action,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    return success(
        data=PageResponse.from_list(
            items=[OperationLogInfo.model_validate(log).model_dump() for log in items],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump()
    )


# ==========================================
# GET /admin/configs — 系统配置列表
# ==========================================
@router.get("/configs", summary="系统配置列表 (admin)")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _admin: SysUser = Depends(require_admin),
):
    """全量配置项列表 (可视化表单数据源)"""
    rows = await ConfigService.list_all(db)
    return success(data=[ConfigItem.model_validate(row).model_dump() for row in rows])


# ==========================================
# PUT /admin/configs/{key} — 更新配置 (实时生效)
# ==========================================
@router.put("/configs/{key}", summary="更新系统配置 (admin)")
async def update_config(
    key: str,
    req: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: SysUser = Depends(require_admin),
    http_req: Request = None,
):
    """更新配置值; 业务读取方每次从 DB 读取, 无需重启服务"""
    before = await ConfigService.get_by_key(db, key)
    old_value = before.config_value
    row = await ConfigService.update(db, key, req.config_value, admin.id)

    await LogService.create(
        db,
        user_id=admin.id,
        username=admin.username,
        action="update_config",
        module=_LOG_MODULE,
        target_type="config",
        target_id=key,
        detail={"old_value": old_value, "new_value": req.config_value},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=ConfigItem.model_validate(row).model_dump(),
        msg=f"配置 '{key}' 已更新, 实时生效",
    )
