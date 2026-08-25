/**
 * 智能问答模块类型定义 (Phase 5)
 * 对话会话 / 消息 / SSE 流式事件 / 反馈
 */

// ==========================================
// 对话会话
// ==========================================

/** 对话会话摘要 */
export interface ConversationInfo {
  id: number;
  title: string;
  template_id: number | null;
  category_ids: number[];
  message_count: number;
  status: "active" | "ended";
  created_at: string | null;
  updated_at: string | null;
  ended_at: string | null;
}

/** 对话详情 — 会话信息 + 全部消息 (时间正序) */
export interface ConversationDetail extends ConversationInfo {
  messages: ChatMessage[];
}

/** 新建对话请求 */
export interface ConversationCreateRequest {
  title?: string;
  template_id?: number | null;
  category_ids?: number[];
}

/** 对话列表查询参数 */
export interface ConversationQuery {
  page: number;
  page_size: number;
  keyword?: string;
}

// ==========================================
// 消息
// ==========================================

/** 检索分块 (retrieved_chunks JSON 结构, DESIGN 4.1.8) */
export interface RetrievedChunk {
  chunk_id: string;
  document_id: number | null;
  title: string;
  text: string;
  score: number;
}

/** 来源文档 (sources JSON 结构, DESIGN 4.1.8) */
export interface MessageSource {
  document_id: number;
  title: string;
  file_name: string;
  relevance_score: number;
}

/** Token 用量 */
export interface TokenUsage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
}

/** 对话消息 */
export interface ChatMessage {
  id: number;
  conversation_id: number;
  role: "user" | "assistant" | "system";
  question: string | null;
  answer: string | null;
  prompt_full: string | null;
  retrieved_chunks: RetrievedChunk[];
  sources: MessageSource[];
  model_name: string | null;
  token_usage: TokenUsage | null;
  response_time_ms: number | null;
  feedback: "positive" | "negative" | null;
  feedback_comment: string | null;
  error_message: string | null;
  created_at: string | null;
}

/** 流式生成中的助手消息占位 (本地状态, 尚未落库) */
export interface StreamingAssistantMessage {
  /** 已接收的回答文本 */
  content: string;
  /** 检索来源 (sources 事件到达后填充) */
  sources: MessageSource[];
  retrieved_chunks: RetrievedChunk[];
  /** 生成失败原因 (error 事件 / 断线) */
  error: string | null;
  /** 完成后的落库消息 (done 事件) */
  done: ChatDoneEvent | null;
}

// ==========================================
// 问答请求
// ==========================================

/** 流式问答请求体 (POST /rag/chat-stream) */
export interface ChatStreamRequest {
  question: string;
  conversation_id?: number | null;
  template_id?: number | null;
  category_ids?: number[];
}

// ==========================================
// SSE 事件负载 (协议见 docs/api-reference.md)
// ==========================================

/** meta 事件 — 流开始 */
export interface ChatMetaEvent {
  conversation_id: number;
  user_message_id: number;
  template_id: number | null;
  template_name: string | null;
}

/** sources 事件 — 检索完成后推送来源 */
export interface ChatSourcesEvent {
  sources: MessageSource[];
  retrieved_chunks: RetrievedChunk[];
}

/** done 事件 — 生成完成 */
export interface ChatDoneEvent {
  conversation_id: number;
  message_id: number;
  token_usage: TokenUsage | null;
  response_time_ms: number | null;
}

// ==========================================
// 反馈
// ==========================================

/** 回答反馈请求 (POST /rag/messages/{id}/feedback) */
export interface MessageFeedbackRequest {
  feedback: "positive" | "negative";
  comment?: string;
}
