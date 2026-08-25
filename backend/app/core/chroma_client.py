"""
ChromaDB 向量库客户端封装
提供单例连接、Collection 管理、文档增删查
Phase 8: 检索结果进程内缓存 (TTL + 写入失效) + 异常友好化 (VectorStoreException)
"""

import threading
import time
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.config import settings
from app.utils.exceptions import VectorStoreException

# Collection 名称常量
COLLECTION_NAME = "document_chunks"

# ---- 检索结果缓存 (Phase 8) ----
# 相同问题的重复检索 (多轮追问 / 并发用户) 直接命中缓存, 免去 Chroma 往返;
# 任何写入 (add_chunks / delete_by_document_id) 都会清空缓存保证一致性
_QUERY_CACHE_TTL_SECONDS = 300.0
_QUERY_CACHE_MAX_ENTRIES = 512
_query_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
_query_cache_lock = threading.Lock()

# 全局单例
# 注意: chromadb.PersistentClient 是工厂函数而非类型, 直接作注解会报
# mypy valid-type, 统一用 Any (与 _collection 一致)
_chroma_client: Any | None = None
_collection: Any | None = None


def get_chroma_client() -> Any:
    """
    获取 ChromaDB PersistentClient 单例。
    使用本地持久化模式，向量数据存储在 CHROMA_PERSIST_DIR。
    """
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        logger.info(
            f"[Chroma] 客户端已初始化, 持久化目录: {settings.CHROMA_PERSIST_DIR}"
        )
    return _chroma_client


def get_collection(name: str = COLLECTION_NAME) -> Any:
    """
    获取或创建 ChromaDB Collection。
    使用 cosine 距离度量，metadata 用于检索时过滤。
    """
    global _collection
    if _collection is None:
        client = get_chroma_client()
        try:
            _collection = client.get_collection(name=name)
            logger.info(f"[Chroma] 获取已有 Collection: {name}")
        except Exception:
            _collection = client.create_collection(
                name=name,
                metadata={
                    "hnsw:space": "cosine",
                    "description": "企业知识库文档分块集合",
                },
            )
            logger.info(f"[Chroma] 创建新 Collection: {name}")
    return _collection


def add_chunks(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
    embeddings: list[list[float]] | None = None,
) -> None:
    """
    批量添加文档分块到向量库。

    Args:
        ids: 分块唯一 ID 列表
        documents: 分块文本列表
        metadatas: 分块元数据列表 (含 document_id, category_id 等)
        embeddings: 可选，预计算的向量
    """
    collection = get_collection()
    try:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
    except VectorStoreException:
        raise
    except Exception as e:
        logger.error(f"[Chroma] 分块写入失败: {e}")
        raise VectorStoreException("向量库写入失败，请稍后重试") from e

    # 写入后失效检索缓存 (向量库内容已变化)
    clear_query_cache()


def clear_query_cache() -> None:
    """清空检索结果缓存 (写入 / 删除分块后调用)"""
    with _query_cache_lock:
        _query_cache.clear()


