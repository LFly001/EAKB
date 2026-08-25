"""
FastAPI 应用入口
生命周期事件、全局中间件、异常捕获、SSE 流式响应、路由挂载
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.config import settings
from app.core.database import engine
from app.utils.exceptions import AppException, DatabaseException


async def _warmup_embedding() -> None:
    """后台预热 Embedding 模型 (线程池加载, 不阻塞事件循环)"""
    try:
        from app.core.llm import get_embedding_model

        await asyncio.to_thread(get_embedding_model)
    except Exception as e:
        logger.warning(f"[核心] Embedding 模型预热失败: {e}")


# ==========================================
# 生命周期事件
# ==========================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用启动 & 关闭事件"""
    logger.info(f"[{settings.APP_NAME}] 启动中... (env={settings.APP_ENV})")

    # ---- 启动时 ----
    # 注意: 数据库表通过 Alembic 迁移管理，此处不自动 create_all
    # 如需开发环境自动建表，取消下方注释:
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    logger.info("[核心] 数据库引擎已就绪")
    logger.info(f"[核心] Chroma 持久化目录: {settings.CHROMA_PERSIST_DIR}")
    logger.info(f"[核心] MinIO 存储桶: {settings.MINIO_BUCKET}")
    logger.info(f"[核心] Neo4j 连接: {settings.NEO4J_URI}")

    # Phase 5: LlamaIndex 全局 Settings (LLM 单例, 失败不阻断启动)
    try:
        from app.core.llm import init_llama_settings

        init_llama_settings()
    except Exception as e:
        logger.warning(f"[核心] LlamaIndex Settings 初始化失败: {e}")

    # 确保 MinIO 存储桶存在 (MinIO 未就绪仅告警, 不阻断启动)
    try:
        from app.core.minio_client import ensure_bucket

        ensure_bucket()
    except Exception as e:
        logger.warning(f"[核心] MinIO 存储桶初始化失败 (服务启动后请检查): {e}")

    # Phase 6: Neo4j 约束初始化 (同步驱动走线程池; 未就绪仅告警, 图谱功能启动后可用)
    try:
        from app.core.neo4j_client import init_graph_constraints

        await asyncio.to_thread(init_graph_constraints)
    except Exception as e:
        logger.warning(f"[核心] Neo4j 初始化失败 (图谱功能不可用): {e}")

    # Phase 5: 后台预热 Embedding 模型 — 首次加载 10-60s,
    # 提前到启动阶段执行, 首次问答的检索步骤不再等待 (失败仅告警, 请求时重试)
    warmup_task = asyncio.create_task(_warmup_embedding())

    yield  # 应用运行中

    # ---- 关闭时 ----
    logger.info(f"[{settings.APP_NAME}] 正在关闭...")
    if not warmup_task.done():
        warmup_task.cancel()
        try:
            await warmup_task
        except (asyncio.CancelledError, Exception):
            pass
    await engine.dispose()
    logger.info("[核心] 数据库连接池已释放")

    # Phase 6: 关闭 Neo4j 驱动
    try:
        from app.core.neo4j_client import close_neo4j_driver

        await asyncio.to_thread(close_neo4j_driver)
    except Exception as e:
        logger.warning(f"[核心] Neo4j 驱动关闭异常: {e}")


# ==========================================
# 创建 FastAPI 实例
# ==========================================

app = FastAPI(
    title=settings.APP_NAME,
    description="企业知识库智能助手 API — 基于 RAG 的私有知识库问答系统",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ==========================================
# 全局中间件
# ==========================================

# CORS 跨域 — 仅放行配置白名单，禁止 *
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
    max_age=3600,
)


