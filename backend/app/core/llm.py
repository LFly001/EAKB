"""
LLM & Embedding 配置 — LlamaIndex 全局 Settings
统一管理 LLM、Embedding 模型实例化

Phase 3: Embedding 已完整实现 (文档向量化流水线使用)
Phase 5: LLM 实例 (llama_index OpenAI 兼容类 → DeepSeek) + 流式对话封装
Phase 6: 非流式 achat_json (图谱实体抽取)
"""

import os
import threading
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.config import settings
from app.utils.exceptions import LLMServiceException

# ==========================================
# LLM 实例 (Phase 5 RAG 核心使用)
# ==========================================

_llm: object | None = None
_embedding_model: object | None = None

# Embedding 初始化锁: 首次加载耗时较长 (10-60s), 并发请求/启动预热
# 同时触发时只允许一个线程加载, 其余等待复用同一实例
_embedding_lock = threading.Lock()


def get_llm() -> object | None:
    """
    获取 LlamaIndex LLM 实例 (单例)。

    llama_index OpenAI 兼容类指向 DeepSeek (LLM_API_BASE=https://api.deepseek.com/v1)。
    - API Key 未配置 (占位符) → 返回 None, 调用方 (RAG 问答) 应报服务不可用
    - llama-index 0.14 系列 OpenAI 类参数兼容 api_base / base_url 两种命名, 自适应

    Returns:
        llama_index.llms.openai.OpenAI 实例; 未配置/初始化失败时返回 None
    """
    global _llm
    if _llm is not None:
        return _llm

    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your"):
        logger.warning(
            f"[LLM] API Key 未配置, LLM 不可用 (LLM_MODEL_NAME={settings.LLM_MODEL_NAME})"
        )
        return None

    try:
        from llama_index.llms.openai import OpenAI

        # openai SDK 在 base_url 参数缺失/被丢弃时回退读取环境变量;
        # 强制注入作为兜底, 兼容 llama-index 各版本 api_base/base_url 行为差异
        # (某版本 api_base 被接受但未透传 → 请求会打到官方 api.openai.com)
        os.environ["OPENAI_API_KEY"] = settings.LLM_API_KEY
        os.environ["OPENAI_BASE_URL"] = settings.LLM_API_BASE

        # 0.14 系列两种参数命名兼容: 先试 api_base, TypeError 回退 base_url
        # (llama-index OpenAI 参数为显式 kw-only, dict[str, Any] 展开类型兼容)
        kwargs: dict[str, Any] = {
            "model": settings.LLM_MODEL_NAME,
            "api_key": settings.LLM_API_KEY,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "timeout": 120.0,
        }
        try:
            _llm = OpenAI(**kwargs, api_base=settings.LLM_API_BASE)
        except TypeError:
            _llm = OpenAI(**kwargs, base_url=settings.LLM_API_BASE)
        logger.info(
            f"[LLM] 模型已初始化: {settings.LLM_MODEL_NAME} "
            f"(api_base={settings.LLM_API_BASE})"
        )
    except Exception as e:
        logger.error(f"[LLM] 初始化失败: {e}")
        return None
    return _llm


