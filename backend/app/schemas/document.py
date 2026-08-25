"""
知识库文档 Pydantic 模型
入参校验 (查询/更新/批量向量化) + 出参序列化 (DocumentInfo/DocumentChunkInfo)
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PageQuery

# ==========================================
# 枚举
# ==========================================


class VectorStatus(str, Enum):
    """向量化状态四状态流转"""

    PENDING = "pending"  # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 完成
    FAILED = "failed"  # 失败


# ==========================================
# 入参 — 查询 / 更新 / 批量操作
# ==========================================


class DocumentQuery(PageQuery):
    """文档分页列表查询参数"""

    category_id: int | None = Field(default=None, description="分类过滤（含子分类）")
    vector_status: VectorStatus | None = Field(
        default=None, description="向量化状态过滤"
    )
    file_type: str | None = Field(default=None, description="文件类型过滤")
    # 列表默认排除已删除(status=-1), 故过滤条件仅允许 0/1 (草稿/发布)
    status: int | None = Field(default=None, ge=0, le=1, description="状态过滤")


class DocumentUpdate(BaseModel):
    """文档元数据更新请求 (仅更新传入字段)"""

    title: str | None = Field(
        default=None, min_length=1, max_length=255, description="文档标题"
    )
    category_id: int | None = Field(default=None, description="所属分类ID")
    description: str | None = Field(
        default=None, max_length=5000, description="文档描述"
    )
    tags: str | None = Field(
        default=None, max_length=500, description="标签（逗号分隔）"
    )


class BatchVectorizeRequest(BaseModel):
    """批量向量化请求"""

    document_ids: list[int] = Field(min_length=1, description="文档ID列表")


class VectorizeResult(BaseModel):
    """向量化触发结果"""

    document_id: int
    triggered: bool = Field(default=False, description="是否成功下发任务")
    message: str = Field(default="", description="跳过原因（未触发时）")


# ==========================================
# 出参 — 文档信息 / 分块信息
# ==========================================


class DocumentInfo(BaseModel):
    """文档完整信息"""

    id: int
    title: str
    category_id: int
    category_name: str | None = Field(
        default=None, description="分类名称（冗余，方便前端展示）"
    )
    file_name: str
    file_type: str
    file_size: int
    file_path: str
    file_hash: str | None = None
    vector_status: str = "pending"
    chunk_count: int = 0
    description: str | None = None
    tags: str | None = None
    view_count: int = 0
    download_count: int = 0
    status: int = 1
    uploaded_by: int | None = None
    uploader_name: str | None = Field(default=None, description="上传人用户名（冗余）")
    vectorized_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkInfo(BaseModel):
    """文档分块信息"""

    id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    chunk_hash: str | None = None
    chroma_chunk_id: str | None = None
    token_count: int | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DownloadUrlResponse(BaseModel):
    """下载地址响应 — 预签名 URL"""

    document_id: int
    file_name: str
    download_url: str
    expires_in: int = Field(default=3600, description="链接有效期（秒）")
