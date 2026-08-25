/**
 * 智能问答状态管理 — Pinia (Phase 5)
 * 管理: 会话列表/详情、消息流、SSE 流式生成状态、来源引用面板、输入偏好
 *
 * 说明: 不配置持久化 — 流式状态与草稿不应跨会话保留, 页面重载后重新加载详情。
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import {
  deleteConversationApi,
  getConversationDetailApi,
  getConversationListApi,
  updateConversationTitleApi,
} from "@/api/conversation";
import { submitMessageFeedbackApi } from "@/api/rag";
import type {
  ChatDoneEvent,
  ChatMessage,
  ChatSourcesEvent,
  ConversationInfo,
  MessageSource,
  RetrievedChunk,
  StreamingAssistantMessage,
} from "@/types/chat";

/** 本地临时消息 ID 生成器 (负数, 保证列表 key 唯一) */
let tempIdCounter = -1000;
function nextTempId(): number {
  tempIdCounter -= 1;
  return tempIdCounter;
}

export const useChatStore = defineStore("chat", () => {
  // ==========================================
  // 会话列表
  // ==========================================
  const conversations = ref<ConversationInfo[]>([]);
  const conversationsTotal = ref(0);
  const conversationsLoading = ref(false);

  // ==========================================
  // 当前会话
  // ==========================================
  const currentConversationId = ref<number | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const detailLoading = ref(false);

  // ==========================================
  // 流式生成状态
  // ==========================================
  const streaming = ref(false);
  /** 流式中的助手占位消息 (未落库) */
  const streamingMessage = ref<StreamingAssistantMessage | null>(null);
  /** 本次流对应的用户消息 (落库前临时 ID, meta 事件回填) */
  const streamingUserMessage = ref<ChatMessage | null>(null);
  /** 最近一次提问 (断线重试用) */
  const lastQuestion = ref("");

  // ==========================================
  // 输入偏好 (模板 / 分类限定)
  // ==========================================
  const draftTemplateId = ref<number | null>(null);
  const draftCategoryIds = ref<number[]>([]);

  // ==========================================
  // 来源引用面板
  // ==========================================
  const selectedSources = ref<{
    sources: MessageSource[];
    retrieved_chunks: RetrievedChunk[];
  } | null>(null);

  // ==========================================
  // Actions — 会话列表
  // ==========================================

  async function loadConversations(keyword?: string) {
    conversationsLoading.value = true;
    try {
      const res = await getConversationListApi({
        page: 1,
        page_size: 100,
        keyword,
      });
      conversations.value = res.data?.items || [];
      conversationsTotal.value = res.data?.total || 0;
    } finally {
      conversationsLoading.value = false;
    }
  }

  async function refreshConversation(id: number) {
    const res = await getConversationListApi({ page: 1, page_size: 100 });
    const list = res.data?.items || [];
    // 新会话未出现在前 100 条时, 单独拉详情补位
    const current = list.find((c) => c.id === id);
    if (current) {
      conversations.value = list;
    } else {
      conversations.value = list;
      try {
        const detailRes = await getConversationDetailApi(id);
        conversations.value.unshift(detailRes.data);
      } catch {
        // 详情拉取失败不阻断列表刷新
      }
    }
  }

  // ==========================================
  // Actions — 会话详情
  // ==========================================

  /** 切换到指定会话并加载消息 */
  async function loadDetail(conversationId: number) {
    detailLoading.value = true;
    try {
      const res = await getConversationDetailApi(conversationId);
      const detail = res.data;
      currentConversationId.value = detail.id;
      messages.value = detail.messages || [];
      // 输入偏好跟随会话 (模板 / 分类限定)
      draftTemplateId.value = detail.template_id;
      draftCategoryIds.value = detail.category_ids || [];
    } finally {
      detailLoading.value = false;
    }
  }

  /** 重置为新对话 (未落库状态) */
  function resetConversation() {
    currentConversationId.value = null;
    messages.value = [];
    draftTemplateId.value = null;
    draftCategoryIds.value = [];
    clearSelectedSources();
  }

  // ==========================================
  // Actions — 会话操作
  // ==========================================

  async function removeConversation(id: number) {
    await deleteConversationApi(id);
    conversations.value = conversations.value.filter((c) => c.id !== id);
    if (currentConversationId.value === id) {
      resetConversation();
    }
  }

  async function renameConversation(id: number, title: string) {
    const res = await updateConversationTitleApi(id, title);
    const info = res.data;
    const target = conversations.value.find((c) => c.id === id);
    if (target) {
      target.title = info.title;
    }
  }

  // ==========================================
  // Actions — 反馈
  // ==========================================

  async function submitFeedback(
    messageId: number,
    feedback: "positive" | "negative",
    comment?: string
  ) {
    const res = await submitMessageFeedbackApi(messageId, { feedback, comment });
    const updated = res.data;
    const target = messages.value.find((m) => m.id === messageId);
    if (target) {
      target.feedback = updated.feedback;
      target.feedback_comment = updated.feedback_comment;
    }
  }

  // ==========================================
  // Actions — 流式生成
  // ==========================================

  /** 发送提问: 本地挂用户消息 + 助手占位消息 */
  function beginStream(question: string) {
    lastQuestion.value = question;
    streaming.value = true;
    streamingMessage.value = {
      content: "",
      sources: [],
      retrieved_chunks: [],
      error: null,
      done: null,
    };
    streamingUserMessage.value = {
      id: -Date.now(), // 临时 ID, meta 事件回填真实 ID
      conversation_id: currentConversationId.value ?? -1,
      role: "user",
      question,
      answer: null,
      prompt_full: null,
      retrieved_chunks: [],
      sources: [],
      model_name: null,
      token_usage: null,
      response_time_ms: null,
      feedback: null,
      feedback_comment: null,
      error_message: null,
      created_at: null,
    };
    messages.value.push(streamingUserMessage.value);
    clearSelectedSources();
  }

  /** meta 事件 — 回填会话/用户消息 ID */
  function applyMeta(conversationId: number, userMessageId: number) {
    currentConversationId.value = conversationId;
    if (streamingUserMessage.value) {
      streamingUserMessage.value.id = userMessageId;
      streamingUserMessage.value.conversation_id = conversationId;
    }
  }

  /** sources 事件 — 填充来源引用 */
  function applySources(data: ChatSourcesEvent) {
    if (streamingMessage.value) {
      streamingMessage.value.sources = data.sources || [];
      streamingMessage.value.retrieved_chunks = data.retrieved_chunks || [];
    }
  }

  /** delta 事件 — 追加文本增量 */
  function appendDelta(content: string) {
    if (streamingMessage.value) {
      streamingMessage.value.content += content;
    }
  }

  /** done 事件 — 占位消息转正式消息 */
  function finishStream(done: ChatDoneEvent) {
    const place = streamingMessage.value;
    const userMsg = streamingUserMessage.value;
    if (place) {
      const message: ChatMessage = {
        id: done.message_id,
        conversation_id: done.conversation_id,
        role: "assistant",
        question: userMsg?.question ?? null,
        answer: place.content,
        prompt_full: null,
        retrieved_chunks: place.retrieved_chunks,
        sources: place.sources,
        model_name: null,
        token_usage: done.token_usage,
        response_time_ms: done.response_time_ms,
        feedback: null,
        feedback_comment: null,
        error_message: null,
        created_at: new Date().toISOString(),
      };
      messages.value.push(message);
    }
    clearStreamState();
    // 会话列表元数据刷新 (新会话标题 / 消息轮数)
    if (done.conversation_id) {
      refreshConversation(done.conversation_id);
    }
  }

  /** error 事件 / 断线 — 占位消息标记失败并保留在列表中 (含已生成内容) */
  function failStream(error: string) {
    if (streamingMessage.value) {
      streamingMessage.value.error = error;
    }
    streaming.value = false;
    streamingUserMessage.value = null;
  }

  /** 清空流式状态 (成功/中止时占位消息一并移除) */
  function clearStreamState() {
    streaming.value = false;
    streamingMessage.value = null;
    streamingUserMessage.value = null;
  }

  /** 中止流式 (用户点击停止) — 保留已生成的部分内容并标记「已停止生成」 */
  function abortStream() {
    const place = streamingMessage.value;
    if (place && place.content) {
      // 服务端断连时也会把部分回答落库 (error_message=连接中断),
      // 这里先生成本地消息即时展示, 页面重载后由服务端数据替换
      const message: ChatMessage = {
        id: nextTempId(), // 本地临时 ID (不参与反馈, 重载后消失)
        conversation_id: currentConversationId.value ?? -1,
        role: "assistant",
        question: lastQuestion.value,
        answer: place.content,
        prompt_full: null,
        retrieved_chunks: place.retrieved_chunks,
        sources: place.sources,
        model_name: null,
        token_usage: null,
        response_time_ms: null,
        feedback: null,
        feedback_comment: null,
        error_message: "已停止生成",
        created_at: null,
      };
      messages.value.push(message);
    }
    // 用户问题气泡保留: 服务端已在流开始前落库该消息
    clearStreamState();
  }

  // ==========================================
  // Actions — 来源引用面板
  // ==========================================

  function openSources(sourceData: {
    sources: MessageSource[];
    retrieved_chunks: RetrievedChunk[];
  }) {
    selectedSources.value = sourceData;
  }

  function clearSelectedSources() {
    selectedSources.value = null;
  }

  return {
    // 会话列表
    conversations,
    conversationsTotal,
    conversationsLoading,
    loadConversations,
    // 当前会话
    currentConversationId,
    messages,
    detailLoading,
    loadDetail,
    resetConversation,
    // 会话操作
    removeConversation,
    renameConversation,
    // 反馈
    submitFeedback,
    // 流式
    streaming,
    streamingMessage,
    lastQuestion,
    beginStream,
    applyMeta,
    applySources,
    appendDelta,
    finishStream,
    failStream,
    abortStream,
    // 输入偏好
    draftTemplateId,
    draftCategoryIds,
    // 来源面板
    selectedSources,
    openSources,
    clearSelectedSources,
  };
});