def get_embedding_model() -> object | None:
    """
    获取 Embedding 模型实例, 统一 get_text_embedding_batch(texts) 接口。

    优先级:
    1. .env 显式配置了 LLM_EMBEDDING_API_KEY (非占位符) → 远端 OpenAI 兼容 API
    2. 否则 → 本地 bge 模型 (EMBEDDING_MODEL_NAME, sentence-transformers 加载)

    初始化失败时返回 None, 调用方 (向量化流水线) 应将其视为
    配置错误并置任务 failed, 而不是静默跳过。

    Returns:
        OpenAIEmbedding 或 _SentenceTransformerEmbedding 实例; 失败时返回 None
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    with _embedding_lock:  # 串行化首次加载 (启动预热与并发请求只加载一次)
        if _embedding_model is not None:
            return _embedding_model

        # ---- 方案 1: 远端 OpenAI 兼容 Embedding API ----
        api_key = settings.LLM_EMBEDDING_API_KEY or ""
        if api_key and not api_key.startswith("sk-your"):
            try:
                from llama_index.embeddings.openai import OpenAIEmbedding

                _embedding_model = OpenAIEmbedding(
                    model=settings.LLM_EMBEDDING_MODEL,
                    api_key=api_key,
                    api_base=settings.LLM_EMBEDDING_API_BASE,
                )
                logger.info(
                    f"[Embedding] 远端模型已初始化: {settings.LLM_EMBEDDING_MODEL} "
                    f"(api_base={settings.LLM_EMBEDDING_API_BASE})"
                )
                return _embedding_model
            except Exception as e:  # 依赖缺失 / 初始化失败 → 尝试本地模型
                logger.warning(f"[Embedding] 远端模型初始化失败, 回退本地模型: {e}")

        # ---- 方案 2: 本地 bge 模型 (默认) ----
        try:
            # .env 的变量不会自动进入 os.environ, huggingface_hub 只读环境变量,
            # 此处桥接 HF_ENDPOINT 镜像配置 (网络受限时避免连不上 huggingface.co)
            if settings.HF_ENDPOINT:
                os.environ.setdefault("HF_ENDPOINT", settings.HF_ENDPOINT)

            logger.info(
                f"[Embedding] 开始加载本地模型 {settings.EMBEDDING_MODEL_NAME} "
                "(首次加载耗时较长, 请稍候)"
            )
            _embedding_model = _SentenceTransformerEmbedding(
                model_name=settings.EMBEDDING_MODEL_NAME,
                device=settings.EMBEDDING_DEVICE,
            )
            logger.info(
                f"[Embedding] 本地模型已初始化: {settings.EMBEDDING_MODEL_NAME} "
                f"(device={settings.EMBEDDING_DEVICE})"
            )
        except Exception as e:
            logger.error(f"[Embedding] 本地模型初始化失败: {e}")
            return None
        return _embedding_model


class _SentenceTransformerEmbedding:
    """
    sentence-transformers 本地模型适配器。
    提供与远端实现一致的 get_text_embedding_batch / get_text_embedding 接口,
    向量已 L2 归一化 (与 Chroma cosine 空间匹配)。
    """

    def __init__(self, model_name: str, device: str = "cpu"):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)

    def get_text_embedding_batch(self, texts: list) -> list:
        """批量编码 → 归一化向量列表"""
        import numpy as np

        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if isinstance(vectors, np.ndarray):
            return vectors.tolist()
        return [v.tolist() for v in vectors]

    def get_text_embedding(self, text: str) -> list:
        """单条编码"""
        return self.get_text_embedding_batch([text])[0]


# ==========================================
# 流式对话 (Phase 5 RAG 流式问答使用)
# ==========================================

# messages 入参格式: [{"role": "system"|"user"|"assistant", "content": "..."}]


def _get_async_client() -> Any:
    """
    构建 openai 原生 AsyncOpenAI 客户端 (base_url 指向 LLM_API_BASE)。
    流式问答与实体抽取共用同一构造 (Phase 5/6)。

    不用 llama-index OpenAI 包装器: 其对模型名做客户端白名单校验,
    会拒绝 deepseek-v4-pro 等 OpenAI 兼容端点上的自定义模型名。
    (openai 在函数内延迟导入, 返回类型标注为 Any 避免模块级依赖)
    """
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your"):
        raise RuntimeError(
            "LLM 未初始化: 请检查 .env 中 LLM_API_KEY / LLM_API_BASE 配置"
        )

    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        timeout=120.0,
        max_retries=1,
    )


async def astream_chat(messages: list) -> AsyncGenerator[dict, None]:
    """
    LLM 流式对话: 逐块产出 {"delta": 文本增量, "usage": 最终块 Token 用量}。

    - DeepSeek 兼容 stream_options include_usage: 最终块携带 usage
    - API Key 未配置 → RuntimeError (调用方转为 SSE error 事件)
    - 调用/网络错误 → RuntimeError 携带具体原因 (调用方透传给 error 事件)

    Args:
        messages: [{"role": ..., "content": ...}], role ∈ system/user/assistant
    """
    client = _get_async_client()

    try:
        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        async for chunk in stream:
            usage = None
            raw_usage = getattr(chunk, "usage", None)
            if raw_usage is not None:
                usage = {
                    "prompt_tokens": getattr(raw_usage, "prompt_tokens", None),
                    "completion_tokens": getattr(raw_usage, "completion_tokens", None),
                    "total_tokens": getattr(raw_usage, "total_tokens", None),
                }
            delta = ""
            if chunk.choices:
                delta = getattr(chunk.choices[0].delta, "content", None) or ""
            if delta:
                yield {"delta": delta, "usage": None}
            if usage is not None:
                yield {"delta": "", "usage": usage}
    except Exception as e:
        # 认证失败/模型不存在/超时等 (Phase 8):
        # 原始原因仅记日志, 对外抛 LLMServiceException 友好提示, 不透出 Key/内部细节
        logger.error(f"[LLM] 流式调用失败: {type(e).__name__}: {e}")
        raise LLMServiceException() from e


async def achat_json(messages: list, response_format: str | None = None) -> str:
    """
    非流式 LLM 对话, 返回完整回复文本 (Phase 6 图谱实体抽取使用)。

    - response_format="json_object" 时附加 {"type": "json_object"};
      端点不支持 → RuntimeError, 调用方可降级为不传 response_format 重试
    - API Key 未配置 / 调用错误 → RuntimeError (与 astream_chat 一致)

    Args:
        messages: [{"role": ..., "content": ...}], role ∈ system/user/assistant
        response_format: None 或 "json_object"

    Returns:
        完整回复文本; 无 choices 时返回 ""
    """
    client = _get_async_client()

    kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL_NAME,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
    }
    if response_format == "json_object":
        kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = await client.chat.completions.create(**kwargs)
    except LLMServiceException:
        raise
    except Exception as e:
        # 与 astream_chat 一致: 原始原因仅记日志, 对外友好提示 (Phase 8)
        logger.error(f"[LLM] 非流式调用失败: {type(e).__name__}: {e}")
        raise LLMServiceException() from e

    if not resp.choices:
        return ""
    return resp.choices[0].message.content or ""


# ==========================================
# LlamaIndex 全局 Settings
# ==========================================


def init_llama_settings() -> None:
    """
    初始化 LlamaIndex 全局 Settings (main.py lifespan 调用)。

    - Settings.llm = 单例 LLM (DeepSeek 兼容)
    - Embedding 不挂入 Settings: 项目 Embedding 走本地 bge 适配器
      (get_text_embedding 直接调用), 向量化/检索均不经过 LlamaIndex 编排。
      Phase 6+ 接入 HyDE 查询改写时同样直接调用 get_embedding_model()
    - 初始化失败不阻断应用启动 (仅告警), 问答接口会显式报服务不可用
    """
    try:
        from llama_index.core import Settings

        llm = get_llm()
        if llm is not None:
            Settings.llm = llm
            logger.info("[LLM] LlamaIndex 全局 Settings 已就绪")
        else:
            logger.warning("[LLM] LlamaIndex Settings.llm 未设置 (LLM 未配置)")
        Settings.chunk_size = settings.DEFAULT_CHUNK_SIZE
        Settings.chunk_overlap = settings.DEFAULT_CHUNK_OVERLAP
    except Exception as e:
        logger.warning(f"[LLM] LlamaIndex 全局 Settings 初始化失败: {e}")
