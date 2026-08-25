/**
 * 对话会话 API
 * 列表 / 新建 / 详情(含消息) / 删除 / 改标题
 */
import request from "./request";
import type { APIResponse, PageResponse } from "@/types/common";
import type {
  ConversationCreateRequest,
  ConversationDetail,
  ConversationInfo,
  ConversationQuery,
} from "@/types/chat";

// ==========================================
// 我的对话列表 (分页, 按更新时间倒序)
// ==========================================
export function getConversationListApi(
  params: ConversationQuery
): Promise<APIResponse<PageResponse<ConversationInfo>>> {
  return request.get("/rag/conversations/", { params });
}

// ==========================================
// 新建对话
// ==========================================
export function createConversationApi(
  data: ConversationCreateRequest
): Promise<APIResponse<ConversationInfo>> {
  return request.post("/rag/conversations/", data);
}

// ==========================================
// 对话详情 (含全部消息)
// ==========================================
export function getConversationDetailApi(
  conversationId: number
): Promise<APIResponse<ConversationDetail>> {
  return request.get(`/rag/conversations/${conversationId}`);
}

// ==========================================
// 删除对话
// ==========================================
export function deleteConversationApi(
  conversationId: number
): Promise<APIResponse<null>> {
  return request.delete(`/rag/conversations/${conversationId}`);
}

// ==========================================
// 修改对话标题
// ==========================================
export function updateConversationTitleApi(
  conversationId: number,
  title: string
): Promise<APIResponse<ConversationInfo>> {
  return request.put(`/rag/conversations/${conversationId}/title`, { title });
}
