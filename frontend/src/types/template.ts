/**
 * 提示词模板模块类型定义 (Phase 4)
 * 模板 CRUD / 分类绑定 / 变量结构 / 渲染
 */

// ==========================================
// 变量结构 (仅支持 {{question}} / {{context}})
// ==========================================

/** 单个模板变量定义 */
export interface TemplateVariable {
  type: string;
  description: string;
  required: boolean;
  default: string;
}

/** 模板变量集合 — 固定 question / context 两项 */
export interface TemplateVariables {
  question: TemplateVariable;
  context: TemplateVariable;
}

// ==========================================
// 模板
// ==========================================

/** 模板列表项 (不含 template_content) */
export interface TemplateListItem {
  id: number;
  name: string;
  description: string | null;
  category_id: number | null;
  category_name: string | null;
  tags: string | null;
  usage_count: number;
  is_system: number; // 1=系统预置 0=用户自定义
  status: number; // 1=启用 0=禁用
  created_by: number | null;
  creator_name: string | null;
  category_ids: number[];
  category_names: string[];
  created_at: string;
  updated_at: string | null;
}

/** 模板详情 — 在列表项基础上携带完整内容与变量定义 */
export interface TemplateInfo extends TemplateListItem {
  template_content: string;
  variables: TemplateVariables;
}

/** 模板列表查询参数 */
export interface TemplateQuery {
  page: number;
  page_size: number;
  keyword?: string;
  category_id?: number;
  is_system?: 0 | 1;
  tag?: string;
  status?: 0 | 1;
}

/** 创建模板请求 */
export interface TemplateCreateRequest {
  name: string;
  description?: string;
  category_id?: number | null;
  template_content: string;
  variables?: TemplateVariables;
  tags?: string;
  status?: 0 | 1;
}

/** 更新模板请求 */
export interface TemplateUpdateRequest {
  name?: string;
  description?: string;
  category_id?: number | null;
  template_content?: string;
  variables?: TemplateVariables;
  tags?: string;
  status?: 0 | 1;
}

/** 绑定/设置分类请求 (空数组=清空绑定) */
export interface TemplateBindRequest {
  category_ids: number[];
}

/** 分类绑定结果 */
export interface TemplateBindResult {
  template_id: number;
  category_ids: number[];
}

/** 渲染请求 — 填充 {{question}}/{{context}} */
export interface TemplateRenderRequest {
  question: string;
  context?: string;
}

/** 渲染结果 */
export interface TemplateRenderResult {
  template_id: number;
  template_name: string;
  variables: { question: string; context: string };
  rendered: string;
}
