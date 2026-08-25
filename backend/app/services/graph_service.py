"""
知识图谱服务 — Phase 6
实体抽取 (DeepSeek JSON) / 图谱构建 / 图谱查询 / SIMILAR_TO / RAG 图谱增强

分层约束:
- 所有 Neo4j/Chroma 同步调用经 asyncio.to_thread, 禁止阻塞事件循环
- 路由仅调用本服务, 禁止路由直接操作 Neo4j
- 实体抽取在文档向量化完成后异步执行 (embedding_service 挂接), 失败不影响向量化结果
"""

import asyncio
import json
import math
import re
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.chroma_client import get_document_embeddings
from app.core.database import async_session_factory
from app.core.llm import achat_json
from app.core.neo4j_client import (
    cleanup_orphan_entities,
    count_entity,
    create_belongs_to,
    create_related_to,
    create_similar_to,
    delete_all_similar_to,
    delete_document_graph,
    delete_similar_to_of_document,
    get_entity_node,
    query_all_entity_names,
    query_edges_belongs_to,
    query_edges_mentions,
    query_edges_related_to,
    query_edges_similar_to,
    query_entity_list,
    query_entity_mention_docs,
    query_entity_neighbors,
    query_neighbors_batch,
    query_overview_categories,
    query_overview_documents,
    query_overview_entities,
    replace_document_mentions,
    upsert_category,
    upsert_document,
    upsert_entity,
)
from app.models.category import KbCategory
from app.models.document import KbDocument
from app.models.document_chunk import KbDocumentChunk
from app.schemas.graph import (
    EntityDetailResponse,
    EntityListItem,
    EntityMentionDoc,
    EntityNeighbor,
    GraphEdge,
    GraphNode,
    GraphSearchResponse,
    GraphStats,
)
from app.services.config_service import ConfigService
from app.utils.exceptions import BadRequestException, NotFoundException

# ==========================================
# 常量
# ==========================================

EXTRACT_BATCH_CHARS = 2500  # 抽取批次大小 (字符, 整块粒度聚合)
MAX_ENTITIES_PER_DOC = 300  # 单文档实体上限 (防 LLM 输出爆炸)
SIMILAR_TOP_N = 3  # SIMILAR_TO 每文档最大边数
OVERVIEW_ENTITY_LIMIT = 300  # 全景画布节点上限
OVERVIEW_DOC_LIMIT = 200
OVERVIEW_CATEGORY_LIMIT = 100
GRAPH_QUERY_EDGE_LIMIT = 3000  # 画布边查询上限
SEARCH_ENTITY_LIMIT = 50  # 搜索子图匹配实体上限
MIN_MATCH_LEN = 2  # RAG 增强实体子串匹配最小长度

# ==========================================
# 实体抽取 Prompt
# ==========================================

ENTITY_EXTRACT_SYSTEM_PROMPT = """你是企业知识库的实体抽取助手。请从给定文本中抽取实体与实体间关系, 仅输出一个 JSON 对象, 不要输出任何解释或其他内容。

输出格式 (严格遵循):
{
  "entities": [
    {"name": "实体规范名称(简洁唯一)", "type": "Person|Org|Term|Product|Policy|Event|Location",
     "description": "一句话描述(可为空字符串)", "aliases": ["别名1", "别名2"]}
  ],
  "relations": [
    {"source": "实体名(必须出现在entities中)", "target": "实体名(必须出现在entities中)",
     "relation_type": "关系类型(如: 主管/包含/相关/制定/位于)", "weight": 0.9}
  ]
}

规则:
1. 只抽取文本中明确出现的信息, 不得臆造。
2. entity.name 使用规范全称; aliases 收录文中出现的简称/别称。
3. relation.weight 取 0.0-1.0, 表示关系强度。
4. 没有实体或关系时, 对应数组输出空数组 []。"""

ENTITY_EXTRACT_USER_TEMPLATE = "请从以下文本中抽取实体和关系:\n\n{text}"

# ==========================================
# 纯函数 (pytest 直测)
# ==========================================

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def parse_extraction_json(content: str) -> dict[str, Any]:
    """
    LLM 抽取结果解析 (三级容错):
    去 markdown 围栏 → json.loads → 正则提取 {…} 兜底 → 空结构。
    任何异常都不抛出, 返回 {"entities": [], "relations": []}。
    """
    if not content or not content.strip():
        return {"entities": [], "relations": []}
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return _normalize_extraction(json.loads(text))
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if match:
            try:
                return _normalize_extraction(json.loads(match.group(0)))
            except json.JSONDecodeError:
                pass
    logger.warning(f"[图谱] JSON 解析失败, 丢弃本批: {text[:80]!r}")
    return {"entities": [], "relations": []}


