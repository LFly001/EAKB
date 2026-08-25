"""
pytest 配置文件
提供测试专用 fixtures: 测试客户端、假用户依赖覆盖 (无需真实 JWT/DB)
Phase 8 补充: override_auth / override_auth_admin fixtures + 依赖覆盖清理
"""

import os
import sys
from collections.abc import AsyncGenerator, Callable
from typing import Any

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.main import app
from app.models.user import SysUser


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """创建 FastAPI 测试客户端 (httpx AsyncClient)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def make_fake_user(
    user_id: int = 1,
    username: str = "zhangsan",
    role: str = "admin",
    status: int = 1,
) -> SysUser:
    """构造内存 SysUser 对象 (不落库, 仅用于依赖注入)"""
    return SysUser(
        id=user_id,
        username=username,
        password_hash="fake-hash",
        real_name="测试用户",
        role=role,
        status=status,
    )


@pytest.fixture
def override_auth() -> Callable[[SysUser], None]:
    """
    覆盖 get_current_user 依赖 — 传入假用户直接通过鉴权, 无需真实 JWT 与数据库。
    测试结束自动清理全部依赖覆盖, 避免用例间串扰。

    用法:
        def test_xxx(async_client, override_auth):
            override_auth(make_fake_user(role="admin"))
    """

    def _override(user: SysUser) -> None:
        async def _fake_current_user() -> SysUser:
            return user

        app.dependency_overrides[get_current_user] = _fake_current_user

    yield _override
    app.dependency_overrides.clear()


@pytest.fixture
def override_auth_admin() -> None:
    """覆盖 get_current_user 为 admin 用户 (后台接口用例)"""
    app.dependency_overrides[get_current_user] = lambda: make_fake_user(
        user_id=1, username="admin", role="admin"
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_auth_employee() -> None:
    """覆盖 get_current_user 为 employee 用户 (权限拦截用例)"""
    app.dependency_overrides[get_current_user] = lambda: make_fake_user(
        user_id=2, username="lisi", role="employee"
    )
    yield
    app.dependency_overrides.clear()


# ==========================================
# 测试用假数据库会话 (服务层用例, 免真实 MySQL)
# ==========================================


class StubScalarResult:
    """execute(...).scalar_one_or_none() 的桩"""

    def __init__(self, value: Any = None):
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar(self) -> Any:
        return self._value


class StubListResult:
    """execute(...).scalars().all() / .one() 的桩"""

    def __init__(self, items: list[Any]):
        self._items = items

    def scalars(self) -> "StubListResult":
        return self

    def all(self) -> list[Any]:
        return self._items

    def one(self) -> Any:
        return self._items[0]

    def one_or_none(self) -> Any:
        return self._items[0] if self._items else None


class FakeDB:
    """
    服务层用例假会话: execute 可返回标量桩或列表桩 (按调用次序),
    commit / rollback / refresh / add / delete 均为空操作。
    用于 upload_files / batch_trigger_vectorize / batch_operate 等纯逻辑验证。
    """

    def __init__(self, execute_results: list[Any] | None = None):
        self.execute_results = list(execute_results or [])
        self.execute_calls: list[Any] = []
        self.committed = 0
        self.rolled_back = 0
        self.refreshed: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        self.execute_calls.append(stmt)
        if self.execute_results:
            return self.execute_results.pop(0)
        return StubScalarResult(None)

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)
        if obj.id is None:
            obj.id = 1

    def add(self, obj: Any) -> None:
        pass

    async def delete(self, obj: Any) -> None:
        pass
