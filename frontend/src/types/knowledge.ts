/**
 * 知识库模块类型定义 (Phase 3)
 * 分类 / 文档 / 分块
 */

/** 向量化状态 */
export type VectorStatus = "pending" | "processing" | "completed" | "failed";

/** 文档状态 */
export type DocStatus = 1 | 0 | -1; // 1=发布 0=草稿 -1=已删除

// ==========================================
// 分类
// ==========================================

/** 分类树节点 */
export interface CategoryNode {
  id: number;
  name: string;
  parent_id: number | null;
  description: string | null;
  icon: string | null;
  sort_order: number;
  status: number;
  created_by: number | null;
  created_at: string;
  updated_at: string | null;
  document_count: number;
  children: CategoryNode[];
}

/** 创建分类请求 */
export interface CategoryCreateRequest {
  name: string;
  parent_id?: number | null;
  description?: string;
  icon?: string;
  sort_order?: number;
}

/** 更新分类请求 */
export interface CategoryUpdateRequest {
  name?: string;
  parent_id?: number | null;
  description?: string;
  icon?: string;
  sort_order?: number;
  status?: number;
}

/** 拖拽排序请求 */
export interface CategoryMoveRequest {
  parent_id?: number | null;
  sort_order?: number;
}

// ==========================================
// 文档
// ==========================================

/** 文档信息 */
export interface DocumentInfo {
  id: number;
  title: string;
  category_id: number;
  category_name?: string | null;
  file_name: string;
  file_type: string;
  file_size: number;
  file_path: string;
  file_hash: string | null;
  vector_status: VectorStatus;
  chunk_count: number;
  description: string | null;
  tags: string | null;
  view_count: number;
  download_count: number;
  status: DocStatus;
  uploaded_by: number | null;
  uploader_name?: string | null;
  vectorized_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string | null;
}

/** 文档列表查询参数 */
export interface DocumentQuery {
  page: number;
  page_size: number;
  keyword?: string;
  category_id?: number;
  vector_status?: VectorStatus;
  file_type?: string;
  status?: DocStatus;
}

/** 文档分块 */
export interface DocumentChunkInfo {
  id: number;
  document_id: number;
  chunk_index: number;
  chunk_text: string;
  chunk_hash: string | null;
  chroma_chunk_id: string | null;
  token_count: number | null;
  created_at: string | null;
}

/** 批量向量化结果项 */
export interface VectorizeResult {
  document_id: number;
  triggered: boolean;
  message: string;
}

/** 下载地址响应 */
export interface DownloadUrlResponse {
  document_id: number;
  file_name: string;
  download_url: string;
  expires_in: number;
}
