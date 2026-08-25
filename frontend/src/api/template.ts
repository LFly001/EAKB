/**
 * 提示词模板 API
 * 列表 / 详情 / 创建 / 更新 / 删除 / 分类绑定 / 热门 / 渲染
 */
import request from "./request";
import type { APIResponse, PageResponse } from "@/types/common";
import type {
  TemplateBindRequest,
  TemplateBindResult,
  TemplateCreateRequest,
  TemplateInfo,
  TemplateListItem,
  TemplateQuery,
  TemplateRenderRequest,
  TemplateRenderResult,
  TemplateUpdateRequest,
} from "@/types/template";

// ==========================================
// 模板分页列表
// ==========================================
export function getTemplateListApi(
  params: TemplateQuery
): Promise<APIResponse<PageResponse<TemplateListItem>>> {
  return request.get("/templates/", { params });
}

// ==========================================
// 模板详情
// ==========================================
export function getTemplateDetailApi(
  templateId: number
): Promise<APIResponse<TemplateInfo>> {
  return request.get(`/templates/${templateId}`);
}

// ==========================================
// 创建模板
// ==========================================
export function createTemplateApi(
  data: TemplateCreateRequest
): Promise<APIResponse<TemplateInfo>> {
  return request.post("/templates/", data);
}

// ==========================================
// 更新模板
// ==========================================
export function updateTemplateApi(
  templateId: number,
  data: TemplateUpdateRequest
): Promise<APIResponse<TemplateInfo>> {
  return request.put(`/templates/${templateId}`, data);
}

// ==========================================
// 删除模板 (系统预置模板接口返回 403)
// ==========================================
export function deleteTemplateApi(
  templateId: number
): Promise<APIResponse<null>> {
  return request.delete(`/templates/${templateId}`);
}

// ==========================================
// 批量绑定分类 (追加语义)
// ==========================================
export function bindTemplateCategoriesApi(
  templateId: number,
  data: TemplateBindRequest
): Promise<APIResponse<TemplateBindResult>> {
  return request.post(`/templates/${templateId}/categories`, data);
}

// ==========================================
// 设置分类绑定 (整体替换, 空数组=清空绑定)
// ==========================================
export function setTemplateCategoriesApi(
  templateId: number,
  data: TemplateBindRequest
): Promise<APIResponse<TemplateBindResult>> {
  return request.put(`/templates/${templateId}/categories`, data);
}

// ==========================================
// 解绑单个分类
// ==========================================
export function unbindTemplateCategoryApi(
  templateId: number,
  categoryId: number
): Promise<APIResponse<null>> {
  return request.delete(`/templates/${templateId}/categories/${categoryId}`);
}

// ==========================================
// 热门模板 (按使用次数倒序, DESIGN.md 6.5)
// ==========================================
export function getPopularTemplatesApi(
  limit = 10
): Promise<APIResponse<TemplateListItem[]>> {
  return request.get("/templates/popular", { params: { limit } });
}

// ==========================================
// 按分类获取可用模板 (绑定该分类优先, Phase 5 问答自动匹配用)
// ==========================================
export function getTemplatesByCategoryApi(
  categoryId: number
): Promise<APIResponse<TemplateListItem[]>> {
  return request.get(`/templates/by-category/${categoryId}`);
}

// ==========================================
// 模板渲染 (预览 / 测试)
// ==========================================
export function renderTemplateApi(
  templateId: number,
  data: TemplateRenderRequest
): Promise<APIResponse<TemplateRenderResult>> {
  return request.post(`/templates/${templateId}/render`, data);
}
