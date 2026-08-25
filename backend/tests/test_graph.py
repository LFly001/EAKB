"""
Phase 6 知识图谱模块测试
覆盖: 抽取结果解析 / 分块聚合 / 跨批合并 / 实体位置 / 向量质心与余弦 /
     实体匹配 / 图谱上下文块 / Schema 校验 / 鉴权边界

说明: 采用纯逻辑 + monkeypatch 模式, 无需真实 MySQL/Chroma/Neo4j/LLM。
Neo4j 集成往返测试见 test_graph_neo4j_integration.py (VM 环境按需开启)。
完整链路 (构建/查询/增强问答) 在 VM 环境按 docs/phase6-test-guide.md 手工自测。
"""

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.schemas.graph import GraphBuildRequest, GraphSearchResponse
from app.services.graph_service import (
    build_extraction_batches,
    build_graph_context_block,
    centroid_embedding,
    cosine_similarity,
    find_entity_positions,
    match_entities,
    merge_entity_batches,
    parse_extraction_json,
)

# ==========================================
# 抽取结果解析 (三级容错)
# ==========================================


class TestParseExtractionJson:
    def test_standard_json(self):
        content = '{"entities": [{"name": "年假", "type": "Policy"}], "relations": []}'
        result = parse_extraction_json(content)
        assert result["entities"][0]["name"] == "年假"
        assert result["relations"] == []

    def test_markdown_fence(self):
        content = '```json\n{"entities": [], "relations": []}\n```'
        result = parse_extraction_json(content)
        assert result == {"entities": [], "relations": []}

    def test_plain_text_with_json_block(self):
        """解释文本包裹 JSON → 正则提取兜底"""
        content = (
            '以下是抽取结果:\n{"entities": [{"name": "考勤"}], "relations": []}\n以上。'
        )
        result = parse_extraction_json(content)
        assert result["entities"][0]["name"] == "考勤"

    def test_invalid_text(self):
        """完全非法文本 → 空结构, 不抛异常"""
        assert parse_extraction_json("这不是JSON") == {"entities": [], "relations": []}
        assert parse_extraction_json("") == {"entities": [], "relations": []}

    def test_entities_not_list(self):
        """entities 非列表 → 容错为空"""
        result = parse_extraction_json('{"entities": "bad", "relations": []}')
        assert result == {"entities": [], "relations": []}


# ==========================================
# 抽取分块聚合
# ==========================================


class TestBuildExtractionBatches:
    def test_single_batch(self):
        chunks = ["短文本A", "短文本B"]
        batches = build_extraction_batches(chunks, max_chars=100)
        assert len(batches) == 1
        assert "短文本A" in batches[0] and "短文本B" in batches[0]

    def test_split_over_limit(self):
        """超限切批, 整块粒度不切断"""
        chunks = ["A" * 60, "B" * 60, "C" * 60]
        batches = build_extraction_batches(chunks, max_chars=100)
        assert len(batches) == 3
        assert batches[0] == "A" * 60

    def test_empty_chunks_skipped(self):
        assert build_extraction_batches(["", "  ", "\n"], max_chars=100) == []


# ==========================================
# 跨批合并
# ==========================================


def _entity(
    name: str, type_: str = "Term", description: str = "", aliases: list | None = None
) -> dict:
    return {
        "name": name,
        "type": type_,
        "description": description,
        "aliases": aliases or [],
    }


class TestMergeEntityBatches:
    def test_merge_same_entity(self):
        """同名实体去重: count 累计, aliases 并集, type/description 取首个非空"""
        batch1 = {
            "entities": [_entity("年假", "Policy", "带薪年休假", ["Annual Leave"])],
            "relations": [],
        }
        batch2 = {"entities": [_entity("年假", "", "", ["年休假"])], "relations": []}
        merged = merge_entity_batches([batch1, batch2])
        assert len(merged["entities"]) == 1
        e = merged["entities"][0]
        assert e["count"] == 2
        assert e["type"] == "Policy"  # 首个非空
        assert e["description"] == "带薪年休假"
        assert e["aliases"] == ["Annual Leave", "年休假"]  # 并集排序

    def test_relation_dedup_weight_max(self):
        """关系按 (source,target) 去重, weight 取最大"""
        batch1 = {
            "entities": [_entity("年假"), _entity("考勤")],
            "relations": [
                {
                    "source": "年假",
                    "target": "考勤",
                    "relation_type": "相关",
                    "weight": 0.5,
                }
            ],
        }
        batch2 = {
            "entities": [_entity("年假"), _entity("考勤")],
            "relations": [
                {
                    "source": "年假",
                    "target": "考勤",
                    "relation_type": "相关",
                    "weight": 0.9,
                }
            ],
        }
        merged = merge_entity_batches([batch1, batch2])
        assert len(merged["relations"]) == 1
        assert merged["relations"][0]["weight"] == 0.9

    def test_relation_endpoint_not_in_entities_dropped(self):
        """关系端点不在实体集合内 → 丢弃"""
        batch = {
            "entities": [_entity("年假")],
            "relations": [{"source": "年假", "target": "不存在的实体", "weight": 0.5}],
        }
        assert merge_entity_batches([batch])["relations"] == []

    def test_weight_clamped(self):
        """weight 越界钳制到 [0, 1]"""
        batch = {
            "entities": [_entity("A"), _entity("B")],
            "relations": [
                {"source": "A", "target": "B", "relation_type": "相关", "weight": 5.0},
                {"source": "B", "target": "A", "relation_type": "相关", "weight": -1.0},
            ],
        }
        relations = merge_entity_batches([batch])["relations"]
        assert sorted(r["weight"] for r in relations) == [0.0, 1.0]

    def test_self_relation_dropped(self):
        batch = {
            "entities": [_entity("A")],
            "relations": [{"source": "A", "target": "A", "weight": 0.5}],
        }
        assert merge_entity_batches([batch])["relations"] == []


