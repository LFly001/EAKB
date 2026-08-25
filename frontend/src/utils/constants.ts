/**
 * 全局常量 (Phase 8 抽离 — 消除多文件重复定义)
 * Token 存储 Key / 向量化状态元数据 / 角色标签 / 分类树 props
 */

import type { VectorStatus } from "@/types/knowledge";

// ==========================================
// Token 存储 Key
// 注意: utils/storage 的 get/set 会自动拼 eakb_ 前缀, 而历史代码约定
// key 本身已含前缀 ("eakb_access_token"), 因此 localStorage 实际键为
// "eakb_eakb_access_token"。三处读写 (request/auth store/useSSE) 保持一致即可,
// 不要只改其中一处。
// ==========================================
export const TOKEN_KEY = "eakb_access_token";
export const REFRESH_TOKEN_KEY = "eakb_refresh_token";
export const USER_INFO_KEY = "eakb_user_info";

// ==========================================
// 向量化状态展示元数据 (DocumentList / DocumentDetail 共用)
// ==========================================
export interface VectorStatusMeta {
  label: string;
  type: "info" | "warning" | "success" | "danger";
}

export const VECTOR_STATUS_META: Record<VectorStatus, VectorStatusMeta> = {
  pending: { label: "待处理", type: "info" },
  processing: { label: "处理中", type: "warning" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
};

/** 状态标签元数据 (异常值兜底, 防止查表 undefined 导致整表渲染崩溃) */
export function vectorStatusMeta(status: string): VectorStatusMeta {
  return (
    VECTOR_STATUS_META[status as VectorStatus] ?? {
      label: status || "未知",
      type: "info",
    }
  );
}

// ==========================================
// 角色展示
// ==========================================
export const ROLE_LABELS: Record<string, string> = {
  admin: "管理员",
  employee: "员工",
};

export const ROLE_TAG_TYPES: Record<string, "danger" | "info"> = {
  admin: "danger",
  employee: "info",
};

// ==========================================
// el-tree-select 分类树 props (多页面重复定义统一)
// ==========================================
export const CATEGORY_TREE_PROPS = {
  label: "name",
  children: "children",
  value: "id",
} as const;
