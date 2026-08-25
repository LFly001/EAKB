/**
 * 用户相关类型定义
 */

/** 用户角色 */
export type UserRole = "admin" | "employee";

/** 用户状态 */
export type UserStatus = 1 | 0; // 1=启用 0=禁用

/** 用户基本信息 */
export interface UserInfo {
  id: number;
  username: string;
  email: string;
  phone: string;
  real_name: string;
  department: string;
  position: string;
  avatar_url: string;
  role: UserRole;
  status: UserStatus;
  last_login_at: string | null;
  created_at: string;
}

/** 登录请求 */
export interface LoginRequest {
  username: string;
  password: string;
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserInfo;
}

/** 注册请求 */
export interface RegisterRequest {
  username: string;
  password: string;
  confirm_password: string;
  email?: string;
  phone?: string;
  real_name?: string;
}

/** 修改密码请求 */
export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}
