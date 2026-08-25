"""
MinIO 对象存储业务封装
对象路径规划 / 上传 / 下载 / 删除 / 预签名 URL。
底层调用 core/minio_client.py, 本层负责路径规划与异常转换。
"""

import io
import uuid
from datetime import datetime

from loguru import logger

from app.core import minio_client
from app.utils.exceptions import StorageException

# 文档对象存储前缀: documents/{年}/{月}/{uuid}.{ext}
DOCUMENT_PREFIX = "documents"

# 预签名 URL 默认有效期 (秒)
PRESIGNED_URL_EXPIRES = 3600


class MinioService:
    """MinIO 文件存储服务 — 业务层统一入口"""

    # ==========================================
    # 路径规划
    # ==========================================

    @staticmethod
    def build_object_path(file_ext: str) -> str:
        """生成 MinIO 对象路径: documents/2026/08/{uuid}.pdf"""
        now = datetime.now()
        return f"{DOCUMENT_PREFIX}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}.{file_ext}"

    # ==========================================
    # 上传 / 下载 / 删除 / 链接
    # ==========================================

    @staticmethod
    def upload(object_path: str, file_bytes: bytes, content_type: str) -> str:
        """
        上传文件字节到 MinIO。

        Raises:
            StorageException (50303): MinIO 不可用 / 上传失败
        """
        try:
            return minio_client.upload_file(
                object_path=object_path,
                file_data=io.BytesIO(file_bytes),
                file_size=len(file_bytes),
                content_type=content_type,
            )
        except Exception as e:
            logger.error(f"[MinIO] 上传失败: {object_path}, 错误: {e}")
            raise StorageException("文件存储服务异常，请稍后重试") from e

    @staticmethod
    def download(object_path: str) -> bytes:
        """
        从 MinIO 下载文件字节。

        Raises:
            StorageException (50303): MinIO 不可用 / 对象不存在
        """
        try:
            return minio_client.download_file(object_path)
        except Exception as e:
            logger.error(f"[MinIO] 下载失败: {object_path}, 错误: {e}")
            raise StorageException("文件存储服务异常，请稍后重试") from e

    @staticmethod
    def delete(object_path: str) -> None:
        """
        从 MinIO 删除对象。删除失败仅记录告警, 不阻断业务 (尽力而为清理)。
        """
        try:
            minio_client.delete_file(object_path)
        except Exception as e:
            logger.warning(f"[MinIO] 删除失败 (已忽略): {object_path}, 错误: {e}")

    @staticmethod
    def get_presigned_url(
        object_path: str,
        expires: int = PRESIGNED_URL_EXPIRES,
    ) -> str:
        """
        生成预签名下载 URL。

        Raises:
            StorageException (50303): MinIO 不可用
        """
        try:
            return minio_client.get_presigned_url(object_path, expires=expires)
        except Exception as e:
            logger.error(f"[MinIO] 生成预签名链接失败: {object_path}, 错误: {e}")
            raise StorageException("文件存储服务异常，请稍后重试") from e

    @staticmethod
    def get_content_type(file_ext: str) -> str | None:
        """常见文档类型的 MIME 映射"""
        return {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "md": "text/markdown",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }.get(file_ext)
