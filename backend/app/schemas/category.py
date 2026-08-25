"""
知识库分类 Pydantic 模型
入参校验 (Create/Update/Move) + 出参序列化 (CategoryInfo/CategoryTreeNode)
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ==========================================
# 入参 — 创建 / 更新 / 移动
# ==========================================


class CategoryCreate(BaseModel):
    """创建分类请求"""

    name: str = Field(min_length=1, max_length=100, description="分类名称")
    parent_id: int | None = Field(default=None, description="父分类ID（None=一级分类）")
    description: str | None = Field(
        default=None, max_length=2000, description="分类描述"
    )
    icon: str | None = Field(
        default=None, max_length=255, description="图标（Element Plus 图标名）"
    )
    sort_order: int = Field(default=0, ge=0, description="同级排序值")


class CategoryUpdate(BaseModel):
    """更新分类请求 (仅更新传入字段)"""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="分类名称"
    )
    parent_id: int | None = Field(default=None, description="父分类ID")
    description: str | None = Field(
        default=None, max_length=2000, description="分类描述"
    )
    icon: str | None = Field(default=None, max_length=255, description="图标")
    sort_order: int | None = Field(default=None, ge=0, description="排序值")
    status: int | None = Field(
        default=None, ge=0, le=1, description="状态: 1=启用 0=禁用"
    )


class CategoryMoveRequest(BaseModel):
    """拖拽排序请求 — 变更父级 / 同级顺序"""

    parent_id: int | None = Field(
        default=None, description="新父分类ID（None=移动到一级分类）"
    )
    sort_order: int | None = Field(default=None, ge=0, description="新排序值")


# ==========================================
# 出参 — 分类信息 / 树节点
# ==========================================


class CategoryInfo(BaseModel):
    """分类基础信息"""

    id: int
    name: str
    parent_id: int | None = None
    description: str | None = None
    icon: str | None = None
    sort_order: int = 0
    status: int = 1
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CategoryTreeNode(CategoryInfo):
    """分类树节点 — 递归包含子分类 + 文档数量统计"""

    document_count: int = Field(default=0, description="分类下文档数（不含子分类）")
    children: list["CategoryTreeNode"] = Field(
        default_factory=list, description="子分类列表"
    )
