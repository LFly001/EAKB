"""phase7 管理后台 — 补充 sys_config 种子配置键

Revision ID: 20260824_0005
Revises: 20260816_0004
Create Date: 2026-08-24

Phase 7:
- sys_config 表已在 20260813_0002 建表, 本迁移不建表
- 补种 Phase 6 知识图谱参数键 (此前仅靠 settings 默认值回退, 管理后台不可见):
    graph_enhance_enabled      图谱增强RAG开关 (默认 false)
    graph_entity_top_k         单实体邻居数量上限 (默认 5)
    graph_similarity_threshold 文档相似度阈值 (默认 0.5, 文档质心级)
- 幂等: 键已存在则跳过, 可重复执行
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260824_0005"
down_revision = "20260816_0004"
branch_labels = None
depends_on = None

# 补种的配置键
_SEED_CONFIGS = [
    ("graph_enhance_enabled", "false", "string", "图谱增强RAG开关 (true/false)"),
    ("graph_entity_top_k", "5", "number", "图谱增强单实体邻居数量上限"),
    (
        "graph_similarity_threshold",
        "0.5",
        "number",
        "文档 SIMILAR_TO 相似度阈值 (质心级)",
    ),
]


def upgrade() -> None:
    config_table = sa.table(
        "sys_config",
        sa.column("config_key", sa.String),
        sa.column("config_value", sa.String),
        sa.column("config_type", sa.String),
        sa.column("description", sa.String),
    )
    bind = op.get_bind()

    existing_keys = {
        row[0]
        for row in bind.execute(sa.text("SELECT config_key FROM sys_config")).fetchall()
    }

    rows = [
        {
            "config_key": key,
            "config_value": value,
            "config_type": config_type,
            "description": description,
        }
        for key, value, config_type, description in _SEED_CONFIGS
        if key not in existing_keys
    ]
    if rows:
        op.bulk_insert(config_table, rows)


def downgrade() -> None:
    # 种子键删除会丢失业务配置, 不做物理删除 (与 20260813_0002 的降级策略一致:
    # 表由 Phase 3 迁移管理, 本迁移仅负责补种)
    pass
