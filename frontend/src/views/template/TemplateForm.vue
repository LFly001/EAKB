<script setup lang="ts">
/**
 * 模板新建 / 编辑共用表单
 * - 可视化编辑模板内容: 变量快捷插入 + 实时渲染预览 + 非法变量提示
 * - 变量定义编辑 (仅 {{question}} / {{context}} 两项, 可改说明/必填)
 * - 配置默认分类与关联知识库分类 (编辑时整体替换绑定)
 */
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type InputInstance } from "element-plus";
import {
  createTemplateApi,
  getTemplateDetailApi,
  renderTemplateApi,
  setTemplateCategoriesApi,
  updateTemplateApi,
} from "@/api/template";
import { getCategoryTreeApi } from "@/api/category";
import type { CategoryNode } from "@/types/knowledge";
import type {
  TemplateRenderResult,
  TemplateVariables,
} from "@/types/template";

const route = useRoute();
const router = useRouter();

// ==========================================
// 状态
// ==========================================

const templateId = computed(() =>
  route.params.id ? Number(route.params.id) : null
);
const isEdit = computed(() => templateId.value !== null);

const loading = ref(false);
const saving = ref(false);
const categoryTree = ref<CategoryNode[]>([]);
const contentInputRef = ref<InputInstance>();
const renderDialogVisible = ref(false);
const renderResult = ref<TemplateRenderResult | null>(null);
const renderLoading = ref(false);

// 占位符字面量 (模板插值里不能直接写 "}}" 字符串, 需经常量绑定)
const QUESTION_TOKEN = "{{question}}";
const CONTEXT_TOKEN = "{{context}}";

// 预览样例值 (渲染 {{question}} / {{context}} 占位符)
const previewQuestion = ref("员工年假可以休多少天？");
const previewContext = ref("【来源: 考勤管理制度】员工工作满一年后可享受带薪年假，具体天数按工龄计算……");

const form = reactive({
  name: "",
  description: "",
  category_id: null as number | null,
  template_content: "",
  variables: {
    question: { type: "string", description: "用户问题", required: true, default: "" },
    context: { type: "string", description: "检索到的知识库上下文", required: true, default: "" },
  } as TemplateVariables,
  tags: "",
  status: 1 as 0 | 1,
  category_ids: [] as number[],
});

// ==========================================
// 占位符校验与实时预览
// ==========================================

/** 提取内容中的全部 {{xxx}} 占位符 */
function extractPlaceholders(content: string): string[] {
  const names: string[] = [];
  const pattern = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(content)) !== null) {
    if (!names.includes(match[1])) names.push(match[1]);
  }
  return names;
}

/** 非法占位符 (仅允许 question/context) */
const invalidPlaceholders = computed(() =>
  extractPlaceholders(form.template_content).filter(
    (name) => name !== "question" && name !== "context"
  )
);

/** 实时渲染预览 */
const renderedPreview = computed(() =>
  form.template_content
    .replace(/\{\{\s*context\s*\}\}/g, previewContext.value || "(上下文为空)")
    .replace(/\{\{\s*question\s*\}\}/g, previewQuestion.value || "(问题为空)")
);

// ==========================================
// 变量快捷插入 (光标位置插入)
// ==========================================

function insertVariable(name: "question" | "context") {
  const textarea = (contentInputRef.value as unknown as { textarea?: HTMLTextAreaElement })
    ?.textarea;
  const token = `{{${name}}}`;

  if (textarea) {
    const start = textarea.selectionStart ?? form.template_content.length;
    const end = textarea.selectionEnd ?? start;
    form.template_content =
      form.template_content.slice(0, start) + token + form.template_content.slice(end);
    nextTick(() => {
      textarea.focus();
      textarea.setSelectionRange(start + token.length, start + token.length);
    });
  } else {
    form.template_content += token;
  }
}

// ==========================================
// 数据加载 / 保存
// ==========================================

async function loadCategories() {
  const res = await getCategoryTreeApi();
  categoryTree.value = res.data || [];
}

async function loadDetail() {
  if (templateId.value === null) return;
  loading.value = true;
  try {
    const res = await getTemplateDetailApi(templateId.value);
    const t = res.data;
    if (!t) return;
    form.name = t.name;
    form.description = t.description || "";
    form.category_id = t.category_id;
    form.template_content = t.template_content;
    form.variables = t.variables;
    form.tags = t.tags || "";
    form.status = (t.status === 1 ? 1 : 0) as 0 | 1;
    form.category_ids = t.category_ids || [];
  } finally {
    loading.value = false;
  }
}

