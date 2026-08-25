"""
基础健康检查测试
验证 FastAPI 应用可以正常启动和响应
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """测试 /health 端点"""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "EAKB"


@pytest.mark.asyncio(loop_scope="function")
async def test_root(async_client: AsyncClient):
    """测试根路径"""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "EAKB"


@pytest.mark.asyncio(loop_scope="function")
async def test_ping(async_client: AsyncClient):
    """测试 API v1 ping"""
    response = await async_client.get("/api/v1/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["ping"] == "pong"
