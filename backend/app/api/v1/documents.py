"""
文档管理路由 — /api/v1/documents
上传 / 分页列表 / 详情 / 下载 / 软删除 / 向量化触发 / 分块查看
上传接口仅下发后台向量化任务, 同步不阻塞前端 (全操作埋点操作日志)
"""

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import SysUser
from app.schemas.common import PageResponse
from app.schemas.document import (
    BatchVectorizeRequest,
    DocumentQuery,
    DownloadUrlResponse,
    VectorizeResult,
    VectorStatus,
)
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.log_service import LogService
from app.utils.exceptions import BadRequestException
from app.utils.response import success

router = APIRouter()

# 操作日志模块名
_LOG_MODULE = "knowledge"

# 预签名 URL 有效期 (秒)
_PRESIGNED_EXPIRES = 3600


# ==========================================
# GET /documents/ — 文档分页列表
# ==========================================
@router.get("/", summary="文档分页列表")
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=None, description="搜索关键词（标题/文件名/标签）"),
    category_id: int = Query(default=None, description="分类过滤（含子分类）"),
    vector_status: str = Query(default=None, description="向量化状态过滤"),
    file_type: str = Query(default=None, description="文件类型过滤"),
    status: int = Query(default=None, description="状态过滤"),
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """文档列表 (分页 + 筛选, 默认排除已删除)"""
    vs = None
    if vector_status:
        try:
            vs = VectorStatus(vector_status)
        except ValueError:
            raise BadRequestException(f"非法向量化状态: {vector_status}")

    query = DocumentQuery(
        page=page,
        page_size=page_size,
        keyword=keyword,
        category_id=category_id,
        vector_status=vs,
        file_type=file_type,
        status=status,
    )
    items, total = await DocumentService.get_list(db, query)

    return success(
        data=PageResponse.from_list(
            items=[item.model_dump() for item in items],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    )


# ==========================================
# POST /documents/upload — 上传文档 (多文件)
# ==========================================
@router.post("/upload", summary="上传文档")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="文档文件 (支持多文件)"),
    category_id: int = Form(..., description="所属分类ID"),
    title: str | None = Form(
        default=None, description="文档标题（仅单文件上传时生效）"
    ),
    description: str | None = Form(default=None, description="文档描述"),
    tags: str | None = Form(default=None, description="标签（逗号分隔）"),
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """
    上传文档: MinIO 持久化 + MySQL 元数据, 向量化任务后台异步执行。
    接口立即返回, 前端通过列表接口轮询 vector_status。
    """
    docs = await DocumentService.upload_files(
        db,
        files=files,
        category_id=category_id,
        user=user,
        title=title,
        description=description,
        tags=tags,
    )

    # 每文档下发一个后台向量化任务 (pending → processing → completed/failed)
    for doc in docs:
        background_tasks.add_task(EmbeddingService.run_vectorize_pipeline, doc.id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="upload_document",
        module=_LOG_MODULE,
        target_type="document",
        target_id=",".join(str(d.id) for d in docs),
        detail={
            "count": len(docs),
            "category_id": category_id,
            "documents": [{"id": d.id, "file_name": d.file_name} for d in docs],
        },
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    infos = await DocumentService._to_infos(db, docs)
    return success(
        data=[info.model_dump() for info in infos],
        msg=f"上传成功 {len(docs)} 个文档，向量化任务已下发",
    )


# ==========================================
# POST /documents/batch-vectorize — 批量向量化
# ==========================================
@router.post("/batch-vectorize", summary="批量向量化")
async def batch_vectorize(
    background_tasks: BackgroundTasks,
    req: BatchVectorizeRequest,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """多选文档一键触发 (重建) 向量"""
    results: list[VectorizeResult] = await DocumentService.batch_trigger_vectorize(
        db, req
    )

    triggered_ids = [r.document_id for r in results if r.triggered]
    for document_id in triggered_ids:
        background_tasks.add_task(EmbeddingService.run_vectorize_pipeline, document_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="batch_vectorize",
        module=_LOG_MODULE,
        target_type="document",
        target_id=",".join(str(i) for i in req.document_ids),
        detail={
            "requested": len(req.document_ids),
            "triggered": len(triggered_ids),
            "results": [r.model_dump() for r in results],
        },
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(
        data=[r.model_dump() for r in results],
        msg=f"已下发 {len(triggered_ids)} 个向量化任务",
    )


# ==========================================
# GET /documents/{id} — 文档详情
# ==========================================
@router.get("/{document_id}", summary="文档详情")
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """文档详情 (+1 浏览次数)"""
    info = await DocumentService.get_detail(db, document_id, increment_view=True)
    return success(data=info.model_dump())


# ==========================================
# GET /documents/{id}/download — 下载文档
# ==========================================
@router.get("/{document_id}/download", summary="下载文档")
async def download_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """返回预签名下载 URL (+1 下载次数), 前端直接打开链接"""
    doc, url = await DocumentService.get_download_url(db, document_id)

    return success(
        data=DownloadUrlResponse(
            document_id=doc.id,
            file_name=doc.file_name,
            download_url=url,
            expires_in=_PRESIGNED_EXPIRES,
        ).model_dump(),
    )


# ==========================================
# DELETE /documents/{id} — 删除文档 (软删)
# ==========================================
@router.delete("/{document_id}", summary="删除文档")
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """软删除 (status=-1), 同步清理 Chroma 向量, 分块记录保留审计"""
    doc = await DocumentService.soft_delete(db, document_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="delete_document",
        module=_LOG_MODULE,
        target_type="document",
        target_id=str(document_id),
        detail={"title": doc.title, "file_name": doc.file_name},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    return success(msg=f"文档 '{doc.title}' 已删除")


# ==========================================
# POST /documents/{id}/vectorize — 触发向量化
# ==========================================
@router.post("/{document_id}/vectorize", summary="触发向量化")
async def vectorize_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: SysUser = Depends(get_current_user),
    http_req: Request = None,
):
    """手动触发 (或失败重试) 向量化"""
    doc = await DocumentService.trigger_vectorize(db, document_id)
    background_tasks.add_task(EmbeddingService.run_vectorize_pipeline, document_id)

    await LogService.create(
        db,
        user_id=user.id,
        username=user.username,
        action="vectorize_document",
        module=_LOG_MODULE,
        target_type="document",
        target_id=str(document_id),
        detail={"title": doc.title},
        ip_address=http_req.client.host if http_req and http_req.client else None,
    )

    info = (await DocumentService._to_infos(db, [doc]))[0]
    return success(
        data=info.model_dump(),
        msg="向量化任务已下发",
    )


# ==========================================
# GET /documents/{id}/chunks — 查看分块列表
# ==========================================
@router.get("/{document_id}/chunks", summary="查看分块列表")
async def get_document_chunks(
    document_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: SysUser = Depends(get_current_user),
):
    """文档分块记录列表 (按 chunk_index 排序)"""
    chunks, total = await DocumentService.get_chunks(
        db, document_id, page=page, page_size=page_size
    )

    return success(
        data=PageResponse.from_list(
            items=[c.model_dump() for c in chunks],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    )
