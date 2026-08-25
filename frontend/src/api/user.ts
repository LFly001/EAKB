/**
 * 用户管理 API (管理员)
 */
import request from "./request";
import type { APIResponse, PageResponse } from "@/types/common";
import type { UserInfo } from "@/types/user";

// ==========================================
// 用户列表 (管理员)
// ==========================================
export function getUserListApi(params: {
  page: number;
  page_size: number;
  keyword?: string;
  role?: string;
  status?: number;
}): Promise<APIResponse<PageResponse<UserInfo>>> {
  return request.get("/users/", { params });
}

// ==========================================
// 用户详情
// ==========================================
export function getUserDetailApi(
  userId: number
): Promise<APIResponse<UserInfo>> {
  return request.get(`/users/${userId}`);
}

// ==========================================
// 创建用户 (管理员)
// ==========================================
export function createUserApi(data: {
  username: string;
  password: string;
  email?: string;
  phone?: string;
  real_name?: string;
  department?: string;
  position?: string;
  role?: string;
  status?: number;
}): Promise<APIResponse<UserInfo>> {
  return request.post("/users/", data);
}

// ==========================================
// 更新用户 (管理员)
// ==========================================
export function updateUserApi(
  userId: number,
  data: Record<string, any>
): Promise<APIResponse<UserInfo>> {
  return request.put(`/users/${userId}`, data);
}

// ==========================================
// 启用/禁用用户 (管理员)
// ==========================================
export function toggleUserStatusApi(
  userId: number,
  status: number
): Promise<APIResponse<UserInfo>> {
  return request.put(`/users/${userId}/status`, { status });
}

// ==========================================
// 删除用户 (管理员)
// ==========================================
export function deleteUserApi(
  userId: number
): Promise<APIResponse<null>> {
  return request.delete(`/users/${userId}`);
}

// ==========================================
// 批量用户操作 (Phase 7)
// ==========================================
export function batchUserApi(data: {
  user_ids: number[];
  action: "enable" | "disable" | "delete";
}): Promise<APIResponse<{ count: number; users: string[] }>> {
  return request.post("/users/batch", data);
}
