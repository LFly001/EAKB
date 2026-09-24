"""
接口限流中间件 (Phase 8)
纯 ASGI 实现 — 不包裹响应体, 与 SSE 流式输出兼容 (同 RequestLogMiddleware 思路)。
滑动窗口计数, 按客户端 IP 限流; 开关与阈值实时读取 sys_config:
  rate_limit_enabled        开关 (默认 false, 关闭)
  rate_limit_requests       窗口内最大请求数 (默认 60)
  rate_limit_window_seconds 窗口时长秒 (默认 60)
配置经进程内缓存 (TTL 30s) 读取, 避免每请求查库; 管理后台更新配置时立即失效缓存。
"""

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import settings

# sys_config 键名 (与 alembic 迁移 20260824_0006 种子一致)
CFG_ENABLED = "rate_limit_enabled"
CFG_REQUESTS = "rate_limit_requests"
CFG_WINDOW = "rate_limit_window_seconds"

# 进程内配置缓存 TTL (秒)
_CONFIG_CACHE_TTL = 30.0


@dataclass(frozen=True)
class RateLimitConfig:
    """限流运行时配置 (进程内缓存)"""

    enabled: bool
    requests: int
    window_seconds: float


# ---- 进程内配置缓存 ----
_config: RateLimitConfig | None = None
_config_expires_at: float = 0.0
_config_lock: asyncio.Lock | None = None
# 锁与连接池绑定的事件循环 (pytest 每用例独立循环, 跨循环必须重建锁与连接池)
_config_lock_loop: Any = None
_config_loop: Any = None


def _ensure_lock() -> asyncio.Lock:
    """取当前事件循环绑定的锁 (asyncio.Lock 绑定创建时的循环, 跨循环复用会报错)"""
    global _config_lock, _config_lock_loop
    loop = asyncio.get_running_loop()
    if _config_lock is None or _config_lock_loop is not loop:
        _config_lock = asyncio.Lock()
        _config_lock_loop = loop
    return _config_lock


def _default_config() -> RateLimitConfig:
    """回退 settings 默认值 (sys_config 表无值时使用)"""
    return RateLimitConfig(
        enabled=settings.RATE_LIMIT_ENABLED,
        requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=float(settings.RATE_LIMIT_WINDOW_SECONDS),
    )


async def _load_config() -> RateLimitConfig:
    """从 sys_config 实时读取限流参数 (独立会话, 不占用请求连接)"""
    global _config_loop
    from app.core.database import async_session_factory, engine
    from app.services.config_service import ConfigService

    # 事件循环变化时释放旧连接池 (旧连接绑定已关闭的循环, 复用会报错)
    loop = asyncio.get_running_loop()
    if _config_loop is not loop:
        await engine.dispose()
        _config_loop = loop

    defaults = _default_config()
    async with async_session_factory() as db:
        enabled = await ConfigService.get_bool(db, CFG_ENABLED, defaults.enabled)
        requests = int(
            await ConfigService.get_value(db, CFG_REQUESTS, defaults.requests) or 0
        )
        window_seconds = float(
            await ConfigService.get_value(db, CFG_WINDOW, defaults.window_seconds) or 0
        )
    if requests <= 0:
        requests = defaults.requests
    if window_seconds <= 0:
        window_seconds = defaults.window_seconds
    return RateLimitConfig(
        enabled=enabled, requests=requests, window_seconds=window_seconds
    )


async def get_config() -> RateLimitConfig:
    """读取限流配置 (进程内缓存, TTL 30s; 读库失败回退默认值不阻断请求)"""
    global _config, _config_expires_at
    now = time.monotonic()
    if _config is not None and now < _config_expires_at:
        return _config

    async with _ensure_lock():
        # 双重检查: 锁内再次判断, 避免并发请求重复读库
        now = time.monotonic()
        if _config is not None and now < _config_expires_at:
            return _config
        try:
            _config = await _load_config()
        except Exception as e:
            logger.warning(f"[限流] 配置读取失败, 回退默认/上次值: {e}")
            if _config is None:
                _config = _default_config()
        _config_expires_at = now + _CONFIG_CACHE_TTL
        return _config


def invalidate_cache() -> None:
    """配置更新后立即失效缓存 (由 ConfigService.update 调用)"""
    global _config_expires_at
    _config_expires_at = 0.0


# ---- 滑动窗口计数器 ----
class _SlidingWindow:
    """单 IP 滑动窗口: 记录命中时间戳, 超过 limit 则拒绝"""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: deque[float] = deque()

    def allow(self, now: float) -> bool:
        # 清理窗口外旧记录
        while self._hits and now - self._hits[0] > self.window_seconds:
            self._hits.popleft()
        if len(self._hits) >= self.limit:
            return False
        self._hits.append(now)
        return True


# 客户端限流状态: {client_key: (配置指纹, 窗口)}
_clients: dict[str, tuple[tuple[int, float], _SlidingWindow]] = {}

# 清理长期不活跃 IP 的阈值 (上次清理后 10 分钟清理一次)
_LAST_CLEANUP_AT: float = 0.0
_CLEANUP_INTERVAL = 600.0
_IDLE_EXPIRE = 900.0


def _get_window(client_key: str, config: RateLimitConfig) -> _SlidingWindow:
    """取 (或按当前配置重建) 客户端滑动窗口"""
    global _LAST_CLEANUP_AT
    fingerprint = (config.requests, config.window_seconds)
    entry = _clients.get(client_key)
    if entry is not None and entry[0] == fingerprint:
        return entry[1]

    # 配置变更 → 重建窗口; 同时做一次惰性清理, 防 IP 无界增长
    window = _SlidingWindow(config.requests, config.window_seconds)
    _clients[client_key] = (fingerprint, window)

    now = time.monotonic()
    if now - _LAST_CLEANUP_AT > _CLEANUP_INTERVAL:
        stale = [
            key
            for key, (_, w) in _clients.items()
            if not w._hits or now - w._hits[-1] > _IDLE_EXPIRE
        ]
        for key in stale:
            _clients.pop(key, None)
        _LAST_CLEANUP_AT = now
    return window


def _client_ip(scope: dict) -> str:
    """取客户端 IP: 优先 X-Forwarded-For 首项 (Nginx 反代), 回退直连地址"""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """
    纯 ASGI 限流中间件 (Phase 8)。
    仅作用于 /api/v1/* 且开关开启时; 超限直接返回 429 JSON, 不进入路由。
    纯 ASGI 实现保证 SSE (chat-stream) 响应不被缓冲。
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith(settings.API_V1_PREFIX):
            await self.app(scope, receive, send)
            return

        # 豁免 /rag/search (DESIGN 8.1): ESD 同 IP 集中调用会触顶;
        # 端点自有 X-Internal-Key 密钥保护, 无需按 IP 限流
        if path == f"{settings.API_V1_PREFIX}/rag/search":
            await self.app(scope, receive, send)
            return

        config = await get_config()
        if not config.enabled:
            await self.app(scope, receive, send)
            return

        client_ip = _client_ip(scope)
        window = _get_window(client_ip, config)
        if not window.allow(time.monotonic()):
            logger.warning(
                f"[限流] 429 {scope.get('method')} {path} client={client_ip} "
                f"(limit={config.requests}/{config.window_seconds:.0f}s)"
            )
            await self._reject(send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send) -> None:
        """返回统一格式 429 响应"""
        body = json.dumps(
            {"code": 42900, "msg": "请求过于频繁，请稍后再试", "data": None},
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
