/**
 * 知识图谱 API (Phase 6)
 * 实体列表 / 实体详情 / 搜索全景 / 图谱构建
 */
import request from "./request";
import type { APIResponse, PageResponse } from "@/types/common";
import type {
  EntityDetail,
  EntityListItem,
  GraphSearchResponse,
} from "@/types/graph";

// ==========================================
// 实体分页列表
// ==========================================
export function getGraphEntitiesApi(params: {
  page: number;
  page_size: number;
  keyword?: string;
  type?: string;
}): Promise<APIResponse<PageResponse<EntityListItem>>> {
  return request.get("/graph/entities/", { params });
}

// ==========================================
// 实体详情 (name 可能含中文/特殊字符, 必须编码)
// ==========================================
export function getGraphEntityDetailApi(
  name: string
): Promise<APIResponse<EntityDetail>> {
  return request.get(`/graph/entities/${encodeURIComponent(name)}`);
}

// ==========================================
// 图谱搜索 / 画布全景 (空 keyword = 全景)
// ==========================================
export function getGraphSearchApi(
  keyword?: string
): Promise<APIResponse<GraphSearchResponse>> {
  return request.get("/graph/search", {
    params: keyword ? { keyword } : {},
  });
}

// ==========================================
// 触发图谱构建 (admin; 空 documentId = 全量重建)
// ==========================================
export function buildGraphApi(
  documentId?: number | null
): Promise<APIResponse<null>> {
  return request.post("/graph/build", documentId ? { document_id: documentId } : {});
}