# ==========================================
# 实体位置 / 向量质心 / 余弦相似度
# ==========================================


class TestFindEntityPositions:
    def test_hits(self):
        chunks = ["年假申请流程", "加班规定", "年假天数上限"]
        positions = find_entity_positions(chunks, ["年假", "加班"])
        assert positions["年假"] == [0, 2]
        assert positions["加班"] == [1]

    def test_missing_name_absent(self):
        positions = find_entity_positions(["文本"], ["不存在实体"])
        assert positions == {}


class TestCentroidCosine:
    def test_centroid_normalized(self):
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        centroid = centroid_embedding(vectors)
        assert centroid is not None
        # L2 归一化后范数应为 1 (允许浮点误差)
        norm = sum(x * x for x in centroid) ** 0.5
        assert abs(norm - 1.0) < 1e-9

    def test_same_vector_similarity_one(self):
        v = [0.6, 0.8]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_dimension_mismatch_zero(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_empty_vectors_none(self):
        assert centroid_embedding([]) is None

    def test_dimension_mismatch_centroid_none(self):
        assert centroid_embedding([[1.0, 0.0], [1.0, 0.0, 0.0]]) is None


# ==========================================
# RAG 增强实体匹配
# ==========================================


class TestMatchEntities:
    def test_exact_name_hit(self):
        rows = [{"name": "年假", "aliases": []}]
        assert match_entities(rows, "年假有多少天?") == ["年假"]

    def test_alias_hit(self):
        rows = [{"name": "员工手册", "aliases": ["手册"]}]
        assert match_entities(rows, "手册里写了什么?") == ["员工手册"]

    def test_too_short_not_matched(self):
        rows = [{"name": "A", "aliases": []}]
        assert match_entities(rows, "A是什么") == []

    def test_no_hit(self):
        rows = [{"name": "年假", "aliases": []}]
        assert match_entities(rows, "今天天气怎么样") == []


# ==========================================
# 图谱增强上下文块
# ==========================================


def _neighbors(entries: list) -> list:
    return [
        {"neighbor": n, "type": "Term", "relation_type": rel, "weight": 0.8}
        for n, rel in entries
    ]


class TestBuildGraphContextBlock:
    def test_with_neighbors(self):
        matches = [
            {
                "entity": "年假",
                "neighbors": _neighbors([("考勤", "相关"), ("调休", "包含")]),
            }
        ]
        block = build_graph_context_block(matches)
        assert block.startswith("[知识图谱关联]")
        assert "年假" in block and "考勤" in block and "调休" in block

    def test_empty_matches(self):
        assert build_graph_context_block([]) == ""

    def test_empty_neighbors_skipped(self):
        matches = [{"entity": "年假", "neighbors": []}]
        assert build_graph_context_block(matches) == ""

    def test_max_three_neighbors(self):
        entries = [("A", "相关"), ("B", "相关"), ("C", "相关"), ("D", "相关")]
        block = build_graph_context_block(
            [{"entity": "年假", "neighbors": _neighbors(entries)}]
        )
        assert "D" not in block


# ==========================================
# Schema 校验
# ==========================================


class TestGraphSchemas:
    def test_build_request_default(self):
        req = GraphBuildRequest()
        assert req.document_id is None

    def test_build_request_document_id_positive(self):
        req = GraphBuildRequest(document_id=1)
        assert req.document_id == 1
        with pytest.raises(ValidationError):
            GraphBuildRequest(document_id=0)

    def test_build_request_forbid_extra(self):
        with pytest.raises(ValidationError):
            GraphBuildRequest(unknown_field="x")

    def test_search_response_defaults(self):
        resp = GraphSearchResponse()
        assert resp.nodes == []
        assert resp.edges == []
        assert resp.truncated is False


# ==========================================
# 鉴权边界 (无 Token 一律 401, 不依赖真实数据库)
# ==========================================


class TestAuthBoundary:
    @pytest.mark.asyncio
    async def test_entity_list_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/graph/entities/")
        assert response.status_code == 401
        assert response.json()["code"] == 40100

    @pytest.mark.asyncio
    async def test_entity_detail_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/graph/entities/%E5%B9%B4%E5%81%87")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/graph/search")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_build_requires_auth(self, async_client: AsyncClient):
        response = await async_client.post("/api/v1/graph/build", json={})
        assert response.status_code == 401
