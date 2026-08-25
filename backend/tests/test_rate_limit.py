"""
Phase 8 接口限流测试
覆盖: 滑动窗口计数逻辑 / 开关关闭放行 / 超限 429 / 非 API 路径不受限
模式: 单元测试 + monkeypatch 限流配置 (免真实 sys_config 表)
"""

from typing import Any

import pytest
from httpx import AsyncClient

from app.core import rate_limit
from app.core.rate_limit import RateLimitConfig, _SlidingWindow

# ==========================================
# 滑动窗口计数 (纯逻辑)
# ==========================================


class TestSlidingWindow:
    def test_allow_within_limit(self) -> None:
        window = _SlidingWindow(limit=3, window_seconds=60)
        assert window.allow(100.0) is True
        assert window.allow(100.5) is True
        assert window.allow(101.0) is True
        assert window.allow(101.5) is False  # 第 4 次超限

    def test_window_expiry_releases(self) -> None:
        """窗口滑动: 旧记录过期后重新放行"""
        window = _SlidingWindow(limit=2, window_seconds=10)
        assert window.allow(0.0) is True
        assert window.allow(5.0) is True
        assert window.allow(9.0) is False
        # 11 秒后, t=0 的记录滑出窗口
        assert window.allow(11.0) is True
        assert window.allow(11.1) is False

    def test_window_rebuild_on_config_change(self) -> None:
        """配置变更后按新指纹重建窗口, 旧计数清零"""
        rate_limit._clients.clear()
        cfg_a = RateLimitConfig(enabled=True, requests=2, window_seconds=60)
        cfg_b = RateLimitConfig(enabled=True, requests=5, window_seconds=60)

        w1 = rate_limit._get_window("1.2.3.4", cfg_a)
        assert w1.allow(100.0) is True
        assert w1.allow(100.1) is True
        assert w1.allow(100.2) is False  # cfg_a 限 2

        w2 = rate_limit._get_window("1.2.3.4", cfg_b)
        assert w2.allow(100.3) is True  # 新配置新窗口, 不受旧计数影响

        rate_limit._clients.clear()


# ==========================================
# 中间件行为 (monkeypatch 配置读取, 免 DB)
# ==========================================


async def _patch_config(monkeypatch: Any, cfg: RateLimitConfig) -> None:
    async def _fake_get_config() -> RateLimitConfig:
        return cfg

    monkeypatch.setattr(rate_limit, "get_config", _fake_get_config)
    rate_limit._clients.clear()


class TestRateLimitMiddleware:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_disabled_passes_through(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """开关关闭 → 高频请求不拦截"""
        await _patch_config(
            monkeypatch, RateLimitConfig(enabled=False, requests=1, window_seconds=60)
        )
        for _ in range(5):
            resp = await async_client.get("/api/v1/ping")
            assert resp.status_code == 200

    @pytest.mark.asyncio(loop_scope="function")
    async def test_over_limit_returns_429(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """超过阈值 → 429 + 统一错误码 42900"""
        await _patch_config(
            monkeypatch, RateLimitConfig(enabled=True, requests=2, window_seconds=60)
        )
        assert (await async_client.get("/api/v1/ping")).status_code == 200
        assert (await async_client.get("/api/v1/ping")).status_code == 200
        resp = await async_client.get("/api/v1/ping")
        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == 42900
        assert "频繁" in body["msg"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_health_check_not_limited(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """非 /api/v1 路径 (健康检查) 不受限流影响"""
        await _patch_config(
            monkeypatch, RateLimitConfig(enabled=True, requests=1, window_seconds=60)
        )
        for _ in range(5):
            resp = await async_client.get("/health")
            assert resp.status_code == 200

    @pytest.mark.asyncio(loop_scope="function")
    async def test_client_ip_from_xff(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """X-Forwarded-For 头优先作为限流键 (Nginx 反代场景)"""
        await _patch_config(
            monkeypatch, RateLimitConfig(enabled=True, requests=1, window_seconds=60)
        )
        headers = {"X-Forwarded-For": "10.0.0.9"}
        assert (
            await async_client.get("/api/v1/ping", headers=headers)
        ).status_code == 200
        resp = await async_client.get("/api/v1/ping", headers=headers)
        assert resp.status_code == 429
