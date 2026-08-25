"""phase8 优化收尾 — 补种接口限流 sys_config 种子配置键

Revision ID: 20260824_0006
Revises: 20260824_0005
Create Date: 2026-08-24

Phase 8:
- 本迁移不建表, 仅补种接口限流参数键 (app/core/rate_limit.py 使用):
    rate_limit_enabled        限流开关 (默认 false, 关闭)
    rate_limit_requests       窗口内单 IP 最大请求数 (默认 60)
    rate_limit_window_seconds 窗口时长秒 (默认 60)
- 幂等: 键已存在则跳过, 可重复执行
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260824_0006"
down_revision = "20260824_0005"
branch_labels = None
depends_on = None

# 补种的配置键
_SEED_CONFIGS = [
    ("rate_limit_enabled", "false", "string", "接口限流开关 (true/false, 默认关闭)"),
    ("rate_limit_requests", "60", "number", "限流窗口内单 IP 最大请求数"),
    ("rate_limit_window_seconds", "60", "number", "限流窗口时长 (秒)"),
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
    # 种子键删除会丢失业务配置, 不做物理删除 (与 0002/0005 降级策略一致)
    pass
