/**
 * 认证模块 API
 */
import request from "./request";
import type { APIResponse } from "@/types/common";
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
} from "@/types/user";

// ==========================================
// 登录
// ==========================================
export function loginApi(data: LoginRequest): Promise<APIResponse<LoginResponse>> {
  return request.post("/auth/login", data);
}

// ==========================================
// 注册
// ==========================================
export function registerApi(data: RegisterRequest): Promise<APIResponse<null>> {
  return request.post("/auth/register", data);
}

// ==========================================
// 获取当前用户
// ==========================================
export function getMeApi(): Promise<APIResponse<any>> {
  return request.get("/auth/me");
}

// ==========================================
// 修改密码
// ==========================================
export function changePasswordApi(data: {
  old_password: string;
  new_password: string;
  confirm_password: string;
}): Promise<APIResponse<null>> {
  return request.put("/auth/password", data);
}

// ==========================================
// 更新个人信息
// ==========================================
export function updateProfileApi(data: {
  email?: string;
  phone?: string;
  real_name?: string;
}): Promise<APIResponse<any>> {
  return request.put("/auth/me", data);
}

// ==========================================
// 注销
// ==========================================
export function logoutApi(): Promise<APIResponse<null>> {
  return request.post("/auth/logout");
}

// ==========================================
// 刷新 Token
// ==========================================
export function refreshTokenApi(
  refreshToken: string
): Promise<APIResponse<{ access_token: string; refresh_token: string }>> {
  return request.post("/auth/refresh", { refresh_token: refreshToken });
}
