"""phase4 提示词模板表 + 系统预置模板种子

Revision ID: 20260815_0003
Revises: 20260813_0002
Create Date: 2026-08-15

Phase 4 建表:
- pt_template           提示词模板主表 (DESIGN.md 4.1.5)
- pt_template_category  模板-知识库分类关联表 (DESIGN.md 4.1.6, UNIQUE 防重复绑定)
并写入 3 个系统预置模板 (is_system=1, created_by=NULL, 不可删除)
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260815_0003"
down_revision = "20260813_0002"
branch_labels = None
depends_on = None


# 系统预置模板变量结构 (DESIGN.md 4.1.5 variables JSON 定义)
_DEFAULT_VARIABLES = {
    "question": {
        "type": "string",
        "description": "用户问题",
        "required": True,
        "default": "",
    },
    "context": {
        "type": "string",
        "description": "检索到的知识库上下文",
        "required": True,
        "default": "",
    },
}

# 系统预置模板种子数据
_SYSTEM_TEMPLATES = [
    {
        "name": "通用知识问答（默认）",
        "description": "系统预置默认模板：基于知识库上下文严谨作答，无匹配内容时如实说明",
        "template_content": (
            "你是一名专业的企业知识库智能助手，请根据以下知识库内容回答用户问题。\n\n"
            "知识库内容：\n{{context}}\n\n"
            "用户问题：{{question}}\n\n"
            "要求：\n"
            "1. 仅基于知识库内容作答，不要编造知识库中不存在的信息；\n"
            "2. 如果知识库中没有相关内容，请明确告知用户，并给出可能的查找建议；\n"
            "3. 回答使用简体中文，条理清晰、重点突出。"
        ),
        "tags": "通用",
    },
    {
        "name": "简洁精炼",
        "description": "系统预置模板：要点式简要作答，适合快速查询场景",
        "template_content": (
            "请用简洁的语言回答用户问题，仅依据提供的知识库内容。\n\n"
            "参考内容：\n{{context}}\n\n"
            "问题：{{question}}\n\n"
            "要求：直接给出要点，不超过 5 条；知识库无相关内容时说明未找到。"
        ),
        "tags": "简洁",
    },
    {
        "name": "详细讲解",
        "description": "系统预置模板：先结论后分点详述，适合需要深入了解的场景",
        "template_content": (
            "你是一名企业知识库专家，请结合知识库内容对用户问题进行详细解答。\n\n"
            "参考资料：\n{{context}}\n\n"
            "用户问题：{{question}}\n\n"
            "要求：\n"
            "1. 先给出结论，再分点详细说明；\n"
            "2. 引用资料时标注来源文档标题；\n"
            "3. 知识库未覆盖的内容请明确说明，不要猜测。"
        ),
        "tags": "详细",
    },
]


def upgrade() -> None:
    # ==========================================
    # pt_template — 提示词模板主表 (DESIGN.md 4.1.5)
    # ==========================================
    op.create_table(
        "pt_template",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False, comment="模版名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="模版描述"),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            nullable=True,
            comment="默认关联知识库分类",
        ),
        sa.Column(
            "template_content",
            sa.Text(),
            nullable=False,
            comment="模版内容（含 {{question}}/{{context}} 占位符）",
        ),
        sa.Column(
            "variables",
            mysql.JSON(),
            nullable=True,
            comment="变量定义（question/context 结构）",
        ),
        sa.Column("tags", sa.String(500), nullable=True, comment="标签（逗号分隔）"),
        sa.Column(
            "usage_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="使用次数",
        ),
        sa.Column(
            "is_system",
            mysql.TINYINT(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="是否系统预置: 1=系统 0=用户自定义",
        ),
        sa.Column(
            "status",
            mysql.TINYINT(),
            nullable=False,
            server_default=sa.text("'1'"),
            comment="状态: 1=启用 0=禁用",
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            nullable=True,
            comment="创建人ID（系统模板为 NULL）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["kb_category.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_ptpl_category", "pt_template", ["category_id"])
    op.create_index("idx_ptpl_is_system", "pt_template", ["is_system"])
    op.create_index("idx_ptpl_usage", "pt_template", ["usage_count"])

    # ==========================================
    # pt_template_category — 模板-知识库分类关联表 (DESIGN.md 4.1.6)
    # ==========================================
    op.create_table(
        "pt_template_category",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False, comment="模板ID"),
        sa.Column("category_id", sa.BigInteger(), nullable=False, comment="分类ID"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["pt_template.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["kb_category.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "category_id", name="uq_ptpl_cat"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    # ==========================================
    # 种子数据 — 3 个系统预置模板 (is_system=1, 不可删除)
    # ==========================================
    template_table = sa.table(
        "pt_template",
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("template_content", sa.String),
        sa.column("variables", mysql.JSON),
        sa.column("tags", sa.String),
        sa.column("usage_count", sa.Integer),
        sa.column("is_system", mysql.TINYINT),
        sa.column("status", mysql.TINYINT),
        sa.column("created_by", sa.BigInteger),
    )
    op.bulk_insert(
        template_table,
        [
            {
                "name": item["name"],
                "description": item["description"],
                "template_content": item["template_content"],
                "variables": _DEFAULT_VARIABLES,
                "tags": item["tags"],
                "usage_count": 0,
                "is_system": 1,
                "status": 1,
                "created_by": None,
            }
            for item in _SYSTEM_TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_table("pt_template_category")
    op.drop_index("idx_ptpl_usage", table_name="pt_template")
    op.drop_index("idx_ptpl_is_system", table_name="pt_template")
    op.drop_index("idx_ptpl_category", table_name="pt_template")
    op.drop_table("pt_template")
