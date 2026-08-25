"""
MinIO 对象存储客户端封装
提供存储桶管理、文件上传/下载/删除
"""

from datetime import timedelta
from typing import BinaryIO

from loguru import logger
from minio import Minio
from minio.error import S3Error

from app.config import settings

# 全局单例
_minio_client: Minio | None = None


def get_minio_client() -> Minio:
    """
    获取 MinIO 客户端单例。
    使用配置中的 endpoint / access_key / secret_key。
    """
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
            region=settings.MINIO_REGION,
        )
        logger.info(f"[MinIO] 客户端已初始化: {settings.MINIO_ENDPOINT}")
    return _minio_client


def ensure_bucket() -> None:
    """
    确保存储桶存在，不存在则创建。
    应在应用启动时调用一次。
    """
    client = get_minio_client()
    bucket_name = settings.MINIO_BUCKET

    found = client.bucket_exists(bucket_name)
    if not found:
        client.make_bucket(bucket_name)
        logger.info(f"[MinIO] 创建存储桶: {bucket_name}")
    else:
        logger.info(f"[MinIO] 存储桶已存在: {bucket_name}")


def upload_file(
    object_path: str,
    file_data: BinaryIO,
    file_size: int,
    content_type: str = "application/octet-stream",
) -> str:
    """
    上传文件到 MinIO。

    Args:
        object_path: MinIO 内对象路径 (如 "documents/2024/abc.pdf")
        file_data: 文件内容 (BinaryIO)
        file_size: 文件大小 (字节)
        content_type: 文件 MIME 类型

    Returns:
        上传后的对象路径
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET

    try:
        client.put_object(
            bucket_name=bucket,
            object_name=object_path,
            data=file_data,
            length=file_size,
            content_type=content_type,
        )
        logger.info(f"[MinIO] 上传成功: {object_path} ({file_size} bytes)")
        return object_path
    except S3Error as e:
        logger.error(f"[MinIO] 上传失败: {object_path}, 错误: {e}")
        raise


def download_file(object_path: str) -> bytes:
    """
    从 MinIO 下载文件内容。

    Args:
        object_path: MinIO 对象路径

    Returns:
        文件字节内容
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET

    try:
        response = client.get_object(bucket_name=bucket, object_name=object_path)
        data = response.read()
        response.close()
        return data
    except S3Error as e:
        logger.error(f"[MinIO] 下载失败: {object_path}, 错误: {e}")
        raise


def delete_file(object_path: str) -> None:
    """
    从 MinIO 删除文件。

    Args:
        object_path: MinIO 对象路径
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET

    try:
        client.remove_object(bucket_name=bucket, object_name=object_path)
        logger.info(f"[MinIO] 删除成功: {object_path}")
    except S3Error as e:
        logger.error(f"[MinIO] 删除失败: {object_path}, 错误: {e}")
        raise


def get_presigned_url(object_path: str, expires: int = 3600) -> str:
    """
    生成预签名下载 URL (临时访问链接)。

    Args:
        object_path: MinIO 对象路径
        expires: URL 有效期 (秒), 默认 1 小时

    Returns:
        预签名 URL 字符串
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET

    url = client.presigned_get_object(
        bucket_name=bucket,
        object_name=object_path,
        expires=timedelta(seconds=expires),
    )
    return url


def get_file_stat(object_path: str) -> dict:
    """
    获取文件元信息 (大小、类型、最后修改时间等)。

    Args:
        object_path: MinIO 对象路径

    Returns:
        文件 stat 信息 dict
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET

    try:
        stat = client.stat_object(bucket_name=bucket, object_name=object_path)
        return {
            "size": stat.size,
            "content_type": stat.content_type,
            "last_modified": (
                stat.last_modified.isoformat() if stat.last_modified else None
            ),
            "etag": stat.etag,
        }
    except S3Error as e:
        logger.error(f"[MinIO] 获取文件信息失败: {object_path}, 错误: {e}")
        raise
