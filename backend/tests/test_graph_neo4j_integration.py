"""
Phase 6 Neo4j 集成往返测试 (默认跳过)

需要真实 Neo4j 服务, VM 上按需运行:
  NEO4J_TEST_URI=bolt://127.0.0.1:7687 NEO4J_TEST_USER=neo4j \
  NEO4J_TEST_PASSWORD=neo4j123456 pytest tests/test_graph_neo4j_integration.py -v

使用独立前缀的测试数据 (实体名 测试实体_P6_*, document_id 999xxx),
测试结束自行清理, 不污染业务数据。
"""

import os

import pytest

NEO4J_TEST_URI = os.environ.get("NEO4J_TEST_URI")

pytestmark = pytest.mark.skipif(
    not NEO4J_TEST_URI,
    reason="Neo4j 集成测试需要 NEO4J_TEST_URI/NEO4J_TEST_USER/NEO4J_TEST_PASSWORD 环境变量",
)

_TEST_ENTITY_A = "测试实体_P6_IT_A"
_TEST_ENTITY_B = "测试实体_P6_IT_B"
_TEST_ENTITY_C = "测试实体_P6_IT_C"
_TEST_DOC_1 = 999001
_TEST_DOC_2 = 999002


@pytest.fixture(autouse=True)
def _patch_neo4j_settings(monkeypatch):
    """将 neo4j_client 的连接参数指向环境变量配置的测试库"""
    from app.config import settings

    monkeypatch.setattr(settings, "NEO4J_URI", NEO4J_TEST_URI)
    monkeypatch.setattr(
        settings, "NEO4J_USERNAME", os.environ.get("NEO4J_TEST_USER", "neo4j")
    )
    monkeypatch.setattr(
        settings, "NEO4J_PASSWORD", os.environ.get("NEO4J_TEST_PASSWORD", "neo4j123456")
    )


def _cleanup() -> None:
    """清理本文件全部测试数据"""
    from app.core.neo4j_client import run_cypher

    run_cypher(
        "MATCH (d:Document) WHERE d.document_id IN $ids DETACH DELETE d",
        {"ids": [_TEST_DOC_1, _TEST_DOC_2]},
    )
    run_cypher(
        "MATCH (e:Entity) WHERE e.name STARTS WITH '测试实体_P6_IT' DETACH DELETE e"
    )


@pytest.fixture(autouse=True)
def _clean_before_after():
    """每个用例前后清理, 保证独立"""
    _cleanup()
    yield
    _cleanup()


class TestNeo4jRoundtrip:
    def test_upsert_entity_idempotent(self):
        """两次 upsert: 第二次空值保留旧值 (幂等)"""
        from app.core.neo4j_client import get_entity_node, upsert_entity

        upsert_entity(_TEST_ENTITY_A, "Term", "描述A", ["别名A"])
        upsert_entity(_TEST_ENTITY_A, "", "", [])
        node = get_entity_node(_TEST_ENTITY_A)
        assert node is not None
        assert node["type"] == "Term"
        assert node["description"] == "描述A"
        assert node["aliases"] == ["别名A"]

    def test_mentions_roundtrip(self):
        """文档节点 + MENTIONS 往返: 写入 → 实体提及文档查询可见"""
        from app.core.neo4j_client import (
            query_entity_mention_docs,
            replace_document_mentions,
            upsert_document,
            upsert_entity,
        )

        upsert_document(_TEST_DOC_1, "集成测试文档", "it_test.txt")
        upsert_entity(_TEST_ENTITY_A, "Term", "", [])
        replace_document_mentions(
            _TEST_DOC_1,
            [{"name": _TEST_ENTITY_A, "count": 3, "positions": [0, 1, 2]}],
        )

        docs = query_entity_mention_docs(_TEST_ENTITY_A)
        hit = [d for d in docs if d["document_id"] == _TEST_DOC_1]
        assert len(hit) == 1
        assert hit[0]["count"] == 3
        assert hit[0]["positions"] == [0, 1, 2]

    def test_related_to_roundtrip(self):
        """RELATED_TO 写入 → 邻居查询可见 (含关系类型与权重)"""
        from app.core.neo4j_client import (
            create_related_to,
            query_entity_neighbors,
            upsert_entity,
        )

        upsert_entity(_TEST_ENTITY_A, "Term", "", [])
        upsert_entity(_TEST_ENTITY_B, "Term", "", [])
        create_related_to(_TEST_ENTITY_A, _TEST_ENTITY_B, 0.9, "包含")

        neighbors = query_entity_neighbors(_TEST_ENTITY_A)
        hit = [n for n in neighbors if n["name"] == _TEST_ENTITY_B]
        assert len(hit) == 1
        assert hit[0]["relation_type"] == "包含"
        assert abs(hit[0]["weight"] - 0.9) < 1e-9

    def test_delete_document_graph(self):
        """删除文档图谱: 文档节点消失, 孤儿实体被清, 共享实体保留"""
        from app.core.neo4j_client import (
            delete_document_graph,
            get_entity_node,
            replace_document_mentions,
            run_cypher,
            upsert_document,
            upsert_entity,
        )

        # 文档1 提及 A/C, 文档2 提及 B/C (C 为共享实体)
        upsert_document(_TEST_DOC_1, "文档1", "d1.txt")
        upsert_document(_TEST_DOC_2, "文档2", "d2.txt")
        for name in (_TEST_ENTITY_A, _TEST_ENTITY_B, _TEST_ENTITY_C):
            upsert_entity(name, "Term", "", [])
        replace_document_mentions(
            _TEST_DOC_1,
            [
                {"name": _TEST_ENTITY_A, "count": 1, "positions": [0]},
                {"name": _TEST_ENTITY_C, "count": 1, "positions": [0]},
            ],
        )
        replace_document_mentions(
            _TEST_DOC_2,
            [
                {"name": _TEST_ENTITY_B, "count": 1, "positions": [0]},
                {"name": _TEST_ENTITY_C, "count": 1, "positions": [0]},
            ],
        )

        delete_document_graph(_TEST_DOC_1)

        rows = run_cypher(
            "MATCH (d:Document {document_id: $id}) RETURN d",
            {"id": _TEST_DOC_1},
        )
        assert rows == []  # 文档节点已删
        assert get_entity_node(_TEST_ENTITY_A) is None  # 孤儿实体被清
        assert get_entity_node(_TEST_ENTITY_C) is not None  # 共享实体保留

    def test_similar_to_roundtrip(self):
        """SIMILAR_TO 写入 → 全量删除"""
        from app.core.neo4j_client import (
            create_similar_to,
            delete_all_similar_to,
            run_cypher,
            upsert_document,
        )

        upsert_document(_TEST_DOC_1, "文档1", "d1.txt")
        upsert_document(_TEST_DOC_2, "文档2", "d2.txt")
        create_similar_to(_TEST_DOC_1, _TEST_DOC_2, 0.85)

        rows = run_cypher(
            "MATCH (a:Document {document_id: $a})-[r:SIMILAR_TO]-(b:Document {document_id: $b}) "
            "RETURN r.score AS score",
            {"a": _TEST_DOC_1, "b": _TEST_DOC_2},
        )
        assert len(rows) == 1 and abs(rows[0]["score"] - 0.85) < 1e-9

        delete_all_similar_to()
        rows = run_cypher("MATCH ()-[r:SIMILAR_TO]-() RETURN r")
        assert rows == []