function buildPayload() {
  return {
    name: form.name,
    description: form.description || undefined,
    category_id: form.category_id,
    template_content: form.template_content,
    variables: form.variables,
    tags: form.tags || undefined,
    status: form.status,
  };
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning("请输入模板名称");
    return;
  }
  if (!form.template_content.trim()) {
    ElMessage.warning("请输入模板内容");
    return;
  }
  if (invalidPlaceholders.value.length > 0) {
    ElMessage.warning(
      `模板内容包含不支持的变量: ${invalidPlaceholders.value
        .map((v) => `{{${v}}}`)
        .join(", ")}，仅支持 {{question}} / {{context}}`
    );
    return;
  }

  saving.value = true;
  try {
    let id: number;
    if (isEdit.value && templateId.value !== null) {
      await updateTemplateApi(templateId.value, buildPayload());
      id = templateId.value;
    } else {
      const res = await createTemplateApi(buildPayload());
      id = res.data!.id;
    }
    // 保存分类绑定 (整体替换)
    await setTemplateCategoriesApi(id, { category_ids: form.category_ids });
    ElMessage.success(isEdit.value ? "模板更新成功" : "模板创建成功");
    router.push("/templates");
  } finally {
    saving.value = false;
  }
}

async function handleCancel() {
  if (isEdit.value) {
    router.push("/templates");
    return;
  }
  try {
    await ElMessageBox.confirm("确定放弃当前编辑内容吗？", "离开确认", {
      type: "warning",
      confirmButtonText: "离开",
      cancelButtonText: "继续编辑",
    });
    router.push("/templates");
  } catch {
    /* 用户取消 */
  }
}

// ==========================================
// 服务端渲染测试
// ==========================================

async function handleRenderTest() {
  if (templateId.value === null) {
    ElMessage.warning("请先保存模板后再测试渲染");
    return;
  }
  renderLoading.value = true;
  try {
    const res = await renderTemplateApi(templateId.value, {
      question: previewQuestion.value,
      context: previewContext.value,
    });
    renderResult.value = res.data ?? null;
    renderDialogVisible.value = true;
  } finally {
    renderLoading.value = false;
  }
}

onMounted(() => {
  loadCategories();
  if (isEdit.value) {
    loadDetail();
  }
});
</script>