class RequestLogMiddleware:
    """
    请求日志中间件 — 记录请求路径。
    纯 ASGI 实现 (非 BaseHTTPMiddleware): BaseHTTPMiddleware 会包裹响应体
    导致 SSE 流式输出被缓冲, chat-stream 断流; 本实现直接透传。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            logger.debug(f"[请求] {scope['method']} {scope['path']}")
        await self.app(scope, receive, send)


app.add_middleware(RequestLogMiddleware)

# 接口限流 (Phase 8) — 纯 ASGI 实现, 不缓冲 SSE 流; 开关实时读 sys_config
try:
    from app.core.rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)
except Exception as e:  # 限流组件加载失败不阻断启动
    logger.warning(f"[限流] 中间件加载失败, 已跳过: {e}")

# ==========================================
# 全局异常捕获
# ==========================================


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """自定义业务异常处理"""
    logger.warning(f"[业务异常] {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "code": exc.code,
            "msg": exc.message,
            "data": exc.detail,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    FastAPI 原生 HTTPException 统一响应格式。
    覆盖鉴权失败(401)、权限不足(403)、路由不存在(404)、参数校验(422)等,
    避免出现 {"detail": ...} 与项目统一格式不一致。
    业务码映射: code = http_status * 100 (与 AppException 子类约定一致)
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code * 100,
            "msg": str(exc.detail),
            "data": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    请求参数校验失败 (422) 统一响应格式。
    FastAPI 默认返回原生 {"detail": [...]}, 与项目 {code, msg, data} 规范不一致;
    此处取第一条错误组装友好文案。
    """
    errors = exc.errors()
    detail = "参数校验失败"
    if errors:
        first = errors[0]
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = str(first.get("msg", "")).split(";")[0]
        detail = f"{loc}: {msg}" if loc else msg
    logger.debug(f"[参数校验] {request.method} {request.url.path}: {detail}")
    return JSONResponse(
        status_code=422,
        content={"code": 42200, "msg": detail, "data": None},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """
    数据库唯一约束 / 外键约束冲突 (Phase 8)。
    常见于并发注册同名用户、删除被引用数据等场景, 统一返回友好提示而非 500。
    """
    logger.warning(f"[数据冲突] {request.method} {request.url.path}: {exc.orig}")
    return JSONResponse(
        status_code=409,
        content={
            "code": 40900,
            "msg": "数据冲突，请检查数据是否已存在或被引用",
            "data": None,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """
    数据库连接 / 执行异常兜底 (Phase 8)。
    MySQL 不可用、连接中断等场景统一返回 503 友好提示, 细节仅记录日志。
    """
    logger.error(
        f"[数据库异常] {request.method} {request.url.path}: {exc}", exc_info=True
    )
    db_exc = DatabaseException()
    return JSONResponse(
        status_code=db_exc.http_status,
        content={
            "code": db_exc.code,
            "msg": db_exc.message,
            "data": None,
        },
    )


@app.exception_handler(asyncio.TimeoutError)
async def timeout_error_handler(
    request: Request, exc: asyncio.TimeoutError
) -> JSONResponse:
    """
    异步超时兜底 (Phase 8): LLM 调用 / Neo4j 查询 / MinIO 上传等外部依赖超时。
    返回 504 友好提示, 避免透出原始超时堆栈。
    """
    logger.warning(f"[请求超时] {request.method} {request.url.path}")
    return JSONResponse(
        status_code=504,
        content={
            "code": 50400,
            "msg": "请求处理超时，请稍后重试",
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局未捕获异常处理"""
    logger.error(
        f"[系统异常] {request.method} {request.url.path}: {exc}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "msg": "服务器内部错误" if settings.APP_ENV == "production" else str(exc),
            "data": None,
        },
    )


# ==========================================
# 路由挂载
# ==========================================

# 挂载 v1 API 路由
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# ==========================================
# 健康检查 (独立于 v1 路由)
# ==========================================


@app.get("/health", tags=["系统"])
async def health_check():
    """Kubernetes / Docker 健康检查端点"""
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.get("/", tags=["系统"])
async def root():
    """API 根路径"""
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }
