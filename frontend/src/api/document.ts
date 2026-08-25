/**
 * 知识库文档 API
 * 上传 / 列表 / 详情 / 下载 / 软删除 / 向量化 / 分块
 */
import request from "./request";
import type { APIResponse, PageResponse } from "@/types/common";
import type {
  DocumentChunkInfo,
  DocumentInfo,
  DocumentQuery,
  DownloadUrlResponse,
  VectorizeResult,
} from "@/types/knowledge";

// ==========================================
// 文档分页列表
// ==========================================
export function getDocumentListApi(
  params: DocumentQuery
): Promise<APIResponse<PageResponse<DocumentInfo>>> {
  return request.get("/documents/", { params });
}

// ==========================================
// 上传文档 (multipart, 支持多文件)
// ==========================================
export function uploadDocumentsApi(data: FormData): Promise<APIResponse<DocumentInfo[]>> {
  return request.post("/documents/upload", data, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000, // 大文件上传放宽超时
  });
}

// ==========================================
// 文档详情
// ==========================================
export function getDocumentDetailApi(
  documentId: number
): Promise<APIResponse<DocumentInfo>> {
  return request.get(`/documents/${documentId}`);
}

// ==========================================
// 下载 (返回预签名 URL)
// ==========================================
export function getDocumentDownloadApi(
  documentId: number
): Promise<APIResponse<DownloadUrlResponse>> {
  return request.get(`/documents/${documentId}/download`);
}

// ==========================================
// 软删除
// ==========================================
export function deleteDocumentApi(
  documentId: number
): Promise<APIResponse<null>> {
  return request.delete(`/documents/${documentId}`);
}

// ==========================================
// 触发向量化 (手动 / 失败重试)
// ==========================================
export function vectorizeDocumentApi(
  documentId: number
): Promise<APIResponse<DocumentInfo>> {
  return request.post(`/documents/${documentId}/vectorize`);
}

// ==========================================
// 批量向量化
// ==========================================
export function batchVectorizeApi(
  documentIds: number[]
): Promise<APIResponse<VectorizeResult[]>> {
  return request.post("/documents/batch-vectorize", {
    document_ids: documentIds,
  });
}

// ==========================================
// 查看分块列表
// ==========================================
export function getDocumentChunksApi(
  documentId: number,
  params: { page: number; page_size: number }
): Promise<APIResponse<PageResponse<DocumentChunkInfo>>> {
  return request.get(`/documents/${documentId}/chunks`, { params });
}