<template>
  <div class="page-container" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">{{ isEdit ? "编辑模板" : "新建模板" }}</span>
          <el-button @click="handleCancel">返回列表</el-button>
        </div>
      </template>

      <el-form label-width="110px" class="template-form">
        <el-form-item label="模板名称" required>
          <el-input v-model="form.name" maxlength="200" show-word-limit placeholder="请输入模板名称" />
        </el-form-item>

        <el-form-item label="模板描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            maxlength="2000"
            placeholder="简要描述模板用途与适用场景"
          />
        </el-form-item>

        <el-form-item label="默认分类">
          <el-tree-select
            v-model="form.category_id"
            :data="categoryTree"
            :props="({ label: 'name', children: 'children', value: 'id' } as any)"
            node-key="id"
            check-strictly
            clearable
            placeholder="选择默认关联的知识库分类（可不选）"
            style="width: 100%"
          />
        </el-form-item>

        <!-- 模板内容: 可视化编辑 -->
        <el-form-item label="模板内容" required>
          <div class="content-editor">
            <div class="editor-toolbar">
              <span class="toolbar-tip">插入变量:</span>
              <el-button size="small" @click="insertVariable('question')">
                <el-icon><Plus /></el-icon>插入 {{ QUESTION_TOKEN }}
              </el-button>
              <el-button size="small" @click="insertVariable('context')">
                <el-icon><Plus /></el-icon>插入 {{ CONTEXT_TOKEN }}
              </el-button>
            </div>
            <el-input
              ref="contentInputRef"
              v-model="form.template_content"
              type="textarea"
              :rows="10"
              placeholder="输入提示词内容，可插入 {{question}} 与 {{context}} 变量"
            />
            <el-alert
              v-if="invalidPlaceholders.length > 0"
              type="error"
              :closable="false"
              class="placeholder-alert"
              :title="`检测到不支持的变量: ${invalidPlaceholders.map((v) => `{{${v}}}`).join(', ')}，仅支持 {{question}} / {{context}}`"
            />
          </div>
        </el-form-item>

        <!-- 变量定义 -->
        <el-form-item label="变量定义">
          <div class="variables-editor">
            <div class="variable-card">
              <div class="variable-head">
                <el-tag size="small" type="primary">{{ QUESTION_TOKEN }}</el-tag>
                <span class="variable-label">用户问题</span>
                <el-switch v-model="form.variables.question.required" active-text="必填" />
              </div>
              <el-input
                v-model="form.variables.question.description"
                placeholder="变量说明"
                maxlength="200"
              />
            </div>
            <div class="variable-card">
              <div class="variable-head">
                <el-tag size="small" type="success">{{ CONTEXT_TOKEN }}</el-tag>
                <span class="variable-label">知识库上下文</span>
                <el-switch v-model="form.variables.context.required" active-text="必填" />
              </div>
              <el-input
                v-model="form.variables.context.description"
                placeholder="变量说明"
                maxlength="200"
              />
            </div>
          </div>
        </el-form-item>

        <el-form-item label="标签">
          <el-input
            v-model="form.tags"
            maxlength="500"
            placeholder="多个标签用逗号分隔，如: 通用,简洁"
          />
        </el-form-item>

        <el-form-item label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" active-text="启用" inactive-text="禁用" />
        </el-form-item>

        <el-form-item label="关联分类">
          <el-tree-select
            v-model="form.category_ids"
            :data="categoryTree"
            :props="({ label: 'name', children: 'children', value: 'id' } as any)"
            node-key="id"
            multiple
            show-checkbox
            clearable
            placeholder="选择模板适用的知识库分类（问答时按分类匹配）"
            style="width: 100%"
          />
        </el-form-item>

        <!-- 实时预览 -->
        <el-form-item label="渲染预览">
          <div class="preview-panel">
            <div class="preview-inputs">
              <el-input v-model="previewQuestion" placeholder="预览用 {{question}} 示例" size="small" />
              <el-input
                v-model="previewContext"
                type="textarea"
                :rows="2"
                placeholder="预览用 {{context}} 示例"
                size="small"
              />
            </div>
            <div class="preview-output">
              <div class="preview-head">
                <span>渲染结果</span>
                <el-button
                  v-if="isEdit"
                  size="small"
                  type="primary"
                  plain
                  :loading="renderLoading"
                  @click="handleRenderTest"
                >
                  服务端渲染测试
                </el-button>
              </div>
              <pre class="preview-content">{{ renderedPreview }}</pre>
            </div>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ isEdit ? "保存修改" : "创建模板" }}
          </el-button>
          <el-button @click="handleCancel">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 服务端渲染结果 -->
    <el-dialog v-model="renderDialogVisible" title="服务端渲染结果" width="640px">
      <template v-if="renderResult">
        <p class="render-meta">
          模板: {{ renderResult.template_name }} (ID: {{ renderResult.template_id }})
        </p>
        <pre class="render-result">{{ renderResult.rendered }}</pre>
      </template>
      <template #footer>
        <el-button type="primary" @click="renderDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="less" scoped>
.page-container {
  padding: @spacing-md;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .card-title {
    font-size: 15px;
    font-weight: 600;
    color: @text-primary;
  }
}

.template-form {
  max-width: 900px;
}

.content-editor {
  width: 100%;

  .editor-toolbar {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 8px;

    .toolbar-tip {
      font-size: 13px;
      color: @text-secondary;
      margin-right: 4px;
    }
  }

  .placeholder-alert {
    margin-top: 8px;
  }
}

.variables-editor {
  width: 100%;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;

  .variable-card {
    flex: 1;
    min-width: 260px;
    border: 1px solid @border-light;
    border-radius: @radius-small;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;

    .variable-head {
      display: flex;
      align-items: center;
      gap: 8px;

      .variable-label {
        flex: 1;
        font-size: 13px;
        color: @text-regular;
      }
    }
  }
}

.preview-panel {
  width: 100%;
  display: flex;
  gap: 12px;

  .preview-inputs {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .preview-output {
    flex: 1;
    border: 1px solid @border-light;
    border-radius: @radius-small;
    padding: 12px;
    background: @bg-page;

    .preview-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      font-size: 13px;
      color: @text-secondary;
    }

    .preview-content {
      margin: 0;
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-all;
      color: @text-regular;
      max-height: 300px;
      overflow-y: auto;
    }
  }
}

.render-meta {
  font-size: 13px;
  color: @text-secondary;
  margin-bottom: 8px;
}

.render-result {
  background: @bg-page;
  border: 1px solid @border-light;
  border-radius: @radius-small;
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
  margin: 0;
}
</style>
