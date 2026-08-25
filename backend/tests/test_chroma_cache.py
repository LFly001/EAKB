"""
Phase 8 Chroma 检索缓存测试
覆盖: 相同查询命中缓存 (免 Chroma 往返) / 参数差异分键 / 写入与删除失效缓存
模式: monkeypatch get_collection 为假 Collection (免真实 Chroma)
"""

from typing import Any

import pytest

from app.core import chroma_client


class FakeCollection:
    """记录调用次数的假 Collection"""

    def __init__(self, distance: float = 0.2) -> None:
        self.query_calls = 0
        self.add_calls = 0
        self.delete_calls: list[Any] = []
        self._distance = distance

    def query(self, **kwargs: Any) -> dict:
        self.query_calls += 1
        return {
            "ids": [["c1"]],
            "documents": [["分块文本内容"]],
            "metadatas": [[{"document_id": 1, "category_id": 1, "chunk_index": 0}]],
            "distances": [[self._distance]],
        }

    def add(self, **kwargs: Any) -> None:
        self.add_calls += 1

    def delete(self, **kwargs: Any) -> None:
        self.delete_calls.append(kwargs)


@pytest.fixture
def fake_collection(monkeypatch: Any) -> FakeCollection:
    fake = FakeCollection()
    monkeypatch.setattr(chroma_client, "get_collection", lambda *a, **k: fake)
    chroma_client.clear_query_cache()
    return fake


class TestQueryCache:
    def test_same_query_hits_cache(self, fake_collection: FakeCollection) -> None:
        """相同查询参数第二次直接返回缓存, 不再调 Chroma"""
        r1 = chroma_client.query_chunks("年假怎么申请", top_k=5)
        r2 = chroma_client.query_chunks("年假怎么申请", top_k=5)

        assert fake_collection.query_calls == 1
        assert r1 == r2
        assert r1[0]["text"] == "分块文本内容"
        assert r1[0]["score"] == pytest.approx(0.9)  # 1 - 0.2/2

    def test_different_params_separate_entries(
        self, fake_collection: FakeCollection
    ) -> None:
        """查询文本 / top_k / 分类过滤不同 → 分键缓存"""
        chroma_client.query_chunks("问题A", top_k=5)
        chroma_client.query_chunks("问题B", top_k=5)
        chroma_client.query_chunks("问题A", top_k=3)
        chroma_client.query_chunks("问题A", top_k=5, category_ids=[1])
        assert fake_collection.query_calls == 4

    def test_cached_result_is_a_copy(self, fake_collection: FakeCollection) -> None:
        """返回缓存副本, 调用方篡改不影响缓存内容"""
        r1 = chroma_client.query_chunks("问题A", top_k=5)
        r1[0]["text"] = "被篡改"
        r2 = chroma_client.query_chunks("问题A", top_k=5)
        assert r2[0]["text"] == "分块文本内容"

    def test_add_chunks_invalidates_cache(
        self, fake_collection: FakeCollection
    ) -> None:
        """写入新分块后缓存失效, 下次检索真实查询"""
        chroma_client.query_chunks("问题A", top_k=5)
        chroma_client.add_chunks(
            ids=["new_1"],
            documents=["新分块"],
            metadatas=[{"document_id": 9}],
            embeddings=[[0.1] * 8],
        )
        chroma_client.query_chunks("问题A", top_k=5)
        assert fake_collection.query_calls == 2

    def test_delete_by_document_invalidates_cache(
        self, fake_collection: FakeCollection
    ) -> None:
        """删除文档分块后缓存失效"""
        chroma_client.query_chunks("问题A", top_k=5)
        chroma_client.delete_by_document_id(1)
        chroma_client.query_chunks("问题A", top_k=5)
        assert fake_collection.query_calls == 2
        assert fake_collection.delete_calls

    def test_below_threshold_cached_as_empty(
        self, fake_collection: FakeCollection, monkeypatch: Any
    ) -> None:
        """低于相似度阈值的结果被过滤, 空结果同样缓存 (不反复打 Chroma)"""
        fake_collection._distance = 1.6  # score = 1 - 0.8 = 0.2 < 0.7
        r1 = chroma_client.query_chunks("无关问题", top_k=5)
        r2 = chroma_client.query_chunks("无关问题", top_k=5)
        assert r1 == []
        assert r2 == []
        assert fake_collection.query_calls == 1
