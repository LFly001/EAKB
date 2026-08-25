/**
 * 通用类型定义
 * Phase 1: 基础分页/响应类型
 */

/** 统一 API 响应包装 */
export interface APIResponse<T = unknown> {
  code: number;
  msg: string;
  data: T;
}

/** 分页响应 */
export interface PageResponse<T> {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: T[];
}

/** 分页查询参数 */
export interface PageQuery {
  page: number;
  page_size: number;
  keyword?: string;
}

/** 通用下拉/选择项 */
export interface SelectOption {
  label: string;
  value: string | number;
  disabled?: boolean;
  children?: SelectOption[];
}
