"""
Alembic 迁移环境配置
从项目 config.py 读取数据库连接，支持自动生成 & 执行迁移
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 将 backend 目录加入 Python 路径，确保可导入 app 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.models.base import Base
from app.models.category import KbCategory  # noqa: F401
from app.models.document import KbDocument  # noqa: F401
from app.models.document_chunk import KbDocumentChunk  # noqa: F401
from app.models.operation_log import SysOperationLog  # noqa: F401
from app.models.sys_config import SysConfig  # noqa: F401

# 导入所有 ORM 模型，确保被 Alembic 检测到
from app.models.user import SysUser  # noqa: F401

# Alembic Config 对象
config = context.config

# 设置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ==========================================
# 目标元数据 — 所有 ORM 模型的表结构
# ==========================================
target_metadata = Base.metadata


# ==========================================
# 离线模式 (生成 SQL 脚本)
# ==========================================
def run_migrations_offline() -> None:
    """
    离线迁移: 生成 SQL 脚本而非直接连接数据库执行。
    使用: alembic upgrade head --sql > migration.sql
    """
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ==========================================
# 在线模式 (直接连接数据库执行)
# ==========================================
def run_migrations_online() -> None:
    """
    在线迁移: 连接数据库并执行迁移。
    使用: alembic upgrade head
    """
    configuration = config.get_section(config.config_ini_section)
    # 从项目配置注入数据库连接 URL
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ==========================================
# 入口
# ==========================================
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