def _normalize_extraction(data: Any) -> dict[str, Any]:
    """字段名/类型容错: 非 dict → 空; entities/relations 非列表 → []"""
    if not isinstance(data, dict):
        return {"entities": [], "relations": []}
    entities = data.get("entities") if isinstance(data.get("entities"), list) else []
    relations = data.get("relations") if isinstance(data.get("relations"), list) else []
    return {"entities": entities, "relations": relations}


def _safe_float(value: Any, default: float) -> float:
    """安全转 float 并钳制到 [0, 1] (关系权重)"""
    try:
        v = float(value)
        return max(0.0, min(1.0, v))
    except (TypeError, ValueError):
        return default


def build_extraction_batches(
    chunks: list[str], max_chars: int = EXTRACT_BATCH_CHARS
) -> list[str]:
    """分块聚合为抽取批次 (整块粒度, 不切断分块; 空块跳过)"""
    batches: list[str] = []
    current = ""
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not current:
            current = chunk
        elif len(current) + 1 + len(chunk) <= max_chars:
            current = current + "\n" + chunk
        else:
            batches.append(current)
            current = chunk
    if current:
        batches.append(current)
    return batches


def merge_entity_batches(batch_results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    跨批合并抽取结果:
    - 实体 name 去重 (strip 后), count 累计, aliases 并集, type/description 取首个非空
    - 关系按 (source, target) 去重, weight 取最大, 端点不在实体集合内的丢弃
    - 实体总量截断 MAX_ENTITIES_PER_DOC
    """
    entities: dict[str, dict[str, Any]] = {}
    for batch in batch_results:
        for ent in batch.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "").strip()
            if not name:
                continue
            row = entities.setdefault(
                name,
                {
                    "name": name,
                    "type": "",
                    "description": "",
                    "aliases": set(),
                    "count": 0,
                },
            )
            row["count"] += 1
            if not row["type"]:
                row["type"] = str(ent.get("type") or "").strip()
            if not row["description"]:
                row["description"] = str(ent.get("description") or "").strip()
            for alias in ent.get("aliases") or []:
                if isinstance(alias, str) and alias.strip() and alias.strip() != name:
                    row["aliases"].add(alias.strip())

    relations: dict[tuple[str, str], dict[str, Any]] = {}
    for batch in batch_results:
        for rel in batch.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            source = str(rel.get("source") or "").strip()
            target = str(rel.get("target") or "").strip()
            if not source or not target or source == target:
                continue
            if source not in entities or target not in entities:
                continue
            key = (source, target)
            weight = _safe_float(rel.get("weight"), 0.5)
            if key in relations:
                relations[key]["weight"] = max(relations[key]["weight"], weight)
                relations[key]["count"] += 1
            else:
                relations[key] = {
                    "source": source,
                    "target": target,
                    "relation_type": str(rel.get("relation_type") or "相关").strip(),
                    "weight": weight,
                    "count": 1,
                }

    entity_list = [
        {
            "name": e["name"],
            "type": e["type"] or "Term",
            "description": e["description"],
            "aliases": sorted(e["aliases"]),
            "count": e["count"],
        }
        for e in entities.values()
    ][:MAX_ENTITIES_PER_DOC]
    return {"entities": entity_list, "relations": list(relations.values())}


def find_entity_positions(chunks: list[str], names: list[str]) -> dict[str, list[int]]:
    """实体名在分块中的出现位置 (chunk_index 列表, 子串扫描)"""
    positions: dict[str, list[int]] = {}
    for name in names:
        hits = [i for i, chunk in enumerate(chunks) if name in chunk]
        if hits:
            positions[name] = hits
    return positions


def centroid_embedding(vectors: list[list[float]]) -> list[float] | None:
    """向量质心 (L2 归一化后返回, 与 Chroma cosine 空间一致); 空/维度异常 → None"""
    if not vectors:
        return None
    dim = len(vectors[0])
    if any(len(v) != dim for v in vectors):
        return None
    centroid = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in centroid))
    if not norm:
        return None
    return [x / norm for x in centroid]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个已归一化向量的余弦相似度 (点积)"""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def match_entities(
    names_with_aliases: list[dict[str, Any]],
    question: str,
    min_len: int = MIN_MATCH_LEN,
) -> list[str]:
    """问题文本与实体名/别名子串匹配 (len>=min_len), 返回命中实体 name 列表 (去重保序)"""
    matched: list[str] = []
    for row in names_with_aliases:
        candidates = [str(row.get("name") or "")]
        candidates += [str(a) for a in (row.get("aliases") or []) if a]
        for cand in candidates:
            if cand and len(cand) >= min_len and cand in question:
                matched.append(str(row["name"]))
                break
    return matched


def build_graph_context_block(matches: list[dict[str, Any]]) -> str:
    """
    图谱增强上下文文本块 (纯函数)。
    matches: [{"entity": str, "neighbors": [{"neighbor", "type", "relation_type", "weight"}]}]
    无邻居的实体跳过; 全部为空 → 返回 ""
    """
    lines = ["[知识图谱关联]"]
    for m in matches:
        neighbors = m.get("neighbors") or []
        if not neighbors:
            continue
        parts = [
            f"「{n.get('neighbor') or ''}」(关系: {n.get('relation_type') or '相关'})"
            for n in neighbors[:3]
        ]
        lines.append(f"- 与「{m['entity']}」相关的实体: {'；'.join(parts)}")
    return "\n".join(lines) if len(lines) > 1 else ""


# ==========================================
# GraphService
# ==========================================


class GraphService:
    """知识图谱业务服务"""

    # ========== 构建流水线 (BackgroundTasks 入口) ==========

    @staticmethod
    async def run_build_pipeline(document_id: int | None) -> None:
        """
        后台任务入口: 独立会话 + 全链路异常捕获 (对齐 EmbeddingService 模式)。
        失败仅记录日志, 不影响其他流程。
        """
        async with async_session_factory() as db:
            try:
                await GraphService.build_graph(db, document_id)
            except Exception as e:
                logger.exception(f"[图谱] 构建失败 document_id={document_id}: {e}")

    @staticmethod
    async def build_graph(db: AsyncSession, document_id: int | None) -> None:
        """全量重建 (document_id=None) 或单文档重建"""
        if document_id is None:
            result = await db.execute(
                select(KbDocument).where(
                    KbDocument.status == 1,
                    KbDocument.vector_status == "completed",
                )
            )
            docs = list(result.scalars().all())
            if not docs:
                logger.info("[图谱] 无已完成向量化的文档, 跳过构建")
                return
            await asyncio.to_thread(delete_all_similar_to)
            for doc in docs:
                await GraphService._rebuild_document_graph(db, doc)
            await GraphService._rebuild_all_similar_to(db, docs)
            await asyncio.to_thread(cleanup_orphan_entities)
            logger.info(f"[图谱] 全量重建完成: {len(docs)} 个文档")
        else:
            await GraphService.validate_build_request(db, document_id)
            # 注意: 变量名不与全量分支的循环变量 doc 同名 (mypy 推断冲突)
            target_doc = await db.get(KbDocument, document_id)
            if target_doc is None:  # 校验通过后理论上不会发生, 防御性兜底
                raise NotFoundException("文档不存在或已删除")
            await GraphService._rebuild_document_graph(db, target_doc)
            await GraphService._update_similar_for_document(db, target_doc)
            await asyncio.to_thread(cleanup_orphan_entities)
            logger.info(f"[图谱] 单文档重建完成: {document_id}")

    @staticmethod
    async def validate_build_request(db: AsyncSession, document_id: int) -> None:
        """构建前校验 (API 层提前返回 404/400)"""
        doc = await db.get(KbDocument, document_id)
        if doc is None or doc.status == -1:
            raise NotFoundException("文档不存在或已删除")
        if doc.vector_status != "completed":
            raise BadRequestException("文档尚未完成向量化, 无法构建图谱")

    @staticmethod
    async def _rebuild_document_graph(
        db: AsyncSession, doc: KbDocument, chunk_texts: list[str] | None = None
    ) -> None:
        """单文档重建: 分块文本 → LLM 分批抽取 → 合并 → Neo4j 写入"""
        if chunk_texts is None:
            chunk_rows = (
                await db.execute(
                    select(KbDocumentChunk.chunk_text)
                    .where(KbDocumentChunk.document_id == doc.id)
                    .order_by(KbDocumentChunk.chunk_index.asc())
                )
            ).scalars()
            chunks = list(chunk_rows)
        else:
            chunks = [c.strip() for c in chunk_texts if c and c.strip()]

        if not chunks:
            logger.warning(f"[图谱] 文档 {doc.id} 无分块记录, 跳过")
            return

        batches = build_extraction_batches(chunks)
        batch_results: list[dict[str, Any]] = []
        for i, batch in enumerate(batches):
            try:
                batch_results.append(await GraphService._extract_batch(batch))
            except Exception as e:
                # 单批失败不影响其他批次 (坏批丢弃)
                logger.warning(f"[图谱] 文档 {doc.id} 第 {i + 1} 批抽取失败: {e}")
                batch_results.append({"entities": [], "relations": []})

        merged = merge_entity_batches(batch_results)
        entities = merged["entities"]
        relations = merged["relations"]
        positions = find_entity_positions(chunks, [e["name"] for e in entities])
        mentions = [
            {
                "name": e["name"],
                "count": e["count"],
                "positions": positions.get(e["name"], []),
            }
            for e in entities
        ]

        category = await db.get(KbCategory, doc.category_id)
        await asyncio.to_thread(
            GraphService._write_document_graph,
            doc,
            category,
            entities,
            relations,
            mentions,
        )
        logger.info(
            f"[图谱] 文档 {doc.id} 抽取完成: {len(entities)} 实体, "
            f"{len(relations)} 关系, {len(batches)} 批"
        )

    @staticmethod
    async def _extract_batch(text: str) -> dict[str, Any]:
        """
        单批 LLM 抽取: json_object 模式尝试 → 端点不支持时降级普通调用 → 容错解析。
        调用失败抛出 RuntimeError, 由 _rebuild_document_graph 逐批捕获。
        """
        messages = [
            {"role": "system", "content": ENTITY_EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": ENTITY_EXTRACT_USER_TEMPLATE.format(text=text)},
        ]
        try:
            content = await achat_json(messages, response_format="json_object")
        except RuntimeError as e:
            logger.warning(f"[图谱] json_object 模式失败, 降级普通调用: {e}")
            content = await achat_json(messages)
        return parse_extraction_json(content)

    @staticmethod
    def _write_document_graph(
        doc: KbDocument,
        category: KbCategory | None,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        mentions: list[dict[str, Any]],
    ) -> None:
        """Neo4j 写入 (同步函数, 必须在 asyncio.to_thread 中调用)"""
        upsert_document(doc.id, doc.title, doc.file_name)
        if category is not None:
            upsert_category(category.id, category.name)
            create_belongs_to(doc.id, category.id)
        for e in entities:
            upsert_entity(e["name"], e["type"], e["description"], e["aliases"])
        # 空列表同样调用: 重新抽取后实体可能减少, 旧 MENTIONS 必须清掉
        replace_document_mentions(doc.id, mentions)
        for rel in relations:
            try:
                create_related_to(
                    rel["source"], rel["target"], rel["weight"], rel["relation_type"]
                )
            except Exception as e:
                logger.warning(
                    f"[图谱] 关系写入失败 {rel['source']}->{rel['target']}: {e}"
                )

    @staticmethod
    async def extract_document_after_vectorize(
        db: AsyncSession, doc: KbDocument, chunks: list[str]
    ) -> None:
        """向量化完成后钩子: 抽取 + 写图谱 + 更新该文档 SIMILAR_TO"""
        await GraphService._rebuild_document_graph(db, doc, chunk_texts=chunks)
        await GraphService._update_similar_for_document(db, doc)

    # ========== SIMILAR_TO ==========

    @staticmethod
    async def _rebuild_all_similar_to(db: AsyncSession, docs: list[KbDocument]) -> None:
        """全量重建 SIMILAR_TO: 已删全部旧边, 逐文档计算 top3 (id 升序写入去重)"""
        threshold = float(
            await ConfigService.get_value(
                db,
                "graph_similarity_threshold",
                settings.DEFAULT_GRAPH_SIMILARITY_THRESHOLD,
            )
            or 0
        )
        for doc in docs:
            await GraphService._update_similar_for_document(
                db, doc, threshold=threshold
            )

    @staticmethod
    async def _update_similar_for_document(
        db: AsyncSession, doc: KbDocument, threshold: float | None = None
    ) -> None:
        """单文档: 删旧 SIMILAR_TO 边 → 与其他 completed 文档质心余弦 → 阈值过滤 → top3"""
        if threshold is None:
            threshold = float(
                await ConfigService.get_value(
                    db,
                    "graph_similarity_threshold",
                    settings.DEFAULT_GRAPH_SIMILARITY_THRESHOLD,
                )
                or 0
            )
        my_centroid = centroid_embedding(
            [
                r["embedding"]
                for r in await asyncio.to_thread(get_document_embeddings, doc.id)
            ]
        )
        if my_centroid is None:
            logger.warning(f"[图谱] 文档 {doc.id} 无嵌入, 跳过 SIMILAR_TO")
            return

        other_ids = (
            await db.execute(
                select(KbDocument.id).where(
                    KbDocument.status == 1,
                    KbDocument.vector_status == "completed",
                    KbDocument.id != doc.id,
                )
            )
        ).scalars()
        await asyncio.to_thread(delete_similar_to_of_document, doc.id)

        scored: list[tuple[int, float]] = []
        for other_id in other_ids:
            other_centroid = centroid_embedding(
                [
                    r["embedding"]
                    for r in await asyncio.to_thread(get_document_embeddings, other_id)
                ]
            )
            if other_centroid is None:
                continue
            score = cosine_similarity(my_centroid, other_centroid)
            if score >= threshold:
                scored.append((other_id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        for other_id, score in scored[:SIMILAR_TOP_N]:
            await asyncio.to_thread(
                create_similar_to,
                min(doc.id, other_id),
                max(doc.id, other_id),
                float(round(score, 4)),
            )
        logger.info(
            f"[图谱] 文档 {doc.id} SIMILAR_TO 更新: {len(scored[:SIMILAR_TOP_N])} 条"
        )

    # ========== 图谱查询 (api/v1/graph.py 调用) ==========

    @staticmethod
    async def list_entities(
        db: AsyncSession,
        page: int,
        page_size: int,
        keyword: str | None,
        entity_type: str | None,
    ) -> tuple[list[EntityListItem], int]:
        """实体分页列表: 2 次 Neo4j 查询 (count + page)"""
        total = await asyncio.to_thread(count_entity, keyword, entity_type)
        rows = await asyncio.to_thread(
            query_entity_list,
            keyword,
            entity_type,
            (page - 1) * page_size,
            page_size,
        )
        items = [
            EntityListItem(
                name=r["name"],
                type=r.get("type") or "Term",
                description=r.get("description") or "",
                aliases=r.get("aliases") or [],
                mention_count=int(r.get("mention_count") or 0),
            )
            for r in rows
        ]
        return items, total

    @staticmethod
    async def get_entity_detail(db: AsyncSession, name: str) -> EntityDetailResponse:
        """实体详情: 节点属性 + RELATED_TO 邻居 + 提及文档"""
        node = await asyncio.to_thread(get_entity_node, name)
        if node is None:
            raise NotFoundException(f"实体不存在: {name}")
        neighbors = await asyncio.to_thread(query_entity_neighbors, name, 50)
        docs = await asyncio.to_thread(query_entity_mention_docs, name, 20)
        return EntityDetailResponse(
            name=node["name"],
            type=node.get("type") or "Term",
            description=node.get("description") or "",
            aliases=node.get("aliases") or [],
            mention_count=int(node.get("mention_count") or 0),
            neighbors=[
                EntityNeighbor(
                    name=n["name"],
                    type=n.get("type") or "Term",
                    description=n.get("description") or "",
                    aliases=n.get("aliases") or [],
                    relation_type=n.get("relation_type") or "相关",
                    weight=float(n.get("weight") or 0),
                )
                for n in neighbors
            ],
            documents=[
                EntityMentionDoc(
                    document_id=d["document_id"],
                    title=d.get("title") or "",
                    file_name=d.get("file_name") or "",
                    count=int(d.get("count") or 0),
                    positions=list(d.get("positions") or []),
                )
                for d in docs
            ],
        )

    @staticmethod
    async def search_graph(
        db: AsyncSession, keyword: str | None
    ) -> GraphSearchResponse:
        """keyword 无 → 画布全景; 有 → 匹配实体及其邻居/文档子图"""
        if not keyword:
            return await GraphService._overview()
        return await GraphService._search_subgraph(keyword)

    @staticmethod
    async def _overview() -> GraphSearchResponse:
        """画布全景: 三类节点 + 全部边类型 + 截断标志"""
        entities = await asyncio.to_thread(
            query_overview_entities, OVERVIEW_ENTITY_LIMIT
        )
        docs = await asyncio.to_thread(query_overview_documents, OVERVIEW_DOC_LIMIT)
        cats = await asyncio.to_thread(
            query_overview_categories, OVERVIEW_CATEGORY_LIMIT
        )
        entity_names = [e["name"] for e in entities]
        doc_ids = [d["document_id"] for d in docs]
        cat_ids = [c["category_id"] for c in cats]

        related_edges = await asyncio.to_thread(
            query_edges_related_to, entity_names, GRAPH_QUERY_EDGE_LIMIT
        )
        mention_edges = await asyncio.to_thread(
            query_edges_mentions, doc_ids, entity_names, GRAPH_QUERY_EDGE_LIMIT
        )
        belongs_edges = await asyncio.to_thread(
            query_edges_belongs_to, doc_ids, cat_ids, GRAPH_QUERY_EDGE_LIMIT
        )
        similar_edges = await asyncio.to_thread(
            query_edges_similar_to, doc_ids, GRAPH_QUERY_EDGE_LIMIT
        )

        nodes: list[GraphNode] = []
        for e in entities:
            nodes.append(
                GraphNode(
                    id=e["name"],
                    node_type="Entity",
                    label=e["name"],
                    type=e.get("type") or "Term",
                    description=e.get("description") or "",
                    aliases=e.get("aliases") or [],
                    mention_count=int(e.get("mention_count") or 0),
                )
            )
        for d in docs:
            nodes.append(
                GraphNode(
                    id=f"doc_{d['document_id']}",
                    node_type="Document",
                    label=d.get("title") or "",
                    document_id=d["document_id"],
                    title=d.get("title") or "",
                    file_name=d.get("file_name") or "",
                    category_id=d.get("category_id"),
                    category_name=d.get("category_name"),
                )
            )
        for c in cats:
            nodes.append(
                GraphNode(
                    id=f"cat_{c['category_id']}",
                    node_type="Category",
                    label=c.get("name") or "",
                    category_id=c["category_id"],
                    category_name=c.get("name") or "",
                )
            )

        edges: list[GraphEdge] = []
        for r in related_edges:
            edges.append(
                GraphEdge(
                    source=r["source"],
                    target=r["target"],
                    edge_type="RELATED_TO",
                    relation_type=r.get("relation_type"),
                    weight=r.get("weight"),
                )
            )
        for r in mention_edges:
            edges.append(
                GraphEdge(
                    source=f"doc_{r['document_id']}",
                    target=r["entity_name"],
                    edge_type="MENTIONS",
                    count=int(r.get("count") or 0),
                )
            )
        for r in belongs_edges:
            edges.append(
                GraphEdge(
                    source=f"doc_{r['document_id']}",
                    target=f"cat_{r['category_id']}",
                    edge_type="BELONGS_TO",
                )
            )
        for r in similar_edges:
            edges.append(
                GraphEdge(
                    source=f"doc_{r['source']}",
                    target=f"doc_{r['target']}",
                    edge_type="SIMILAR_TO",
                    score=r.get("score"),
                )
            )

        truncated = (
            len(entities) >= OVERVIEW_ENTITY_LIMIT or len(docs) >= OVERVIEW_DOC_LIMIT
        )
        return GraphSearchResponse(
            nodes=nodes,
            edges=edges,
            stats=GraphService._count_stats(nodes, edges),
            truncated=truncated,
        )

    @staticmethod
    async def _search_subgraph(keyword: str) -> GraphSearchResponse:
        """搜索子图: 匹配实体 + 一跳邻居 + 提及文档 (RELATED_TO + MENTIONS 边)"""
        matched = await asyncio.to_thread(
            query_entity_list, keyword, None, 0, SEARCH_ENTITY_LIMIT
        )
        names = [m["name"] for m in matched]
        neighbor_rows = (
            await asyncio.to_thread(query_neighbors_batch, names, 500) if names else []
        )
        neighbor_names: dict[str, dict[str, Any]] = {}
        for r in neighbor_rows:
            nb = r.get("neighbor")
            if nb and nb not in neighbor_names and nb not in names:
                neighbor_names[nb] = r

        docs_by_id: dict[int, dict[str, Any]] = {}
        for m in matched[:10]:
            for d in await asyncio.to_thread(query_entity_mention_docs, m["name"], 5):
                docs_by_id.setdefault(d["document_id"], d)

        visible_names = names + list(neighbor_names.keys())
        doc_ids = list(docs_by_id.keys())

        nodes: list[GraphNode] = []
        for m in matched:
            nodes.append(
                GraphNode(
                    id=m["name"],
                    node_type="Entity",
                    label=m["name"],
                    type=m.get("type") or "Term",
                    description=m.get("description") or "",
                    aliases=m.get("aliases") or [],
                    mention_count=int(m.get("mention_count") or 0),
                )
            )
        for nb_name, nb in neighbor_names.items():
            nodes.append(
                GraphNode(
                    id=nb_name,
                    node_type="Entity",
                    label=nb_name,
                    type=nb.get("type") or "Term",
                    description=nb.get("description") or "",
                    aliases=nb.get("aliases") or [],
                )
            )
        for d in docs_by_id.values():
            nodes.append(
                GraphNode(
                    id=f"doc_{d['document_id']}",
                    node_type="Document",
                    label=d.get("title") or "",
                    document_id=d["document_id"],
                    title=d.get("title") or "",
                    file_name=d.get("file_name") or "",
                )
            )

        edges: list[GraphEdge] = []
        for r in await asyncio.to_thread(
            query_edges_related_to, visible_names, GRAPH_QUERY_EDGE_LIMIT
        ):
            edges.append(
                GraphEdge(
                    source=r["source"],
                    target=r["target"],
                    edge_type="RELATED_TO",
                    relation_type=r.get("relation_type"),
                    weight=r.get("weight"),
                )
            )
        for r in await asyncio.to_thread(
            query_edges_mentions, doc_ids, visible_names, GRAPH_QUERY_EDGE_LIMIT
        ):
            edges.append(
                GraphEdge(
                    source=f"doc_{r['document_id']}",
                    target=r["entity_name"],
                    edge_type="MENTIONS",
                    count=int(r.get("count") or 0),
                )
            )

        return GraphSearchResponse(
            nodes=nodes,
            edges=edges,
            stats=GraphService._count_stats(nodes, edges),
            truncated=len(matched) >= SEARCH_ENTITY_LIMIT,
        )

    @staticmethod
    def _count_stats(nodes: list[GraphNode], edges: list[GraphEdge]) -> GraphStats:
        """按响应内实际节点/边类型计数 (全景与搜索子图通用)"""
        entity_count = sum(1 for n in nodes if n.node_type == "Entity")
        document_count = sum(1 for n in nodes if n.node_type == "Document")
        category_count = sum(1 for n in nodes if n.node_type == "Category")
        return GraphStats(
            entity_count=entity_count,
            document_count=document_count,
            category_count=category_count,
            related_to_count=sum(1 for e in edges if e.edge_type == "RELATED_TO"),
            mentions_count=sum(1 for e in edges if e.edge_type == "MENTIONS"),
            similar_to_count=sum(1 for e in edges if e.edge_type == "SIMILAR_TO"),
        )

    # ========== RAG 图谱增强 (rag_service 调用) ==========

    @staticmethod
    async def build_graph_context(question: str, top_k: int) -> str:
        """
        图谱增强: 全量实体名/别名子串匹配问题 → 命中实体取 RELATED_TO 一跳邻居
        (每实体 top_k) → 组装文本块。无命中/无邻居 → 返回 ""
        """
        if not question or not question.strip():
            return ""
        names = await asyncio.to_thread(query_all_entity_names)
        matched = match_entities(names, question)
        if not matched:
            return ""
        rows = await asyncio.to_thread(query_neighbors_batch, matched, top_k * 20)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            ent = r.get("entity")
            if not ent:
                continue
            lst = grouped.setdefault(ent, [])
            if len(lst) < top_k:
                lst.append(r)
        matches = [
            {"entity": name, "neighbors": grouped[name]}
            for name in matched
            if grouped.get(name)
        ]
        return build_graph_context_block(matches)

    # ========== 文档删除同步 (document_service 调用) ==========

    @staticmethod
    async def cleanup_document_graph(document_id: int) -> None:
        """软删除同步清理 (同步函数包线程, 调用方再包 try/except 仅告警)"""
        await asyncio.to_thread(delete_document_graph, document_id)
