"""
数据库连接 — SQLAlchemy 引擎 & 会话工厂
支持同步 (alembic 迁移) 和异步 (FastAPI 请求) 双模式
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# ==========================================
# 同步引擎 — Alembic 迁移使用
# ==========================================
sync_engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,  # 自动检测断连
)

# 同步会话工厂
sync_session_factory = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)

# ==========================================
# 异步引擎 — FastAPI 请求使用
# ==========================================
async_engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

# 异步会话工厂
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ==========================================
# 便捷别名 — main.py / alembic 使用
# ==========================================
# 默认 engine 指向异步引擎 (FastAPI 主循环使用)
engine = async_engine

# ==========================================
# ORM 基类
# ==========================================


class Base(DeclarativeBase):
    """所有 ORM 模型的抽象基类"""