def query_chunks(
    query_text: str,
    top_k: int = 5,
    category_ids: list[int] | None = None,
    similarity_threshold: float = 0.7,
    query_embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    """
    向量相似度检索。

    Args:
        query_text: 查询文本 (仅 query_embedding 未提供时使用, Chroma 本地
                    ONNX 默认嵌入与库内 bge 1024 维向量不匹配, 不推荐)
        top_k: 返回结果数
        category_ids: 知识库分类 ID 过滤 (可选, int 列表;
                      metadata 中 category_id 以 int 存储, 类型必须一致)
        similarity_threshold: 相似度阈值
        query_embedding: 预计算的查询向量 (RAG 问答必须提供: 与库内向量同
                         模型同维度, 否则 Chroma 报维度不匹配)

    Returns:
        检索结果列表，每项包含 id, document, metadata, distance
    """
    # ---- 缓存查找 (Phase 8): 相同查询直接返回, 免 Chroma 往返 ----
    cache_key = (
        query_text.strip(),
        top_k,
        tuple(category_ids) if category_ids else (),
        similarity_threshold,
    )
    with _query_cache_lock:
        cached = _query_cache.get(cache_key)
    if cached is not None:
        expires_at, cached_chunks = cached
        if time.monotonic() < expires_at:
            # 返回副本, 防止调用方篡改缓存内容
            return [dict(c) for c in cached_chunks]
        with _query_cache_lock:
            _query_cache.pop(cache_key, None)

    collection = get_collection()

    # 构建 metadata 过滤条件
    where_filter: dict[str, Any] | None = None
    if category_ids:
        where_filter = {"category_id": {"$in": category_ids}}

    try:
        # 显式查询向量优先: 保证与写入侧 (bge-large-zh 1024 维) 同源同维度
        if query_embedding is not None:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        else:
            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
    except VectorStoreException:
        raise
    except Exception as e:
        # Phase 8: Chroma 不可用 / 查询失败 → 友好异常, 原始错误仅记日志
        logger.error(f"[Chroma] 向量检索失败: {e}")
        raise VectorStoreException() from e

    # 格式化返回结果
    chunks: list[dict[str, Any]] = []
    if results and results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 0
            # Chroma 使用距离度量，转换为相似度分数 (cosine: distance ∈ [0, 2])
            score = 1 - (distance / 2)

            if score >= similarity_threshold:
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": results["documents"][0][i]
                        if results.get("documents")
                        else "",
                        "metadata": results["metadatas"][0][i]
                        if results.get("metadatas")
                        else {},
                        "score": round(score, 4),
                        "distance": round(distance, 4),
                    }
                )

    # ---- 写入缓存 (简单容量控制: 满则淘汰最早插入项) ----
    with _query_cache_lock:
        if len(_query_cache) >= _QUERY_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(_query_cache))
            _query_cache.pop(oldest_key, None)
        _query_cache[cache_key] = (
            time.monotonic() + _QUERY_CACHE_TTL_SECONDS,
            [dict(c) for c in chunks],
        )

    return chunks


def delete_by_document_id(document_id: int) -> None:
    """
    按文档 ID 删除向量库中所有关联分块。
    metadata 中 document_id 以 int 存储, where 过滤条件必须类型一致。
    """
    collection = get_collection()
    try:
        collection.delete(where={"document_id": document_id})
        logger.info(f"[Chroma] 已删除文档 {document_id} 的所有分块")
    except Exception as e:
        logger.warning(f"[Chroma] 删除文档 {document_id} 分块失败: {e}")
        return

    # 删除后失效检索缓存 (向量库内容已变化)
    clear_query_cache()


def get_document_chunks(document_id: int) -> list[dict[str, Any]]:
    """
    获取某文档在向量库中的所有分块记录。

    Args:
        document_id: 文档 ID

    Returns:
        分块记录列表, 每项含 chroma_chunk_id 与 metadata
    """
    collection = get_collection()
    try:
        result = collection.get(
            where={"document_id": document_id},
            include=["metadatas"],
        )
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        return [
            {"chroma_chunk_id": ids[i], "metadata": metadatas[i]}
            for i in range(min(len(ids), len(metadatas)))
        ]
    except Exception as e:
        logger.warning(f"[Chroma] 查询文档 {document_id} 分块失败: {e}")
        return []


def count_chunks() -> int:
    """返回 Collection 中分块总数"""
    collection = get_collection()
    return collection.count()


def get_document_embeddings(document_id: int) -> list[dict[str, Any]]:
    """
    获取某文档在向量库中的全部分块嵌入 (含 chroma_chunk_id)。
    供图谱 SIMILAR_TO 质心计算使用 (Phase 6)。

    Args:
        document_id: 文档 ID

    Returns:
        [{"chroma_chunk_id": str, "embedding": List[float]}]; 失败/无数据返回 []
    """
    collection = get_collection()
    try:
        result = collection.get(
            where={"document_id": document_id},
            include=["embeddings"],
        )
        ids = result.get("ids") or []
        # 注意: chroma 返回的 embeddings 是 numpy 数组, 不能做真值判断
        # ("array or []" 会抛 "truth value of an array is ambiguous"),
        # 须用 is None + len 判断; 遍历行时同样避免直接布尔判断
        embeddings = result.get("embeddings")
        if embeddings is None or len(embeddings) == 0:
            return []
        return [
            {"chroma_chunk_id": ids[i], "embedding": emb}
            for i, emb in enumerate(embeddings[: len(ids)])
            if emb is not None and len(emb) > 0
        ]
    except Exception as e:
        logger.warning(f"[Chroma] 查询文档 {document_id} 嵌入失败: {e}")
        return []
