"""
API v1 路由汇总
挂载所有子模块路由
"""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.documents import router as documents_router
from app.api.v1.graph import router as graph_router
from app.api.v1.rag import router as rag_router
from app.api.v1.templates import router as templates_router
from app.api.v1.users import router as users_router

# API v1 主路由
api_router = APIRouter()

# ==========================================
# 已启用路由
# ==========================================
api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(users_router, prefix="/users", tags=["用户管理"])
api_router.include_router(categories_router, prefix="/categories", tags=["知识库分类"])
api_router.include_router(documents_router, prefix="/documents", tags=["文档管理"])
api_router.include_router(templates_router, prefix="/templates", tags=["提示词模版"])
api_router.include_router(rag_router, prefix="/rag", tags=["RAG问答"])
api_router.include_router(graph_router, prefix="/graph", tags=["知识图谱"])
api_router.include_router(admin_router, prefix="/admin", tags=["管理后台"])


# ==========================================
# 连通性测试
# ==========================================
@api_router.get("/ping", tags=["系统"])
async def ping():
    """API v1 连通性测试"""
    return {"ping": "pong", "version": "v1", "status": "ok"}
