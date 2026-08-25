"""
Neo4j 图数据库驱动封装
提供连接管理、Cypher 执行、图谱操作
"""

from typing import Any

from loguru import logger
from neo4j import Driver, GraphDatabase, Result, Session

from app.config import settings

# 全局单例 Driver
_driver: Driver | None = None


def get_neo4j_driver() -> Driver:
    """
    获取 Neo4j Driver 单例。
    使用 Bolt 协议连接，连接池配置来自 settings。
    """
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
            max_connection_lifetime=settings.NEO4J_MAX_CONNECTION_LIFETIME,
            max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
        )
        # 验证连接
        try:
            _driver.verify_connectivity()
            logger.info(f"[Neo4j] 连接成功: {settings.NEO4J_URI}")
        except Exception as e:
            logger.error(f"[Neo4j] 连接失败: {e}")
            raise
    return _driver


def close_neo4j_driver() -> None:
    """关闭 Neo4j 驱动连接"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("[Neo4j] 驱动已关闭")


def run_cypher(
    query: str,
    params: dict[str, Any] | None = None,
    db: str | None = None,
) -> list[dict[str, Any]]:
    """
    执行 Cypher 查询并返回结果列表。

    Args:
        query: Cypher 查询语句
        params: 查询参数 (参数化查询防止注入)
        db: 数据库名，默认使用配置中的 database

    Returns:
        查询结果列表，每条记录转为 dict
    """
    driver = get_neo4j_driver()
    database = db or settings.NEO4J_DATABASE

    with driver.session(database=database) as session:
        result: Result = session.run(query, parameters=params or {})
        records = [record.data() for record in result]
        return records


def get_session() -> Session:
    """
    获取 Neo4j 原生 Session，用于事务性操作。
    调用方需自行关闭 session。
    """
    driver = get_neo4j_driver()
    return driver.session(database=settings.NEO4J_DATABASE)


# ==========================================
# 图谱初始化 (Phase 1 基础)
# ==========================================


def init_graph_constraints() -> None:
    """
    初始化 Neo4j 约束 (Phase 6 补全)。
    - Entity 节点 name 唯一约束
    - Document 节点 document_id 唯一约束
    - Category 节点 category_id 唯一约束

    注意: 只建唯一约束 — Neo4j Community Edition 不支持属性存在性约束
    (Enterprise 专有, 会报 ConstraintCreationFailed);
    唯一约束本身已隐含属性必须存在, 存在性约束冗余。
    """
    constraints = [
        (
            "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
        ),
        (
            "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
            "FOR (d:Document) REQUIRE d.document_id IS UNIQUE"
        ),
        (
            "CREATE CONSTRAINT category_id_unique IF NOT EXISTS "
            "FOR (c:Category) REQUIRE c.category_id IS UNIQUE"
        ),
    ]

    for cypher in constraints:
        try:
            run_cypher(cypher)
            logger.debug(f"[Neo4j] 执行约束: {cypher[:60]}...")
        except Exception as e:
            logger.warning(f"[Neo4j] 约束执行异常 (可能已存在): {e}")

    logger.info("[Neo4j] 图谱约束初始化完成")


# ==========================================
# 节点写入 (Phase 6)
# 注意: 以下函数全部为同步函数, 调用方必须经 asyncio.to_thread 执行
# ==========================================


def upsert_entity(name: str, type_: str, description: str, aliases: list[str]) -> None:
    """
    MERGE 实体节点; 新数据为空值时保留库中旧值 (幂等)。
    别名跨文档累计: 后抽取批次别名更少时不清空已累计别名。
    """
    run_cypher(
        """
        MERGE (e:Entity {name: $name})
        SET e.type = CASE WHEN $type IS NOT NULL AND $type <> '' THEN $type ELSE e.type END,
            e.description = CASE WHEN $description IS NOT NULL AND $description <> ''
                                 THEN $description ELSE e.description END,
            e.aliases = CASE WHEN $aliases IS NOT NULL AND size($aliases) > 0
                             THEN $aliases ELSE e.aliases END
        """,
        {"name": name, "type": type_, "description": description, "aliases": aliases},
    )


def upsert_document(document_id: int, title: str, file_name: str) -> None:
    """MERGE 文档节点 (document_id 映射 MySQL kb_document.id)"""
    run_cypher(
        "MERGE (d:Document {document_id: $document_id}) "
        "SET d.title = $title, d.file_name = $file_name",
        {"document_id": document_id, "title": title, "file_name": file_name},
    )


def upsert_category(category_id: int, name: str) -> None:
    """MERGE 分类节点 (category_id 映射 MySQL kb_category.id)"""
    run_cypher(
        "MERGE (c:Category {category_id: $category_id}) SET c.name = $name",
        {"category_id": category_id, "name": name},
    )


# ==========================================
# 关系写入 (Phase 6)
# ==========================================


def create_belongs_to(document_id: int, category_id: int) -> None:
    """创建 BELONGS_TO 关系 (Document → Category)"""
    run_cypher(
        """
        MATCH (d:Document {document_id: $document_id})
        MATCH (c:Category {category_id: $category_id})
        MERGE (d)-[:BELONGS_TO]->(c)
        """,
        {"document_id": document_id, "category_id": category_id},
    )


def replace_document_mentions(document_id: int, mentions: list[dict]) -> None:
    """
    重建某文档的 MENTIONS 关系 (Document → Entity):
    先删该文档全部旧 MENTIONS, 再按 UNWIND 批量创建 (单语句原子执行)。
    mentions 为空列表时仅清旧边 (重新抽取后实体可能减少)。
    mentions: [{"name", "count", "positions"}], 实体节点须已存在。
    """
    run_cypher(
        """
        MATCH (d:Document {document_id: $document_id})
        OPTIONAL MATCH (d)-[m:MENTIONS]->(:Entity)
        DELETE m
        WITH d
        UNWIND $mentions AS mention
        MATCH (e:Entity {name: mention.name})
        MERGE (d)-[m2:MENTIONS]->(e)
        SET m2.count = mention.count, m2.positions = mention.positions
        """,
        {"document_id": document_id, "mentions": mentions},
    )


def create_related_to(
    source: str, target: str, weight: float, relation_type: str
) -> None:
    """创建 RELATED_TO 关系 (Entity → Entity)"""
    run_cypher(
        """
        MATCH (a:Entity {name: $source}), (b:Entity {name: $target})
        MERGE (a)-[r:RELATED_TO]->(b)
        SET r.weight = $weight, r.relation_type = $relation_type
        """,
        {
            "source": source,
            "target": target,
            "weight": weight,
            "relation_type": relation_type,
        },
    )


def create_similar_to(document_id: int, other_id: int, score: float) -> None:
    """创建 SIMILAR_TO 关系 (Document ↔ Document, 无向);
    调用方保证 document_id < other_id 以避免双向重复边"""
    run_cypher(
        """
        MATCH (a:Document {document_id: $a}), (b:Document {document_id: $b})
        MERGE (a)-[r:SIMILAR_TO]-(b)
        SET r.score = $score
        """,
        {"a": document_id, "b": other_id, "score": score},
    )


def delete_similar_to_of_document(document_id: int) -> None:
    """删除某文档的全部 SIMILAR_TO 边 (重建前调用)"""
    run_cypher(
        "MATCH (:Document {document_id: $document_id})-[r:SIMILAR_TO]-() DELETE r",
        {"document_id": document_id},
    )


def delete_all_similar_to() -> None:
    """删除全部 SIMILAR_TO 边 (全量重建前调用)"""
    run_cypher("MATCH (:Document)-[r:SIMILAR_TO]-(:Document) DELETE r")


def delete_document_graph(document_id: int) -> None:
    """
    软删除同步清理: DETACH 删除文档节点 (连带 MENTIONS/BELONGS_TO/SIMILAR_TO 边),
    随后清理不再被任何文档提及的孤儿实体。
    """
    run_cypher(
        "MATCH (d:Document {document_id: $document_id}) DETACH DELETE d",
        {"document_id": document_id},
    )
    cleanup_orphan_entities()


def cleanup_orphan_entities() -> None:
    """清理孤儿实体: 不再被任何文档 MENTIONS 的 Entity 节点及其边 (重建后调用)"""
    run_cypher("MATCH (e:Entity) WHERE NOT (e)<-[:MENTIONS]-() DETACH DELETE e")


# ==========================================
# 图谱查询 (Phase 6)
# ==========================================


def query_entity_list(
    keyword: str | None,
    type_: str | None,
    skip: int,
    limit: int,
) -> list[dict[str, Any]]:
    """实体分页列表: keyword 匹配 name/aliases/description, type 过滤, 按提及次数降序"""
    return run_cypher(
        """
        MATCH (e:Entity)
        WHERE ($keyword IS NULL OR e.name CONTAINS $keyword
               OR any(a IN coalesce(e.aliases, []) WHERE a CONTAINS $keyword)
               OR coalesce(e.description, '') CONTAINS $keyword)
          AND ($type IS NULL OR e.type = $type)
        OPTIONAL MATCH (e)<-[m:MENTIONS]-()
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.aliases AS aliases, count(m) AS mention_count
        ORDER BY mention_count DESC, e.name ASC
        SKIP $skip LIMIT $limit
        """,
        {"keyword": keyword, "type": type_, "skip": skip, "limit": limit},
    )


def count_entity(keyword: str | None, type_: str | None) -> int:
    """实体总数 (与 query_entity_list 同条件)"""
    rows = run_cypher(
        """
        MATCH (e:Entity)
        WHERE ($keyword IS NULL OR e.name CONTAINS $keyword
               OR any(a IN coalesce(e.aliases, []) WHERE a CONTAINS $keyword)
               OR coalesce(e.description, '') CONTAINS $keyword)
          AND ($type IS NULL OR e.type = $type)
        RETURN count(e) AS total
        """,
        {"keyword": keyword, "type": type_},
    )
    return int(rows[0]["total"] or 0) if rows else 0


def get_entity_node(name: str) -> dict[str, Any] | None:
    """按 name 精确查询实体节点 (含 MENTIONS 提及次数)"""
    rows = run_cypher(
        """
        MATCH (e:Entity {name: $name})
        OPTIONAL MATCH (e)<-[m:MENTIONS]-()
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.aliases AS aliases, count(m) AS mention_count
        """,
        {"name": name},
    )
    return rows[0] if rows else None


def query_entity_neighbors(name: str, limit: int = 50) -> list[dict[str, Any]]:
    """实体的一跳 RELATED_TO 邻居 (含关系类型与权重, 按权重降序)"""
    return run_cypher(
        """
        MATCH (e:Entity {name: $name})-[r:RELATED_TO]-(n:Entity)
        RETURN n.name AS name, n.type AS type, n.description AS description,
               n.aliases AS aliases, r.relation_type AS relation_type, r.weight AS weight
        ORDER BY r.weight DESC
        LIMIT $limit
        """,
        {"name": name, "limit": limit},
    )


def query_entity_mention_docs(name: str, limit: int = 20) -> list[dict[str, Any]]:
    """提及某实体的文档列表 (按提及次数降序)"""
    return run_cypher(
        """
        MATCH (e:Entity {name: $name})<-[m:MENTIONS]-(d:Document)
        RETURN d.document_id AS document_id, d.title AS title, d.file_name AS file_name,
               m.count AS count, m.positions AS positions
        ORDER BY m.count DESC
        LIMIT $limit
        """,
        {"name": name, "limit": limit},
    )


def query_overview_entities(limit: int) -> list[dict[str, Any]]:
    """全景画布实体节点 (按提及次数降序, 截断)"""
    return run_cypher(
        """
        MATCH (e:Entity)
        OPTIONAL MATCH (e)<-[m:MENTIONS]-()
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.aliases AS aliases, count(m) AS mention_count
        ORDER BY mention_count DESC
        LIMIT $limit
        """,
        {"limit": limit},
    )


def query_overview_documents(limit: int) -> list[dict[str, Any]]:
    """全景画布文档节点 (含所属分类)"""
    return run_cypher(
        """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:BELONGS_TO]->(c:Category)
        RETURN d.document_id AS document_id, d.title AS title, d.file_name AS file_name,
               c.category_id AS category_id, c.name AS category_name
        LIMIT $limit
        """,
        {"limit": limit},
    )


def query_overview_categories(limit: int) -> list[dict[str, Any]]:
    """全景画布分类节点"""
    return run_cypher(
        "MATCH (c:Category) RETURN c.category_id AS category_id, c.name AS name LIMIT $limit",
        {"limit": limit},
    )


def query_edges_related_to(entity_names: list[str], limit: int) -> list[dict[str, Any]]:
    """可见实体之间的 RELATED_TO 边"""
    return run_cypher(
        """
        MATCH (a:Entity)-[r:RELATED_TO]-(b:Entity)
        WHERE a.name IN $names AND b.name IN $names
        RETURN a.name AS source, b.name AS target,
               r.relation_type AS relation_type, r.weight AS weight
        LIMIT $limit
        """,
        {"names": entity_names, "limit": limit},
    )


def query_edges_mentions(
    document_ids: list[int], entity_names: list[str], limit: int
) -> list[dict[str, Any]]:
    """可见文档与可见实体之间的 MENTIONS 边"""
    return run_cypher(
        """
        MATCH (d:Document)-[m:MENTIONS]->(e:Entity)
        WHERE d.document_id IN $doc_ids AND e.name IN $names
        RETURN d.document_id AS document_id, e.name AS entity_name,
               m.count AS count, m.positions AS positions
        LIMIT $limit
        """,
        {"doc_ids": document_ids, "names": entity_names, "limit": limit},
    )


def query_edges_belongs_to(
    document_ids: list[int], category_ids: list[int], limit: int
) -> list[dict[str, Any]]:
    """可见文档与可见分类之间的 BELONGS_TO 边"""
    return run_cypher(
        """
        MATCH (d:Document)-[:BELONGS_TO]->(c:Category)
        WHERE d.document_id IN $doc_ids AND c.category_id IN $cat_ids
        RETURN d.document_id AS document_id, c.category_id AS category_id
        LIMIT $limit
        """,
        {"doc_ids": document_ids, "cat_ids": category_ids, "limit": limit},
    )


def query_edges_similar_to(document_ids: list[int], limit: int) -> list[dict[str, Any]]:
    """
    可见文档之间的 SIMILAR_TO 边。
    无向边按 a.document_id < b.document_id 过滤去重
    (写入侧 create_similar_to 保证 min<max 不变量)。
    """
    return run_cypher(
        """
        MATCH (a:Document)-[r:SIMILAR_TO]-(b:Document)
        WHERE a.document_id IN $doc_ids AND b.document_id IN $doc_ids
          AND a.document_id < b.document_id
        RETURN a.document_id AS source, b.document_id AS target, r.score AS score
        LIMIT $limit
        """,
        {"doc_ids": document_ids, "limit": limit},
    )


def query_all_entity_names(limit: int = 3000) -> list[dict[str, Any]]:
    """全量实体名+别名 (RAG 图谱增强用, 子串匹配在 Python 侧完成)"""
    return run_cypher(
        "MATCH (e:Entity) RETURN e.name AS name, e.aliases AS aliases LIMIT $limit",
        {"limit": limit},
    )


def query_neighbors_batch(names: list[str], limit: int) -> list[dict[str, Any]]:
    """批量查询实体的一跳 RELATED_TO 邻居 (图谱增强/子图搜索共用)"""
    if not names:
        return []
    return run_cypher(
        """
        MATCH (e:Entity)-[r:RELATED_TO]-(n:Entity)
        WHERE e.name IN $names
        RETURN e.name AS entity, n.name AS neighbor, n.type AS type,
               n.description AS description, r.relation_type AS relation_type, r.weight AS weight
        ORDER BY r.weight DESC
        LIMIT $limit
        """,
        {"names": names, "limit": limit},
    )
