"""
文本分块工具
基于系统配置 chunk_size / chunk_overlap 的段落优先滑动窗口分割。
纯工具层: 不操作数据库、不调用外部服务, 参数由调用方传入。
"""

import math
import re

# ==========================================
# 分块
# ==========================================


def split_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """
    将长文本按 chunk_size / chunk_overlap 分割为分块列表。

    策略:
    1. 按空行分段 (段落优先, 保持语义完整)
    2. 段落累积到接近 chunk_size 时切出当前块, 并携带 chunk_overlap
       长度的尾部文本作为下一块开头 (滑动窗口重叠)
    3. 单段落超过 chunk_size 时, 按固定窗口硬切 (步长 = chunk_size - chunk_overlap)

    Args:
        text: 原始文本
        chunk_size: 分块目标大小 (字符数)
        chunk_overlap: 相邻分块重叠大小 (字符数), 必须小于 chunk_size

    Returns:
        分块文本列表 (已 strip, 不含空块)
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size 必须为正数: {chunk_size}")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size: {chunk_overlap}"
        )

    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # 超长段落 → 先落当前块, 再按窗口硬切
        if len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_window_split(para, chunk_size, chunk_overlap))
            continue

        candidate = para if not current else f"{current}\n{para}"
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            # 滑动窗口重叠: 下一块以当前块尾部 overlap 文本开头。
            # 若尾部 + 段落本身超过 chunk_size, 放弃重叠 (保证块长不超限)
            if chunk_overlap > 0:
                tail = current[-chunk_overlap:]
                current = (
                    tail + "\n" + para
                    if len(tail) + 1 + len(para) <= chunk_size
                    else para
                )
            else:
                current = para

    if current:
        chunks.append(current)

    return [c.strip() for c in chunks if c.strip()]


def _window_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """固定窗口硬切, 步长 = chunk_size - chunk_overlap"""
    step = chunk_size - chunk_overlap
    parts: list[str] = []
    start = 0
    while start < len(text):
        part = text[start : start + chunk_size].strip()
        if part:
            parts.append(part)
        start += step
    return parts


# ==========================================
# Token 估算
# ==========================================


def estimate_token_count(text: str) -> int:
    """
    粗略估算文本 Token 数量 (用于分块记录统计, 非精确计费):
    - CJK 字符 ≈ 1 token / 字
    - 其他字符 ≈ 4 字符 / token
    """
    if not text:
        return 0
    cjk_count = sum(1 for ch in text if "一" <= ch <= "鿿")
    other_count = len(text) - cjk_count
    # 纯 CJK 文本时 other 为 0, 不应强行加 1
    other_tokens = math.ceil(other_count / 4) if other_count > 0 else 0
    return cjk_count + other_tokens
