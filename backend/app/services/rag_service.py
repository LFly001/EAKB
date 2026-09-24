"""
RAG 智能问答核心编排服务 — Phase 5

标准流程 (CLAUDE.md / DESIGN.md 八, 已确认决策):
1. 读取/自动匹配提示词模板 (显式 template_id > 会话绑定 > 分类匹配 > 系统默认)
2. Query 改写扩展点 (Phase 5: 原样返回直接向量检索, Phase 6+ 可接入 HyDE/多查询)
3. Chroma 向量检索 + category_id 元数据过滤 Top-K (query_embeddings 保证维度一致)
4. 组装上下文填充模板 {{context}} / {{question}} (+ 最近 N 轮历史拼接)
5. LLM 流式生成 → SSE 事件 (meta → sources → delta* → done)
6. 保存消息: retrieved_chunks / sources / token_usage / response_time_ms
7. 操作日志埋点 + 消息轮数统计

强制业务规则:
- 无匹配知识库内容 → 不调用 LLM, 返回固定提示 (禁止编造)
- 流内错误 → SSE error 事件 + assistant 消息落库 error_message
- 客户端断连 → 尽力保存部分回答后终止 (不自动重放, 前端提示重试)
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.core.chroma_client import query_chunks
from app.core.database import async_session_factory
from app.core.llm import astream_chat, get_embedding_model
from app.models.category import KbCategory
from app.models.conversation import RagConversation
from app.models.message import RagMessage
from app.models.template import PtTemplate
from app.models.user import SysUser
from app.schemas.conversation import join_category_ids, parse_category_ids
from app.schemas.rag import (
    ChatDoneEvent,
    ChatMetaEvent,
    ChatSourcesEvent,
    ChatStreamRequest,
    MessageFeedbackRequest,
    RagSearchRequest,
    RagSearchResponse,
)
from app.services.config_service import ConfigService
from app.services.conversation_service import ConversationService
from app.services.log_service import LogService
from app.services.template_service import TemplateService, render_template_content
from app.utils.exceptions import (
    AppException,
    BadRequestException,
    LLMServiceException,
    NotFoundException,
    ServiceUnavailableException,
)
from app.utils.text_splitter import estimate_token_count

# ==========================================
# 常量
# ==========================================

# 无匹配知识库内容时的固定回复 (禁止编造: 不调用 LLM, 直接返回并结束)
NO_MATCH_REPLY = (
    "抱歉，知识库中未找到与您问题相关的资料，我无法给出可靠回答。\n\n"
    "建议尝试：\n"
    "1. 换一种表述方式重新提问；\n"
    "2. 检查或调整知识库分类筛选范围；\n"
    "3. 联系管理员补充相关文档。"
)

# SSE 事件类型 (前后端契约, 详见 docs/api-reference.md)
EVENT_META = "meta"
EVENT_DELTA = "delta"
EVENT_SOURCES = "sources"
EVENT_DONE = "done"
EVENT_ERROR = "error"

# 多轮对话历史默认携带轮数 (可用 sys_config key `chat_history_rounds` 覆盖)
DEFAULT_HISTORY_ROUNDS = 5

# 历史中单条消息最大字符数 (控制 Prompt 长度)
HISTORY_MAX_CHARS = 2000

# 图谱增强调用超时 (秒): Neo4j 驱动连接失败时会内部重试可达数十秒,
# 必须限时降级, 否则图谱服务故障会拖慢整个问答 (Phase 6)
GRAPH_ENHANCE_TIMEOUT_SECONDS = 5

# 错误信息入库截断长度
_ERROR_MAX_LENGTH = 2000

# 固定回复流式分片大小 (模拟逐字输出)
FALLBACK_CHUNK_SIZE = 80

# 模板全部缺失时的兜底系统 Prompt (种子数据正常情况下不会走到)
_DEFAULT_TEMPLATE_CONTENT = (
    "你是一名专业的企业知识库智能助手，请根据以下知识库内容回答用户问题。\n\n"
    "知识库内容：\n{{context}}\n\n"
    "用户问题：{{question}}\n\n"
    "要求：仅基于知识库内容作答，不要编造知识库中不存在的信息；"
    "如果知识库中没有相关内容，请明确告知用户。"
)


# ==========================================
# 纯工具函数 (模块级, 便于单元测试)
# ==========================================


def sse_event(event: str, data: dict) -> dict:
    """构建 sse-starlette 事件 dict (data 序列化为 JSON 字符串)"""
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def build_history(rows: list) -> list[dict]:
    """
    历史消息组装 (Phase 8 修正): user/assistant 按轮次配对过滤。

    跳过无意义轮次: 生成失败 (answer 为空) 与无匹配固定回复
    (retrieved_chunks 为空) 均不携带知识信息;
    **其配对的用户问题必须一并丢弃** — 否则孤儿 user 消息会残留,
    LLM 误以为上一问未作答, 在下一轮回答中补答旧问题。
    """
    history: list[dict] = []
    pending_user: str | None = None
    for m in rows:
        if m.role == "user":
            pending_user = (m.question or "").strip()[:HISTORY_MAX_CHARS]
            continue
        # assistant 消息
        if not m.answer or not m.retrieved_chunks:
            pending_user = None  # 无效轮次: 配对用户问题一并丢弃
            continue
        if pending_user:
            history.append({"role": "user", "content": pending_user})
        history.append(
            {"role": "assistant", "content": m.answer.strip()[:HISTORY_MAX_CHARS]}
        )
        pending_user = None
    # 尾部未配对的用户消息 (理论不存在: 每条用户消息都会产生助手消息) 直接丢弃
    return history


def build_retrieved_chunks(chunks: list[dict]) -> list[dict]:
    """检索结果 → retrieved_chunks JSON (DESIGN 4.1.8 结构)"""
    return [
        {
            "chunk_id": c["chunk_id"],
            "document_id": c["metadata"].get("document_id"),
            "title": c["metadata"].get("document_title", ""),
            "text": c["text"],
            "score": c["score"],
        }
        for c in chunks
    ]


def build_sources(chunks: list[dict]) -> list[dict]:
    """
    检索结果 → sources JSON: 按文档聚合去重,
    relevance_score 取该文档命中的分块最高分。
    """
    by_doc: dict[Any, dict] = {}
    order: list[Any] = []
    for c in chunks:
        meta = c["metadata"]
        doc_id = meta.get("document_id")
        if doc_id is None:
            continue
        if doc_id not in by_doc:
            by_doc[doc_id] = {
                "document_id": doc_id,
                "title": meta.get("document_title", ""),
                "file_name": meta.get("file_name", ""),
                "relevance_score": c["score"],
            }
            order.append(doc_id)
        else:
            by_doc[doc_id]["relevance_score"] = max(
                by_doc[doc_id]["relevance_score"], c["score"]
            )
    return [by_doc[doc_id] for doc_id in order]


def build_context(chunks: list[dict], max_context_tokens: int) -> str:
    """拼接检索分块为上下文文本, 按 max_context_tokens 截断 (整块粒度)"""
    blocks: list[str] = []
    used = 0
    for c in chunks:
        meta = c["metadata"]
        chunk_index = meta.get("chunk_index")
        index_text = (
            f"(分块 {int(chunk_index) + 1})" if isinstance(chunk_index, int) else ""
        )
        block = f"[文档] {meta.get('document_title', '')} {index_text}\n{c['text']}"
        cost = estimate_token_count(block)
        if blocks and used + cost > max_context_tokens:
            break
        blocks.append(block)
        used += cost
    return "\n\n---\n\n".join(blocks)


def build_prompt_full(system_prompt: str, history: list[dict], question: str) -> str:
    """记录实际发送的完整 Prompt (system + 历史 + 当前问题)"""
    parts = [f"[system]\n{system_prompt}"]
    for m in history:
        parts.append(f"[{m['role']}]\n{m['content']}")
    parts.append(f"[user]\n{question}")
    return "\n\n".join(parts)


def estimate_usage(prompt_text: str, answer_text: str) -> dict:
    """流式响应取不到 usage 时的估算兜底 (非精确计费)"""
    prompt_tokens = estimate_token_count(prompt_text)
    completion_tokens = estimate_token_count(answer_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def split_fallback_reply(text: str, size: int = FALLBACK_CHUNK_SIZE) -> list[str]:
    """固定回复按字符分片, 模拟流式输出"""
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


# ==========================================
# RAG 核心编排
# ==========================================


class RagService:
    """RAG 智能问答编排服务"""

    # ==========================================
    # 流式问答入口 (路由调用)
    # ==========================================

    @staticmethod
    async def stream_chat(
        db: AsyncSession,
        user: SysUser,
        req: ChatStreamRequest,
        ip_address: str | None = None,
    ) -> EventSourceResponse:
        """
        POST /api/v1/rag/chat-stream — SSE 流式问答。

        流开始前 (请求会话, 失败走标准 JSON 错误):
        1. 分类合法性校验  2. 解析/自动新建会话  3. 用户消息落库
        流过程中 (独立会话, 与请求生命周期解耦, 错误走 SSE error 事件)
        """
        # ---- 流开始前 ----
        if req.category_ids:
            await RagService._validate_category_ids(db, req.category_ids)

        conversation = await ConversationService.resolve_for_chat(
            db, user.id, req.conversation_id, req.question
        )

        user_msg = RagMessage(
            conversation_id=conversation.id,
            role="user",
            question=req.question,
            model_name=settings.LLM_MODEL_NAME,
        )
        db.add(user_msg)
        await db.commit()
        await db.refresh(user_msg)
        logger.info(
            f"[RAG] 收到提问: conversation={conversation.id}, "
            f"user={user.username}, question={req.question[:50]}"
        )

        # ---- 事件生成器 (独立会话: 客户端断连时请求会话可能已被回收) ----
        async def event_generator() -> AsyncGenerator[dict, None]:
            async with async_session_factory() as stream_db:
                async for event in RagService._stream_events(
                    stream_db,
                    user,
                    req,
                    conversation.id,
                    user_msg.id,
                    ip_address,
                ):
                    yield event

        return EventSourceResponse(event_generator())

    @staticmethod
    async def _stream_events(
        stream_db: AsyncSession,
        user: SysUser,
        req: ChatStreamRequest,
        conversation_id: int,
        user_message_id: int,
        ip_address: str | None,
    ) -> AsyncGenerator[dict, None]:
        """SSE 事件流主体 — 检索 → 组装 → 生成 → 落库 → done"""
        start_time = time.perf_counter()
        partial_answer: list[str] = []
        prompt_full: str | None = None

        try:
            conversation = await stream_db.get(RagConversation, conversation_id)
            if conversation is None:
                raise NotFoundException("对话不存在")

            # ---- 1. 模板解析 + 使用计数 ----
            template = await RagService._resolve_template(stream_db, req, conversation)
            if template is not None:
                if conversation.template_id != template.id:
                    conversation.template_id = template.id
                    await stream_db.commit()
                await TemplateService.increment_usage(stream_db, template.id)

            yield sse_event(
                EVENT_META,
                ChatMetaEvent(
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                    template_id=template.id if template else None,
                    template_name=template.name if template else None,
                ).model_dump(),
            )

            # ---- 2. Query 改写扩展点 (Phase 5: 直接向量检索) ----
            question = await RagService._rewrite_query(req.question)

            # ---- 3. 分类范围 + Chroma 检索 (query_embeddings 保证维度一致) ----
            rag_params = await ConfigService.get_rag_params(stream_db)
            if req.category_ids is not None:
                conversation.category_ids = join_category_ids(req.category_ids)
                await stream_db.commit()
            category_ids = parse_category_ids(conversation.category_ids)

            # 多轮历史提前加载: 检索兜底与 Prompt 组装共用
            history = await RagService._load_history(
                stream_db, conversation_id, user_message_id
            )

            chunks = await RagService._retrieve(question, category_ids, rag_params)
            if not chunks and history:
                # 多轮追问兜底 (追问往往省略主语, 裸问题相似度不足):
                # ① 拼接最近一轮完整问答的用户问题检索
                # ② 仍无命中则直接用该问题检索 (追问与上轮同主题)
                # 注意: 必须取「有助手回答的完整轮次」的用户问题 —
                # 紧邻的上条用户消息可能本身也是失败的模糊追问, 兜底会再次落空
                last_user = None
                for i in range(len(history) - 1, 0, -1):
                    if (
                        history[i]["role"] == "assistant"
                        and history[i - 1]["role"] == "user"
                    ):
                        last_user = history[i - 1]["content"]
                        break
                if last_user:
                    logger.info(
                        f"[RAG] 裸问题未命中, 拼接上轮问题扩展检索: "
                        f"conversation={conversation_id}"
                    )
                    chunks = await RagService._retrieve(
                        f"{last_user} {question}", category_ids, rag_params
                    )
                    if not chunks:
                        logger.info(
                            f"[RAG] 拼接检索仍无命中, 回退上轮问题检索: "
                            f"conversation={conversation_id}"
                        )
                        chunks = await RagService._retrieve(
                            last_user, category_ids, rag_params
                        )

            retrieved = build_retrieved_chunks(chunks)
            sources = build_sources(chunks)
            yield sse_event(
                EVENT_SOURCES,
                ChatSourcesEvent(
                    sources=sources, retrieved_chunks=retrieved
                ).model_dump(),
            )
            logger.info(
                f"[RAG] 检索完成: conversation={conversation_id}, "
                f"top_k={rag_params['top_k']}, 命中 {len(chunks)} 块"
            )

            # ---- 3.5 图谱增强 (可选, sys_config graph_enhance_enabled 控制) ----
            # 仅在检索命中且开关开启时补充实体关联上下文; Neo4j 异常/超时静默降级纯向量检索
            graph_context_text = ""
            if chunks and rag_params.get("graph_enhance_enabled"):
                try:
                    from app.services.graph_service import GraphService

                    graph_context_text = await asyncio.wait_for(
                        GraphService.build_graph_context(
                            question,
                            int(
                                rag_params.get("graph_entity_top_k")
                                or settings.DEFAULT_GRAPH_ENTITY_TOP_K
                            ),
                        ),
                        timeout=GRAPH_ENHANCE_TIMEOUT_SECONDS,
                    )
                    if graph_context_text:
                        logger.info(
                            f"[RAG] 图谱增强命中: conversation={conversation_id}"
                        )
                except asyncio.TimeoutError:
                    # Neo4j 驱动连接重试可能很慢, 限时放弃, 不拖慢问答
                    logger.warning(
                        f"[RAG] 图谱增强超时 ({GRAPH_ENHANCE_TIMEOUT_SECONDS}s), "
                        f"降级纯向量检索: conversation={conversation_id}"
                    )
                except Exception as e:
                    logger.warning(f"[RAG] 图谱增强失败, 降级纯向量检索: {e}")

            # ---- 4. 上下文组装 Prompt ----
            context_text = build_context(chunks, int(rag_params["max_context_tokens"]))
            if graph_context_text:
                context_text = context_text + "\n\n" + graph_context_text
            system_prompt = RagService._build_system_prompt(
                template, question, context_text
            )
            prompt_full = build_prompt_full(system_prompt, history, question)

            # ---- 5. 生成回答 ----
            usage: dict | None = None
            if not chunks:
                # 无匹配知识库内容: 禁止编造, 不调用 LLM, 直接返回固定提示
                answer = NO_MATCH_REPLY
                logger.info(
                    f"[RAG] 无匹配分块, 返回固定提示: conversation={conversation_id}"
                )
                for piece in split_fallback_reply(answer):
                    partial_answer.append(piece)
                    yield sse_event(EVENT_DELTA, {"content": piece})
                    await asyncio.sleep(0)
            else:
                messages = (
                    [{"role": "system", "content": system_prompt}]
                    + history
                    + [{"role": "user", "content": question}]
                )
                try:
                    # 注意: 循环变量不与无匹配分支的 piece (str) 同名,
                    # 否则 mypy 推断冲突 (此处为 dict)
                    async for stream_piece in astream_chat(messages):
                        if stream_piece.get("usage") is not None:
                            usage = stream_piece["usage"]
                        if stream_piece.get("delta"):
                            partial_answer.append(stream_piece["delta"])
                            yield sse_event(
                                EVENT_DELTA, {"content": stream_piece["delta"]}
                            )
                except LLMServiceException:
                    # Phase 8: LLM 异常已在 core/llm 层友好化 (50304), 直接透传
                    raise
                except RuntimeError as e:
                    # LLM 未初始化等可预期错误 → SSE error 事件携带具体原因
                    raise ServiceUnavailableException(str(e)) from e
                answer = "".join(partial_answer)
                if usage is None:
                    # DeepSeek 流式最终块 usage 取不到时估算兜底
                    usage = estimate_usage(prompt_full, answer)

            # ---- 6. 助手消息落库 + 统计 ----
            response_time_ms = int((time.perf_counter() - start_time) * 1000)
            assistant_msg = RagMessage(
                conversation_id=conversation_id,
                role="assistant",
                question=question,
                answer=answer,
                prompt_full=prompt_full,
                retrieved_chunks=retrieved,
                sources=sources,
                model_name=settings.LLM_MODEL_NAME,
                token_usage=usage if chunks else None,
                response_time_ms=response_time_ms,
            )
            stream_db.add(assistant_msg)
            await stream_db.commit()
            await stream_db.refresh(assistant_msg)
            await ConversationService.increment_message_count(
                stream_db, conversation_id
            )

            # ---- 7. 完成事件 + 操作日志 ----
            yield sse_event(
                EVENT_DONE,
                ChatDoneEvent(
                    conversation_id=conversation_id,
                    message_id=assistant_msg.id,
                    token_usage=assistant_msg.token_usage,
                    response_time_ms=response_time_ms,
                ).model_dump(),
            )

            try:
                await LogService.create(
                    stream_db,
                    user_id=user.id,
                    username=user.username,
                    action="chat",
                    module="rag",
                    target_type="conversation",
                    target_id=str(conversation_id),
                    detail={
                        "message_id": assistant_msg.id,
                        "chunk_count": len(chunks),
                        "template_id": template.id if template else None,
                        "response_time_ms": response_time_ms,
                    },
                    ip_address=ip_address,
                )
            except Exception:
                logger.exception("[RAG] 操作日志写入失败")

        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断连: 尽力保存已生成的部分回答, 不自动重放 (前端提示重试)
            # Phase 8: shield 保护保存操作在后台完成 — 直接 await 会被取消作用域
            # 半途打断, 连接留在"执行中取消"状态, 连接池清理时打印大量报错噪音
            try:
                await asyncio.shield(
                    RagService._persist_failure(
                        stream_db,
                        conversation_id,
                        req.question,
                        error="客户端连接中断，生成未完成",
                        partial_answer="".join(partial_answer),
                        prompt_full=prompt_full,
                        response_time_ms=int((time.perf_counter() - start_time) * 1000),
                    )
                )
            except asyncio.CancelledError:
                # 外层任务仍被取消; 保存任务已在后台继续, 正常退出
                pass
            raise
        except Exception as e:
            logger.exception(f"[RAG] 问答生成失败: conversation={conversation_id}")
            await RagService._persist_failure(
                stream_db,
                conversation_id,
                req.question,
                error=str(e)[:_ERROR_MAX_LENGTH],
                partial_answer="".join(partial_answer),
                prompt_full=prompt_full,
                response_time_ms=int((time.perf_counter() - start_time) * 1000),
            )
            # 业务异常透传友好文案, 系统异常统一隐藏细节
            message = (
                e.message if isinstance(e, AppException) else "生成失败，请稍后重试"
            )
            yield sse_event(EVENT_ERROR, {"message": message})

    # ==========================================
    # 内部检索 (ESD 集成, POST /api/v1/rag/search)
    # ==========================================

    @staticmethod
    async def search(db: AsyncSession, req: RagSearchRequest) -> RagSearchResponse:
        """
        无状态检索 — 供 ESD 知识 agent 调用 (DESIGN 8.1)。

        复用问答链路的检索环节: 分类校验 → 检索参数 → 向量检索 → 分块/来源组装。
        无 LLM 调用、无消息落库、无操作日志 (调用方自行组织回答)。
        """
        category_ids = req.category_ids or []
        if category_ids:
            await RagService._validate_category_ids(db, category_ids)

        rag_params = await ConfigService.get_rag_params(db)
        chunks = await RagService._retrieve(req.question, category_ids, rag_params)

        return RagSearchResponse(
            chunks=build_retrieved_chunks(chunks),
            sources=build_sources(chunks),
            top_k=int(rag_params["top_k"]),
            similarity_threshold=float(rag_params["similarity_threshold"]),
        )

    # ==========================================
    # 反馈
    # ==========================================

    @staticmethod
    async def submit_feedback(
        db: AsyncSession,
        user_id: int,
        message_id: int,
        req: MessageFeedbackRequest,
    ) -> RagMessage:
        """回答点赞/点踩反馈 — 仅本人会话中的助手消息可反馈"""
        result = await db.execute(
            select(RagMessage)
            .join(RagConversation, RagMessage.conversation_id == RagConversation.id)
            .where(
                RagMessage.id == message_id,
                RagConversation.user_id == user_id,
            )
        )
        message = result.scalar_one_or_none()
        if message is None:
            raise NotFoundException("消息不存在或无权访问")
        if message.role != "assistant":
            raise BadRequestException("仅可对助手回答提交反馈")

        message.feedback = req.feedback
        message.feedback_comment = req.comment
        await db.commit()
        await db.refresh(message)
        logger.info(
            f"[RAG] 反馈已记录: message_id={message_id}, "
            f"feedback={req.feedback}, comment={bool(req.comment)}"
        )
        return message

    # ==========================================
    # 内部步骤
    # ==========================================

    @staticmethod
    async def _validate_category_ids(db: AsyncSession, category_ids: list[int]) -> None:
        """分类存在性校验 (去重后任一不存在整体拒绝)"""
        ids = list(dict.fromkeys(category_ids))
        result = await db.execute(select(KbCategory.id).where(KbCategory.id.in_(ids)))
        existing = set(result.scalars().all())
        missing = [cid for cid in ids if cid not in existing]
        if missing:
            raise BadRequestException(f"分类不存在: {missing}")

    @staticmethod
    async def _resolve_template(
        db: AsyncSession,
        req: ChatStreamRequest,
        conversation: RagConversation,
    ) -> PtTemplate | None:
        """
        模板匹配优先级:
        1. 本次请求显式 template_id
        2. 会话已绑定且仍启用
        3. 首个限定分类的 by-category 匹配
        4. 系统默认模板 (is_system 种子首个)
        """
        if req.template_id is not None:
            template = await db.get(PtTemplate, req.template_id)
            if template is None or template.status != 1:
                raise BadRequestException("提示词模板不存在或已禁用")
            return template

        if conversation.template_id is not None:
            template = await db.get(PtTemplate, conversation.template_id)
            if template is not None and template.status == 1:
                return template

        category_ids = parse_category_ids(conversation.category_ids)
        if category_ids:
            templates = await TemplateService.get_by_category(db, category_ids[0])
            if templates:
                return await db.get(PtTemplate, templates[0].id)

        result = await db.execute(
            select(PtTemplate)
            .where(PtTemplate.is_system == 1, PtTemplate.status == 1)
            .order_by(PtTemplate.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _rewrite_query(question: str) -> str:
        """Query 改写扩展点。Phase 5: 原样返回直接向量检索; Phase 6+ 可接入 HyDE/多查询"""
        return question

    @staticmethod
    async def _retrieve(
        question: str,
        category_ids: list[int],
        rag_params: dict[str, Any],
    ) -> list[dict]:
        """
        Chroma 向量检索: 显式生成查询向量 (与库内 bge 同源同维度),
        按 category_id 元数据过滤, 相似度阈值过滤。
        """
        # 本地 bge 模型首次加载耗时较长 (CPU 上 10-60s), 必须放线程池:
        # 同步加载会阻塞事件循环, 表现为 meta 事件后长时间无响应
        # get_embedding_model 返回本地 bge 适配器或远端实现, 统一
        # get_text_embedding 接口 (适配器类型未导出, 标注为 Any)
        embed_model: Any = await asyncio.to_thread(get_embedding_model)
        if embed_model is None:
            raise ServiceUnavailableException(
                "Embedding 模型未初始化: 请检查 .env 中 "
                "LLM_EMBEDDING_API_KEY / LLM_EMBEDDING_API_BASE 配置"
            )

        query_embedding = await asyncio.to_thread(
            embed_model.get_text_embedding, question
        )
        return await asyncio.to_thread(
            query_chunks,
            question,
            top_k=int(rag_params["top_k"]),
            category_ids=category_ids or None,
            similarity_threshold=float(rag_params["similarity_threshold"]),
            query_embedding=query_embedding,
        )

    @staticmethod
    async def _load_history(
        db: AsyncSession,
        conversation_id: int,
        exclude_message_id: int,
    ) -> list[dict]:
        """
        加载最近 N 轮历史 (user/assistant 配对, N 取 sys_config chat_history_rounds,
        缺省 DEFAULT_HISTORY_ROUNDS), 排除刚入库的当前用户消息。
        """
        rounds_value = await ConfigService.get_value(
            db, "chat_history_rounds", DEFAULT_HISTORY_ROUNDS
        )
        try:
            rounds = int(rounds_value)
        except (TypeError, ValueError):
            rounds = DEFAULT_HISTORY_ROUNDS
        if rounds <= 0:
            return []

        result = await db.execute(
            select(RagMessage)
            .where(
                RagMessage.conversation_id == conversation_id,
                RagMessage.id != exclude_message_id,
                RagMessage.role.in_(["user", "assistant"]),
            )
            .order_by(RagMessage.id.desc())
            .limit(rounds * 2)
        )
        rows = list(reversed(list(result.scalars().all())))
        return build_history(rows)

    @staticmethod
    def _build_system_prompt(
        template: PtTemplate | None,
        question: str,
        context_text: str,
    ) -> str:
        """模板渲染 — 填充 {{context}} / {{question}} (模板全缺时用内置兜底)"""
        content = (
            template.template_content
            if template is not None
            else _DEFAULT_TEMPLATE_CONTENT
        )
        return render_template_content(content, question=question, context=context_text)

    @staticmethod
    async def _persist_failure(
        stream_db: AsyncSession,
        conversation_id: int,
        question: str,
        *,
        error: str,
        partial_answer: str = "",
        prompt_full: str | None = None,
        response_time_ms: int | None = None,
    ) -> None:
        """生成失败落库 assistant 消息 (error_message 记录原因), 尽力而为"""
        try:
            await stream_db.rollback()
            msg = RagMessage(
                conversation_id=conversation_id,
                role="assistant",
                question=question,
                answer=partial_answer or None,
                prompt_full=prompt_full,
                model_name=settings.LLM_MODEL_NAME,
                error_message=error,
                response_time_ms=response_time_ms,
            )
            stream_db.add(msg)
            await stream_db.commit()
            await stream_db.refresh(msg)
            await ConversationService.increment_message_count(
                stream_db, conversation_id
            )
            logger.info(f"[RAG] 失败消息已落库: message_id={msg.id}, error={error}")
        except Exception:
            logger.exception("[RAG] 失败消息落库失败")
            try:
                await stream_db.rollback()
            except Exception:
                pass
