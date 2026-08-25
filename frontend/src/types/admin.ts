/**
 * 管理后台类型定义 (Phase 7)
 * 数据看板 / 操作日志 / 系统配置
 */

/** 看板聚合统计 */
export interface DashboardStats {
  user_count: number;
  document_count: number;
  conversation_count: number;
  today_question_count: number;
  vectorized_document_count: number;
  today_operation_count: number;
}

/** 操作日志条目 */
export interface OperationLogInfo {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  module: string | null;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  status: string;
  error_info: string | null;
  created_at: string | null;
}

/** 操作日志查询参数 */
export interface LogQuery {
  page: number;
  page_size: number;
  username?: string;
  module?: string;
  action?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
}

/** 系统配置项 */
export interface ConfigItem {
  id: number;
  config_key: string;
  config_value: string | null;
  config_type: string;
  description: string | null;
  updated_by: number | null;
  updated_at: string | null;
  created_at: string | null;
}
