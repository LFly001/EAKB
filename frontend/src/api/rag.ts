/**
 * RAG 智能问答 API
 * 流式问答走 useSSE (fetch + ReadableStream, 不经 axios 拦截器),
 * 此处导出 SSE 路径常量与反馈等常规请求。
 */
import request from "./request";
import type { APIResponse } from "@/types/common";
import type { ChatMessage, MessageFeedbackRequest } from "@/types/chat";

// ==========================================
// SSE 流式问答 (DESIGN 6.6)
// ==========================================

/** 流式问答接口路径 — 与 VITE_SSE_BASE_URL 拼接后由 useSSE 发起 POST */
export const CHAT_STREAM_PATH = "/rag/chat-stream";

// ==========================================
// 消息反馈 (点赞/点踩 + 备注)
// ==========================================
export function submitMessageFeedbackApi(
  messageId: number,
  data: MessageFeedbackRequest
): Promise<APIResponse<ChatMessage>> {
  return request.post(`/rag/messages/${messageId}/feedback`, data);
}
