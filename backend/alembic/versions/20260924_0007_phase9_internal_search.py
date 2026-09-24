"""phase9 内部检索 — 补种 internal_api_key 内部服务密钥种子键

Revision ID: 20260924_0007
Revises: 20260824_0006
Create Date: 2026-09-24

ESD 集成 (DESIGN 8.1):
- 本迁移不建表, 仅补种内部检索接口密钥键 (app/dependencies.py require_internal_key 使用):
    internal_api_key  64 位十六进制随机密钥 (迁移时 secrets.token_hex(32) 生成,
                      不写死仓库; ESD 侧 sys_config eakb_internal_key 需配置为相同值)
- 幂等: 键已存在则跳过, 可重复执行
"""

import secrets

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260924_0007"
down_revision = "20260824_0006"
branch_labels = None
depends_on = None


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
    if "internal_api_key" in existing_keys:
        return

    op.bulk_insert(
        config_table,
        [
            {
                "config_key": "internal_api_key",
                "config_value": secrets.token_hex(32),
                "config_type": "string",
                "description": "内部检索接口密钥 (X-Internal-Key 校验, ESD 集成)",
            }
        ],
    )


def downgrade() -> None:
    # 种子键删除会导致 ESD 检索全部 40100, 不做物理删除 (与 0002/0005/0006 降级策略一致)
    pass
