"""
Phase 8 认证模块测试
覆盖: 注册 / 登录 / 刷新 Token / 个人信息 / 修改密码 / 注销
模式: 路由级测试 + monkeypatch 业务服务 (免真实 MySQL/JWT 密钥不变更)
"""

from typing import Any

import pytest
from httpx import AsyncClient

from app.services.auth_service import AuthService
from app.utils.exceptions import ConflictException, UnauthorizedException
from tests.conftest import make_fake_user

# ==========================================
# 公共桩
# ==========================================

_REGISTER_BODY = {
    "username": "zhangsan",
    "password": "Abc123456",
    "confirm_password": "Abc123456",
    "real_name": "张三",
}


def _patch_noop_log(monkeypatch: Any) -> None:
    """操作日志写库桩 (路由层测试无需真实落库)"""
    import app.api.v1.auth as auth_api

    async def _noop_log(*args: Any, **kwargs: Any) -> Any:
        return None

    monkeypatch.setattr(auth_api.LogService, "create", _noop_log)


# ==========================================
# 注册
# ==========================================


class TestRegister:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_register_success(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """注册成功 → 200, 返回用户信息"""
        _patch_noop_log(monkeypatch)

        async def _fake_register(db: Any, req: Any) -> Any:
            return make_fake_user(user_id=10, username=req.username, role="employee")

        monkeypatch.setattr(AuthService, "register", _fake_register)

        resp = await async_client.post("/api/v1/auth/register", json=_REGISTER_BODY)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["data"]["username"] == "zhangsan"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_register_username_conflict(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """用户名已存在 → 40900 友好提示"""
        _patch_noop_log(monkeypatch)

        async def _fake_register(db: Any, req: Any) -> Any:
            raise ConflictException(f"用户名 '{req.username}' 已存在")

        monkeypatch.setattr(AuthService, "register", _fake_register)

        resp = await async_client.post("/api/v1/auth/register", json=_REGISTER_BODY)
        assert resp.status_code == 409
        assert resp.json()["code"] == 40900

    @pytest.mark.asyncio(loop_scope="function")
    async def test_register_password_mismatch(self, async_client: AsyncClient) -> None:
        """两次密码不一致 → 42200 参数校验"""
        body = {**_REGISTER_BODY, "confirm_password": "Different123"}
        resp = await async_client.post("/api/v1/auth/register", json=body)
        assert resp.status_code == 422
        assert resp.json()["code"] == 42200

    @pytest.mark.asyncio(loop_scope="function")
    async def test_register_invalid_username(self, async_client: AsyncClient) -> None:
        """用户名含非法字符 → 42200"""
        body = {**_REGISTER_BODY, "username": "中文名"}
        resp = await async_client.post("/api/v1/auth/register", json=body)
        assert resp.status_code == 422
        assert resp.json()["code"] == 42200


# ==========================================
# 登录 / 刷新 Token
# ==========================================


class TestLogin:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_success(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """登录成功 → 返回 access/refresh token + 用户信息"""
        _patch_noop_log(monkeypatch)

        async def _fake_login(db: Any, username: str, password: str) -> Any:
            return (
                "fake-access-token",
                "fake-refresh-token",
                make_fake_user(user_id=1, username=username),
            )

        monkeypatch.setattr(AuthService, "login", _fake_login)

        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "zhangsan", "password": "Abc123456"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"] == "fake-access-token"
        assert data["refresh_token"] == "fake-refresh-token"
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "zhangsan"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_login_wrong_password(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """密码错误 → 40100"""
        _patch_noop_log(monkeypatch)

        async def _fake_login(db: Any, username: str, password: str) -> Any:
            raise UnauthorizedException("用户名或密码错误")

        monkeypatch.setattr(AuthService, "login", _fake_login)

        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"username": "zhangsan", "password": "wrong-password"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_success(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """刷新 Token 成功 → 返回新 token 对"""

        async def _fake_refresh(db: Any, refresh_token: str) -> Any:
            return "new-access", "new-refresh"

        monkeypatch.setattr(AuthService, "refresh_access_token", _fake_refresh)

        resp = await async_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "old-refresh"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"] == "new-access"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_refresh_invalid_token(
        self, async_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """Refresh Token 无效 → 40100"""

        async def _fake_refresh(db: Any, refresh_token: str) -> Any:
            raise UnauthorizedException("Refresh Token 无效或已过期")

        monkeypatch.setattr(AuthService, "refresh_access_token", _fake_refresh)

        resp = await async_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "bad-token"}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100


# ==========================================
# 个人信息 / 修改密码 / 注销 (需鉴权)
# ==========================================


class TestMe:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_me_requires_token(self, async_client: AsyncClient) -> None:
        """未携带 Token → 40100"""
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == 40100

    @pytest.mark.asyncio(loop_scope="function")
    async def test_me_success(
        self, async_client: AsyncClient, override_auth_employee: None
    ) -> None:
        """已登录员工获取个人信息 → 200"""
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["username"] == "lisi"
        assert data["role"] == "employee"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_change_password_success(
        self, async_client: AsyncClient, override_auth_employee: None, monkeypatch: Any
    ) -> None:
        """修改密码成功 → 200 (旧密码校验在 service 层完成)"""
        _patch_noop_log(monkeypatch)

        async def _fake_change(db: Any, user_id: int, old: str, new: str) -> None:
            assert old == "OldPass123"
            assert new == "NewPass456"

        monkeypatch.setattr(AuthService, "change_password", _fake_change)

        resp = await async_client.put(
            "/api/v1/auth/password",
            json={
                "old_password": "OldPass123",
                "new_password": "NewPass456",
                "confirm_password": "NewPass456",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    @pytest.mark.asyncio(loop_scope="function")
    async def test_change_password_mismatch(
        self, async_client: AsyncClient, override_auth_employee: None
    ) -> None:
        """两次新密码不一致 → 42200 (鉴权依赖先于参数校验, 需先覆盖登录态)"""
        resp = await async_client.put(
            "/api/v1/auth/password",
            json={
                "old_password": "OldPass123",
                "new_password": "NewPass456",
                "confirm_password": "OtherPass789",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 42200

    @pytest.mark.asyncio(loop_scope="function")
    async def test_logout(
        self, async_client: AsyncClient, override_auth_employee: None, monkeypatch: Any
    ) -> None:
        """注销 → 200"""
        _patch_noop_log(monkeypatch)
        resp = await async_client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["msg"] == "注销成功"
