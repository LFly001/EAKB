"""
文档向量化流水线 (Embedding Pipeline)
MinIO 下载 → 文本解析 → 分块 → Embedding → 写入 Chroma → 同步 MySQL 分块记录 → 更新状态

由 API 层通过 BackgroundTasks 异步调度 (上传接口不阻塞前端);
每次运行使用独立数据库会话, 与请求生命周期解耦。
"""

import asyncio
import hashlib
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chroma_client import add_chunks, delete_by_document_id
from app.core.database import async_session_factory
from app.core.llm import get_embedding_model
from app.models.category import KbCategory
from app.models.document import KbDocument
from app.models.document_chunk import KbDocumentChunk
from app.services.config_service import ConfigService
from app.services.minio_service import MinioService
from app.utils.file_parser import parse_file
from app.utils.text_splitter import estimate_token_count, split_text

# Embedding API 单批最大文本数 (避免超限)
EMBED_BATCH_SIZE = 64

# 错误信息入库截断长度
_ERROR_MAX_LENGTH = 2000


class EmbeddingService:
    """文档向量化流水线服务 — 后台任务入口"""

    # ==========================================
    # 后台任务入口 (BackgroundTasks 调用)
    # ==========================================

    @staticmethod
    async def run_vectorize_pipeline(document_id: int) -> None:
        """
        执行单个文档的完整向量化流水线。
        独立会话 + 全链路异常捕获: 失败置 failed 并记录错误信息, 支持重试。
        """
        async with async_session_factory() as db:
            try:
                await EmbeddingService._vectorize(db, document_id)
            except Exception as e:
                logger.exception(f"[向量化] 文档 {document_id} 处理失败: {e}")
                await EmbeddingService._mark_failed(db, document_id, str(e))

    # ==========================================
    # 流水线主体
    # ==========================================

    @staticmethod
    async def _vectorize(db: AsyncSession, document_id: int) -> None:
        # ---- 0. 任务前置检查 & 状态流转 pending → processing ----
        doc = await db.get(KbDocument, document_id)
        if doc is None or doc.status == -1:
            logger.warning(f"[向量化] 文档 {document_id} 不存在或已删除, 跳过")
            return

        doc.vector_status = "processing"
        await db.commit()
        logger.info(f"[向量化] 开始处理文档 {document_id}: {doc.file_name}")

        # ---- 1. MinIO 下载 ----
        file_bytes = await asyncio.to_thread(MinioService.download, doc.file_path)

        # ---- 2. 文本解析 ----
        text = await asyncio.to_thread(parse_file, file_bytes, doc.file_type)

        # ---- 3. 分块 (读取系统配置 chunk_size / chunk_overlap) ----
        chunk_size, chunk_overlap = await ConfigService.get_chunk_params(db)
        chunks = await asyncio.to_thread(split_text, text, chunk_size, chunk_overlap)
        if not chunks:
            raise ValueError("文档分块结果为空")
        logger.info(
            f"[向量化] 文档 {document_id} 分块完成: {len(chunks)} 块 "
            f"(chunk_size={chunk_size}, overlap={chunk_overlap})"
        )

        # ---- 4. Embedding 模型检查 & 批量向量生成 ----
        embed_model = get_embedding_model()
        if embed_model is None:
            raise RuntimeError(
                "Embedding 模型未初始化: 请检查 .env 中 "
                "LLM_EMBEDDING_API_KEY / LLM_EMBEDDING_API_BASE 配置"
            )
        embeddings = await asyncio.to_thread(
            EmbeddingService._batch_embed, embed_model, chunks
        )
        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"Embedding 返回数量与分块数不一致: {len(embeddings)} != {len(chunks)}"
            )

        # ---- 5. 清理 Chroma 旧向量 (重新向量化场景) ----
        # 注意: MySQL 旧分块记录推迟到步骤 7 与新分块同事务提交,
        # 若此后的 Chroma 写入失败, 旧分块记录保留 (权威副本不丢失)
        await asyncio.to_thread(delete_by_document_id, doc.id)

        # ---- 6. 写入 Chroma (metadata 携带 document_id/category_id 供 RAG 过滤) ----
        category = await db.get(KbCategory, doc.category_id)
        category_name = category.name if category else ""
        created_at_iso = datetime.now().isoformat()

        chroma_ids: list[str] = []
        metadatas: list[dict] = []
        chunk_records: list[KbDocumentChunk] = []

        for i, chunk_text in enumerate(chunks):
            chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            chroma_id = f"doc_{doc.id}_chunk_{i}"

            chroma_ids.append(chroma_id)
            metadatas.append(
                {
                    "document_id": doc.id,
                    "document_title": doc.title,
                    "chunk_index": i,
                    "category_id": doc.category_id,
                    "category_name": category_name,
                    "file_name": doc.file_name,
                    "file_type": doc.file_type,
                    "chunk_hash": chunk_hash,
                    "created_at": created_at_iso,
                }
            )
            chunk_records.append(
                KbDocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    chunk_text=chunk_text,
                    chunk_hash=chunk_hash,
                    chroma_chunk_id=chroma_id,
                    token_count=estimate_token_count(chunk_text),
                )
            )

        await asyncio.to_thread(
            add_chunks,
            ids=chroma_ids,
            documents=chunks,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        # ---- 7. MySQL 分块记录 & 文档状态 completed ----
        # 旧分块删除与新分块插入在同一事务: 任一步失败整体回滚, 旧数据不丢失
        await db.execute(
            delete(KbDocumentChunk).where(KbDocumentChunk.document_id == doc.id)
        )
        db.add_all(chunk_records)
        doc.chunk_count = len(chunks)
        doc.vector_status = "completed"
        doc.vectorized_at = datetime.now()
        doc.error_message = None
        await db.commit()

        logger.info(
            f"[向量化] 文档 {document_id} 处理完成: {len(chunks)} 块已入库 "
            f"(Chroma + MySQL)"
        )

        # ---- 8. 图谱实体抽取 + SIMILAR_TO 更新 (Phase 6) ----
        # 独立 try/except: 图谱构建失败仅记录日志, 不影响 vector_status=completed;
        # 重新向量化时同路径重建图谱 (旧 MENTIONS 边在写入时清除)
        try:
            from app.services.graph_service import GraphService

            await GraphService.extract_document_after_vectorize(db, doc, chunks)
            logger.info(f"[图谱] 文档 {document_id} 实体抽取与相似边更新完成")
        except Exception as e:
            logger.warning(
                f"[图谱] 文档 {document_id} 图谱更新失败 (不影响向量化结果): {e}"
            )

    # ==========================================
    # 辅助
    # ==========================================

    @staticmethod
    def _batch_embed(embed_model: Any, chunks: list[str]) -> list[list[float]]:
        """分批调用 Embedding API (避免单批超限)"""
        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            try:
                batch_embeddings = embed_model.get_text_embedding_batch(batch)
            except AttributeError:
                # 新版 llama-index 可能移除批量方法, 退化为逐条调用
                batch_embeddings = [
                    embed_model.get_text_embedding(text) for text in batch
                ]
            embeddings.extend(batch_embeddings)
            logger.debug(f"[向量化] Embedding 批次 {i // EMBED_BATCH_SIZE + 1} 完成")
        return embeddings

    @staticmethod
    async def _mark_failed(db: AsyncSession, document_id: int, error: str) -> None:
        """失败状态回写 — 保留错误信息, 支持重新触发向量化"""
        try:
            doc = await db.get(KbDocument, document_id)
            if doc is not None and doc.status != -1:
                doc.vector_status = "failed"
                doc.error_message = error[:_ERROR_MAX_LENGTH]
                await db.commit()
                logger.error(
                    f"[向量化] 文档 {document_id} 置为 failed: {error[:_ERROR_MAX_LENGTH]}"
                )
        except Exception as mark_err:  # 状态回写失败仅记录, 不影响任务退出
            logger.error(f"[向量化] 文档 {document_id} 状态回写失败: {mark_err}")
            await db.rollback()
