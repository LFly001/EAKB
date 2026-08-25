/**
 * 知识库分类 API
 */
import request from "./request";
import type { APIResponse } from "@/types/common";
import type {
  CategoryCreateRequest,
  CategoryMoveRequest,
  CategoryNode,
  CategoryUpdateRequest,
} from "@/types/knowledge";

// ==========================================
// 分类树
// ==========================================
export function getCategoryTreeApi(): Promise<APIResponse<CategoryNode[]>> {
  return request.get("/categories/");
}

// ==========================================
// 创建分类
// ==========================================
export function createCategoryApi(
  data: CategoryCreateRequest
): Promise<APIResponse<CategoryNode>> {
  return request.post("/categories/", data);
}

// ==========================================
// 更新分类
// ==========================================
export function updateCategoryApi(
  categoryId: number,
  data: CategoryUpdateRequest
): Promise<APIResponse<CategoryNode>> {
  return request.put(`/categories/${categoryId}`, data);
}

// ==========================================
// 拖拽排序 (变更父级 / 同级顺序)
// ==========================================
export function moveCategoryApi(
  categoryId: number,
  data: CategoryMoveRequest
): Promise<APIResponse<CategoryNode>> {
  return request.put(`/categories/${categoryId}/move`, data);
}

// ==========================================
// 删除分类
// ==========================================
export function deleteCategoryApi(
  categoryId: number
): Promise<APIResponse<null>> {
  return request.delete(`/categories/${categoryId}`);
}
