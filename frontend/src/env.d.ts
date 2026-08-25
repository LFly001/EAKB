/// <reference types="vite/client" />

// ==========================================
// 环境变量类型声明
// ==========================================
interface ImportMetaEnv {
  /** 应用标题 */
  readonly VITE_APP_TITLE: string;
  /** API 基础路径 */
  readonly VITE_API_BASE_URL: string;
  /** SSE 基础路径 */
  readonly VITE_SSE_BASE_URL: string;
  /** 是否启用 Mock */
  readonly VITE_ENABLE_MOCK: string;
  /** 日志级别 */
  readonly VITE_LOG_LEVEL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// ==========================================
// Vue 单文件组件类型声明
// ==========================================
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

// ==========================================
// Less 模块声明
// ==========================================
declare module "*.less" {
  const content: Record<string, string>;
  export default content;
}
