"""
文本分块工具测试 (纯工具层, 无外部依赖)
覆盖: 基本分块 / 重叠连续性 / 段落边界 / 超长段落硬切 / 参数校验 / Token 估算
"""

from itertools import pairwise

import pytest

from app.utils.text_splitter import estimate_token_count, split_text


class TestSplitText:
    """split_text 基础行为"""

    def test_empty_text(self):
        assert split_text("") == []
        assert split_text("   \n\n  ") == []

    def test_short_text_single_chunk(self):
        text = "这是一段很短的文本"
        assert split_text(text, chunk_size=512) == [text]

    def test_paragraph_aware_split(self):
        """按段落累积, 超出 chunk_size 才切块"""
        paragraphs = [f"第{i}段内容" * 10 for i in range(10)]  # 每段 50 字符
        text = "\n\n".join(paragraphs)
        chunks = split_text(text, chunk_size=120, chunk_overlap=0)

        # 每块不超过 chunk_size
        assert all(len(c) <= 120 for c in chunks)
        # 至少切出多块
        assert len(chunks) > 1
        # 段落不被拦腰截断 (每块末行都是完整段落)
        for chunk in chunks:
            assert all(line in paragraphs for line in chunk.split("\n"))

    def test_overlap_continuity(self):
        """相邻分块重叠: 前块尾部出现在后块头部"""
        text = "abcdefghij" * 30  # 300 字符
        chunks = split_text(text, chunk_size=100, chunk_overlap=20)

        assert len(chunks) > 1
        for prev, nxt in pairwise(chunks):
            assert prev[-20:] == nxt[:20]

    def test_long_paragraph_window_split(self):
        """单段落超过 chunk_size → 固定窗口硬切"""
        text = "长" * 500
        chunks = split_text(text, chunk_size=100, chunk_overlap=20)

        # 窗口起点: 0,80,160,240,320,400,480 (步长 80) → 7 块
        assert len(chunks) == 7
        assert all(0 < len(c) <= 100 for c in chunks)
        # 重叠连续性
        for prev, nxt in pairwise(chunks):
            assert prev[-20:] == nxt[:20]

    def test_no_overlap_mode(self):
        text = "x" * 250
        chunks = split_text(text, chunk_size=100, chunk_overlap=0)
        assert [len(c) for c in chunks] == [100, 100, 50]

    def test_overlap_dropped_when_paragraph_too_long(self):
        """重叠尾部 + 长段落超过 chunk_size 时放弃重叠, 保证块长不超限"""
        paras = ["a" * 500, "b" * 450, "c" * 100]
        text = "\n\n".join(paras)
        chunks = split_text(text, chunk_size=512, chunk_overlap=64)

        # 任意块都不超过 chunk_size
        assert all(len(c) <= 512 for c in chunks)
        # 第一块 = 500 字符段落; 第二块若携带 64 字重叠会变成 515 > 512, 应放弃重叠
        assert chunks[0] == "a" * 500
        assert chunks[1] == "b" * 450

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            split_text("text", chunk_size=0)
        with pytest.raises(ValueError):
            split_text("text", chunk_size=100, chunk_overlap=100)
        with pytest.raises(ValueError):
            split_text("text", chunk_size=100, chunk_overlap=-1)

    def test_chinese_text_split(self):
        """中文文本按字符切分"""
        text = "企业知识库智能助手。" * 40
        chunks = split_text(text, chunk_size=60, chunk_overlap=10)
        assert len(chunks) > 1
        assert all(len(c) <= 60 for c in chunks)


class TestEstimateTokenCount:
    """Token 估算"""

    def test_empty(self):
        assert estimate_token_count("") == 0

    def test_pure_cjk(self):
        # 9 个汉字 = 9 token (纯 CJK 不额外加 1)
        assert estimate_token_count("企业知识库智能助手") == 9

    def test_mixed_text(self):
        # CJK 1字1token + 英文 4字符1token
        count = estimate_token_count("你好world")
        assert count == 2 + 2  # 你好=2, world=5字符→ceil(5/4)=2
