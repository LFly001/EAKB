"""
提示词模板 Pydantic 模型
入参校验 (Create/Update/查询/绑定/渲染) + 出参序列化 (TemplateListItem/TemplateInfo)

模板变量规则 (CLAUDE.md 提示词模板系统):
- 仅支持 {{question}} / {{context}} 两个占位符
- variables 字段 JSON 定义变量约束 (DESIGN.md 4.1.5 固定结构)
"""

import json
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PageQuery

# ==========================================
# 变量结构 (DESIGN.md 4.1.5 variables JSON)
# ==========================================

# 模板内容中允许的占位符: 仅 {{question}} / {{context}}
_ALLOWED_PLACEHOLDERS = {"question", "context"}
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def extract_placeholders(content: str) -> list[str]:
    """提取模板内容中所有 {{xxx}} 占位符变量名 (去重, 保持出现顺序)"""
    seen: list[str] = []
    for name in _PLACEHOLDER_PATTERN.findall(content):
        if name not in seen:
            seen.append(name)
    return seen


def validate_template_content(content: str) -> None:
    """
    校验模板内容占位符合法性:
    - 仅允许 {{question}} / {{context}}
    - 非法变量 → ValueError (由 schema/service 捕获转业务异常)
    """
    for name in extract_placeholders(content):
        if name not in _ALLOWED_PLACEHOLDERS:
            allowed = ", ".join(f"{{{{{v}}}}}" for v in sorted(_ALLOWED_PLACEHOLDERS))
            raise ValueError(
                f"模板内容包含不支持的变量 {{{{ {name} }}}}，仅允许 {allowed}"
            )


class TemplateVariable(BaseModel):
    """单个模板变量定义"""

    type: str = Field(default="string", description="变量类型")
    description: str = Field(default="", max_length=200, description="变量说明")
    required: bool = Field(default=True, description="是否必填")
    default: str = Field(default="", description="默认值")

    model_config = ConfigDict(extra="forbid")


class TemplateVariables(BaseModel):
    """模板变量集合 — 固定 question/context 两项"""

    question: TemplateVariable = Field(
        default_factory=TemplateVariable, description="用户问题变量"
    )
    context: TemplateVariable = Field(
        default_factory=TemplateVariable, description="知识库上下文变量"
    )

    model_config = ConfigDict(extra="forbid")


def default_variables() -> TemplateVariables:
    """标准变量结构 (DESIGN.md 4.1.5)"""
    return TemplateVariables(
        question=TemplateVariable(
            type="string", description="用户问题", required=True, default=""
        ),
        context=TemplateVariable(
            type="string", description="检索到的知识库上下文", required=True, default=""
        ),
    )


def default_variables_json() -> dict:
    """标准变量结构的 JSON dict (直接入库)"""
    return json.loads(default_variables().model_dump_json())


# ==========================================
# 入参 — 创建 / 更新
# ==========================================


class TemplateCreate(BaseModel):
    """创建模板请求 (占位符合法性在 Service 层校验, 保证错误信息友好)"""

    name: str = Field(min_length=1, max_length=200, description="模版名称")
    description: str | None = Field(
        default=None, max_length=2000, description="模版描述"
    )
    category_id: int | None = Field(default=None, description="默认关联知识库分类ID")
    template_content: str = Field(
        min_length=1, description="模版内容（含 {{question}}/{{context}} 占位符）"
    )
    variables: TemplateVariables | None = Field(
        default=None, description="变量定义（缺省使用标准结构）"
    )
    tags: str | None = Field(
        default=None, max_length=500, description="标签（逗号分隔）"
    )
    status: int | None = Field(default=1, ge=0, le=1, description="状态: 1=启用 0=禁用")


class TemplateUpdate(BaseModel):
    """更新模板请求 (仅更新传入字段, 占位符合法性在 Service 层校验)"""

    name: str | None = Field(
        default=None, min_length=1, max_length=200, description="模版名称"
    )
    description: str | None = Field(
        default=None, max_length=2000, description="模版描述"
    )
    category_id: int | None = Field(default=None, description="默认关联知识库分类ID")
    template_content: str | None = Field(
        default=None, min_length=1, description="模版内容"
    )
    variables: TemplateVariables | None = Field(default=None, description="变量定义")
    tags: str | None = Field(
        default=None, max_length=500, description="标签（逗号分隔）"
    )
    status: int | None = Field(
        default=None, ge=0, le=1, description="状态: 1=启用 0=禁用"
    )


# ==========================================
# 入参 — 查询 / 绑定 / 渲染
# ==========================================


class TemplateQuery(PageQuery):
    """模板分页列表查询参数"""

    category_id: int | None = Field(
        default=None, description="分类过滤（模板绑定该分类或默认分类为该分类）"
    )
    is_system: int | None = Field(
        default=None, ge=0, le=1, description="类型过滤: 1=系统 0=自定义"
    )
    tag: str | None = Field(default=None, max_length=100, description="标签过滤")
    status: int | None = Field(default=None, ge=0, le=1, description="状态过滤")


class TemplateBindRequest(BaseModel):
    """绑定/设置分类请求"""

    category_ids: list[int] = Field(
        default_factory=list, description="知识库分类ID列表（空列表=清空绑定）"
    )


class TemplateRenderRequest(BaseModel):
    """模板渲染请求 — 填充 {{question}}/{{context}} 预览或测试"""

    question: str = Field(min_length=1, description="用户问题")
    context: str = Field(default="", description="检索上下文（可留空测试渲染）")


# ==========================================
# 出参 — 列表项 / 详情 / 渲染结果
# ==========================================


class TemplateListItem(BaseModel):
    """模板列表项 (不含 template_content, 减少列表负载)"""

    id: int
    name: str
    description: str | None = None
    category_id: int | None = None
    category_name: str | None = Field(default=None, description="默认分类名称（冗余）")
    tags: str | None = None
    usage_count: int = 0
    is_system: int = 0
    status: int = 1
    created_by: int | None = None
    creator_name: str | None = Field(default=None, description="创建人用户名（冗余）")
    category_ids: list[int] = Field(
        default_factory=list, description="已绑定的分类ID列表"
    )
    category_names: list[str] = Field(
        default_factory=list, description="已绑定的分类名称列表"
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TemplateInfo(TemplateListItem):
    """模板详情 — 在列表项基础上携带完整内容与变量定义"""

    template_content: str
    variables: TemplateVariables = Field(
        default_factory=default_variables, description="变量定义"
    )


class TemplateRenderResult(BaseModel):
    """模板渲染结果"""

    template_id: int
    template_name: str
    variables: dict = Field(default_factory=dict, description="实际使用的变量值")
    rendered: str = Field(description="渲染后的完整 Prompt")
