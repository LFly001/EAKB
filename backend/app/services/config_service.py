"""
系统配置服务
sys_config 表读取, 支持类型转换; 表无值时回退 settings 默认值。
RAG 相关参数 (chunk_size / chunk_overlap / top_k 等) 统一从这里读取。
"""

import json
import math
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.sys_config import SysConfig
from app.utils.exceptions import BadRequestException, NotFoundException


class ConfigService:
    """系统配置读取服务 — 业务层收敛所有 sys_config 访问"""

    # ==========================================
    # 基础读取
    # ==========================================

    @staticmethod
    async def get_value(
        db: AsyncSession,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        读取配置值并按 config_type 转换:
        number → int/float, json → dict/list, 其他 → str
        """
        result = await db.execute(select(SysConfig).where(SysConfig.config_key == key))
        row = result.scalar_one_or_none()

        if row is None or row.config_value is None or row.config_value == "":
            return default

        config_type = (row.config_type or "string").lower()
        raw = row.config_value

        if config_type == "number":
            try:
                return float(raw) if "." in raw else int(raw)
            except ValueError:
                logger.warning(f"[配置] {key}={raw!r} 无法转换为 number, 返回默认值")
                return default
        if config_type == "json":
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"[配置] {key} 的 JSON 解析失败, 返回默认值")
                return default
        return raw

    # ==========================================
    # RAG / 文档处理参数 (带校验)
    # ==========================================

    @staticmethod
    async def get_chunk_params(db: AsyncSession) -> tuple[int, int]:
        """
        读取文档分块参数 (chunk_size, chunk_overlap)。
        表无值 / 非法值 → 回退 settings 默认值并做合法性校验。
        """
        chunk_size = int(
            await ConfigService.get_value(db, "chunk_size", settings.DEFAULT_CHUNK_SIZE)
            or 0
        )
        chunk_overlap = int(
            await ConfigService.get_value(
                db, "chunk_overlap", settings.DEFAULT_CHUNK_OVERLAP
            )
            or 0
        )

        if chunk_size <= 0:
            chunk_size = settings.DEFAULT_CHUNK_SIZE
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            chunk_overlap = min(settings.DEFAULT_CHUNK_OVERLAP, chunk_size - 1)

        return chunk_size, chunk_overlap

    @staticmethod
    async def get_bool(db: AsyncSession, key: str, default: bool = False) -> bool:
        """bool 配置读取: 兼容 string("true"/"1"/"yes"/"on") / number / bool (Phase 6)"""
        value = await ConfigService.get_value(db, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return default

    @staticmethod
    async def get_rag_params(db: AsyncSession) -> dict[str, Any]:
        """读取 RAG 检索参数 (Phase 5 问答使用; Phase 6 追加图谱增强开关)"""
        return {
            "top_k": int(
                await ConfigService.get_value(db, "top_k", settings.DEFAULT_TOP_K) or 0
            ),
            "similarity_threshold": float(
                await ConfigService.get_value(
                    db, "similarity_threshold", settings.DEFAULT_SIMILARITY_THRESHOLD
                )
                or 0
            ),
            "max_context_tokens": int(
                await ConfigService.get_value(
                    db, "max_context_tokens", settings.DEFAULT_MAX_CONTEXT_TOKENS
                )
                or 0
            ),
            "graph_enhance_enabled": await ConfigService.get_bool(
                db, "graph_enhance_enabled", settings.DEFAULT_GRAPH_ENHANCE_ENABLED
            ),
            "graph_entity_top_k": int(
                await ConfigService.get_value(
                    db, "graph_entity_top_k", settings.DEFAULT_GRAPH_ENTITY_TOP_K
                )
                or 0
            ),
        }

    @staticmethod
    async def get_upload_max_size_mb(db: AsyncSession) -> int:
        """
        读取上传文件大小上限 (MB) — sys_config 实时生效 (Phase 7),
        表无值 / 非法值回退 settings.UPLOAD_MAX_SIZE_MB
        """
        try:
            value = int(
                await ConfigService.get_value(
                    db, "upload_max_size_mb", settings.UPLOAD_MAX_SIZE_MB
                )
                or 0
            )
        except (TypeError, ValueError):
            value = 0
        return value if value > 0 else settings.UPLOAD_MAX_SIZE_MB

    # ==========================================
    # 管理后台读写 (Phase 7, 仅 admin)
    # ==========================================

    @staticmethod
    async def list_all(db: AsyncSession) -> list[SysConfig]:
        """配置项全量列表 (按 id 升序, 种子配置在前)"""
        result = await db.execute(select(SysConfig).order_by(SysConfig.id))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_key(db: AsyncSession, key: str) -> SysConfig:
        """按配置键查询 (不存在 → NotFoundException)"""
        result = await db.execute(select(SysConfig).where(SysConfig.config_key == key))
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundException(f"配置项 '{key}' 不存在")
        return row

    @staticmethod
    async def update(
        db: AsyncSession, key: str, config_value: str, updated_by: int
    ) -> SysConfig:
        """
        更新配置值 (实时生效: 各业务读取方每次从 DB 读取, 无需重启)。
        按 config_type 校验值合法性: number 必须可转数字, json 必须可解析。
        """
        row = await ConfigService.get_by_key(db, key)
        config_type = (row.config_type or "string").lower()
        config_value = config_value.strip()

        if config_type == "number":
            try:
                parsed = float(config_value)
                if not math.isfinite(parsed):
                    raise ValueError
            except ValueError:
                raise BadRequestException(
                    f"配置项 '{key}' 类型为 number, 值 '{config_value}' 不是合法数字"
                )
        elif config_type == "json":
            try:
                json.loads(config_value)
            except json.JSONDecodeError:
                raise BadRequestException(
                    f"配置项 '{key}' 类型为 json, 值不是合法 JSON"
                )

        row.config_value = config_value
        row.updated_by = updated_by
        await db.commit()
        await db.refresh(row)
        logger.info(f"[配置] 管理员更新配置: {key} = {config_value}")

        # Phase 8: 限流参数实时生效 — 更新后失效限流中间件进程内缓存
        if key.startswith("rate_limit"):
            try:
                from app.core.rate_limit import invalidate_cache

                invalidate_cache()
            except Exception as e:  # 缓存失效失败不影响配置更新结果
                logger.warning(f"[配置] 限流缓存失效失败: {e}")

        return row
