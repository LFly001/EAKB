"""
管理后台 Pydantic Schema (Phase 7)
看板统计数据 / 操作日志 / 系统配置 — 均仅 admin 角色可访问
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ==========================================
# 数据看板 (DESIGN 7.1)
# ==========================================
class DashboardStats(BaseModel):
    """看板聚合统计 — 数字展示"""

    user_count: int = Field(default=0, description="用户总数 (含禁用)")
    document_count: int = Field(default=0, description="文档总量 (不含软删)")
    conversation_count: int = Field(default=0, description="问答会话总量")
    today_question_count: int = Field(
        default=0, description="今日问答量 (用户提问消息数)"
    )
    vectorized_document_count: int = Field(default=0, description="向量化完成文档数")
    today_operation_count: int = Field(default=0, description="今日操作日志数")


# ==========================================
# 操作日志 (DESIGN 4.1.9 / 7.3)
# ==========================================
class OperationLogInfo(BaseModel):
    """操作日志出参"""

    id: int
    user_id: int | None = None
    username: str | None = None
    action: str
    module: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    detail: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    status: str = "success"
    error_info: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ==========================================
# 系统配置 (DESIGN 4.1.10 / 7.4)
# ==========================================
class ConfigItem(BaseModel):
    """系统配置项出参"""

    id: int
    config_key: str
    config_value: str | None = None
    config_type: str = "string"
    description: str | None = None
    updated_by: int | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConfigUpdateRequest(BaseModel):
    """更新配置值 (PUT /admin/configs/{key})"""

    config_value: str = Field(description="新配置值 (字符串形式, 按 config_type 校验)")
