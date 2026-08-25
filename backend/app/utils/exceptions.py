"""
全局自定义异常类
统一业务错误抛出，由 main.py 全局异常处理器捕获
"""

from typing import Any


class AppException(Exception):
    """
    业务异常基类。
    所有业务逻辑层错误通过抛出此异常中断流程，
    由全局异常处理器统一转换为标准 JSON 响应。

    使用:
        raise AppException(40001, "用户名已存在")
        raise NotFoundException("文档不存在")
    """

    def __init__(
        self,
        code: int = 500,
        message: str = "服务器内部错误",
        http_status: int = 400,
        detail: Any = None,
    ):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail
        super().__init__(message)


# ==========================================
# 常用业务异常子类
# ==========================================


class BadRequestException(AppException):
    """400 — 请求参数错误"""

    def __init__(self, message: str = "请求参数错误", detail: Any = None):
        super().__init__(code=40000, message=message, http_status=400, detail=detail)


class UnauthorizedException(AppException):
    """401 — 未认证"""

    def __init__(self, message: str = "未登录或 Token 已过期"):
        super().__init__(code=40100, message=message, http_status=401)


class ForbiddenException(AppException):
    """403 — 无权限"""

    def __init__(self, message: str = "权限不足"):
        super().__init__(code=40300, message=message, http_status=403)


class NotFoundException(AppException):
    """404 — 资源不存在"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40400, message=message, http_status=404)


class ConflictException(AppException):
    """409 — 资源冲突 (如用户名已存在)"""

    def __init__(self, message: str = "资源冲突"):
        super().__init__(code=40900, message=message, http_status=409)


class FileTooLargeException(AppException):
    """413 — 文件过大"""

    def __init__(self, message: str = "文件大小超过限制"):
        super().__init__(code=41300, message=message, http_status=413)


class UnsupportedFileTypeException(AppException):
    """415 — 文件类型不支持"""

    def __init__(self, message: str = "不支持的文件类型"):
        super().__init__(code=41500, message=message, http_status=415)


class ServiceUnavailableException(AppException):
    """503 — 服务不可用 (外部依赖异常)"""

    def __init__(self, message: str = "服务暂时不可用"):
        super().__init__(code=50300, message=message, http_status=503)


class RateLimitException(AppException):
    """429 — 请求频率超限 (接口限流中间件)"""

    def __init__(
        self, message: str = "请求过于频繁，请稍后再试", retry_after: int | None = None
    ):
        super().__init__(
            code=42900,
            message=message,
            http_status=429,
            detail={"retry_after": retry_after} if retry_after is not None else None,
        )


# ==========================================
# 外部依赖异常 (Phase 8: 数据库 / 向量库 / 对象存储 / LLM)
# 统一 503 族, 消息友好化, 具体细节仅记录日志
# ==========================================


class DatabaseException(AppException):
    """50301 — 关系数据库异常 (MySQL 不可用 / 执行失败)"""

    def __init__(self, message: str = "数据库服务异常，请稍后重试"):
        super().__init__(code=50301, message=message, http_status=503)


class VectorStoreException(AppException):
    """50302 — 向量库异常 (Chroma 检索 / 写入失败)"""

    def __init__(self, message: str = "向量检索服务异常，请稍后重试"):
        super().__init__(code=50302, message=message, http_status=503)


class StorageException(AppException):
    """50303 — 对象存储异常 (MinIO 上传 / 下载失败)"""

    def __init__(self, message: str = "文件存储服务异常，请稍后重试"):
        super().__init__(code=50303, message=message, http_status=503)


class LLMServiceException(AppException):
    """50304 — 大模型服务异常 (LLM 调用失败 / 超时)"""

    def __init__(self, message: str = "大模型服务暂时不可用，请稍后重试"):
        super().__init__(code=50304, message=message, http_status=503)
