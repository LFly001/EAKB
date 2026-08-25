/**
 * 管理后台 API (Phase 7) — 全部接口仅 admin 角色可访问
 */
import request from "./request";
import type { APIResponse, PageResponse } from "@/types/common";
import type {
  ConfigItem,
  DashboardStats,
  LogQuery,
  OperationLogInfo,
} from "@/types/admin";

// ==========================================
// 数据看板
// ==========================================
export function getDashboardApi(): Promise<APIResponse<DashboardStats>> {
  return request.get("/admin/dashboard");
}

// ==========================================
// 操作日志 (仅查询, 审计保留)
// ==========================================
export function getLogListApi(
  params: LogQuery
): Promise<APIResponse<PageResponse<OperationLogInfo>>> {
  return request.get("/admin/logs", { params });
}

// ==========================================
// 系统配置
// ==========================================
export function getConfigsApi(): Promise<APIResponse<ConfigItem[]>> {
  return request.get("/admin/configs");
}

export function updateConfigApi(
  key: string,
  configValue: string
): Promise<APIResponse<ConfigItem>> {
  return request.put(`/admin/configs/${key}`, { config_value: configValue });
}
