"""
Phase 8 管理员权限边界测试
覆盖: 未登录 401 / 普通员工访问后台接口 40300 / admin 正常访问
模式: 依赖覆盖 get_current_user (免真实 JWT), 服务层 monkeypatch
"""

from typing import Any

import pytest
from httpx import AsyncClient

from app.schemas.admin import DashboardStats
from app.services.dashboard_service import DashboardService

# 后台管理 GET 接口清单 (DESIGN 6.8, 全部 require_admin)
_ADMIN_ENDPOINTS = [
    ("GET", "/api/v1/admin/dashboard"),
    ("GET", "/api/v1/admin/logs"),
    ("GET", "/api/v1/admin/configs"),
    ("GET", "/api/v1/users/"),
]


class TestUnauthorized:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_admin_api_without_token(self, async_client: AsyncClient) -> None:
        """未携带 Token 访问后台接口 → 40100"""
        for method, path in _ADMIN_ENDPOINTS:
            resp = await async_client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} 应返回 401"
            assert resp.json()["code"] == 40100


class TestEmployeeForbidden:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_employee_blocked_from_admin_apis(
        self, async_client: AsyncClient, override_auth_employee: None
    ) -> None:
        """普通员工访问全部后台接口 → 40300 拦截"""
        for method, path in _ADMIN_ENDPOINTS:
            resp = await async_client.request(method, path)
            assert resp.status_code == 403, f"{method} {path} 应返回 403"
            body = resp.json()
            assert body["code"] == 40300, f"{method} {path} 业务码应为 40300"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_employee_blocked_from_graph_build(
        self, async_client: AsyncClient, override_auth_employee: None
    ) -> None:
        """员工 POST /graph/build (全量重建图谱) → 40300"""
        resp = await async_client.post("/api/v1/graph/build", json={})
        assert resp.status_code == 403
        assert resp.json()["code"] == 40300

    @pytest.mark.asyncio(loop_scope="function")
    async def test_employee_blocked_from_user_batch(
        self, async_client: AsyncClient, override_auth_employee: None
    ) -> None:
        """员工 POST /users/batch → 40300"""
        resp = await async_client.post(
            "/api/v1/users/batch", json={"action": "disable", "user_ids": [3]}
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 40300


class TestAdminAllowed:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_admin_access_dashboard(
        self, async_client: AsyncClient, override_auth_admin: None, monkeypatch: Any
    ) -> None:
        """admin 访问看板 → 200 并返回统计结构 (服务层打桩, 免真实 DB)"""

        async def _fake_stats(db: Any) -> DashboardStats:
            return DashboardStats(
                user_count=3,
                document_count=2,
                conversation_count=5,
                today_question_count=1,
                vectorized_document_count=1,
                today_operation_count=10,
            )

        monkeypatch.setattr(DashboardService, "get_stats", _fake_stats)

        resp = await async_client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_count"] == 3
        assert data["document_count"] == 2
        assert data["today_operation_count"] == 10
