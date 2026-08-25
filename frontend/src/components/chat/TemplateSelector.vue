<script setup lang="ts">
/**
 * 模板下拉选择组件 (供 Phase 5 问答页使用)
 *
 * - 加载启用状态模板, 按 系统预置 / 自定义 分组展示
 * - 传入 categoryId 时, 绑定该分类的模板优先排序并标注「适用当前分类」
 * - v-model 绑定 template_id, change 事件回传完整模板对象
 *
 * 用法:
 *   <TemplateSelector v-model="selectedTemplateId" :category-id="currentCategoryId" @change="onTemplateChange" />
 */
import { computed, onMounted, ref } from "vue";
import { getTemplateListApi } from "@/api/template";
import type { TemplateListItem } from "@/types/template";

// ==========================================
// Props / Emits
// ==========================================

const props = withDefaults(
  defineProps<{
    modelValue?: number | null;
    categoryId?: number | null;
    disabled?: boolean;
    placeholder?: string;
    clearable?: boolean;
  }>(),
  {
    modelValue: null,
    categoryId: null,
    disabled: false,
    placeholder: "选择提示词模板",
    clearable: true,
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: number | null): void;
  (e: "change", template: TemplateListItem | null): void;
}>();

// ==========================================
// 状态
// ==========================================

const loading = ref(false);
const templates = ref<TemplateListItem[]>([]);

// ==========================================
// 选项分组
// ==========================================

interface TemplateOption {
  label: string;
  value: number;
  disabled?: boolean;
  tag?: string; // 「适用当前分类」标注
}

const systemOptions = computed<TemplateOption[]>(() =>
  buildOptions(templates.value.filter((t) => t.is_system === 1))
);

const customOptions = computed<TemplateOption[]>(() =>
  buildOptions(templates.value.filter((t) => t.is_system !== 1))
);

function buildOptions(list: TemplateListItem[]): TemplateOption[] {
  return list
    .slice()
    .sort(compareRelevance)
    .map((t) => ({
      label: t.name,
      value: t.id,
      tag: isBoundToCategory(t) ? "适用当前分类" : undefined,
    }));
}

/** 绑定当前分类的模板优先 (未传 categoryId 时保持原顺序) */
function compareRelevance(a: TemplateListItem, b: TemplateListItem): number {
  if (props.categoryId == null) return 0;
  const aHit = isBoundToCategory(a) ? 1 : 0;
  const bHit = isBoundToCategory(b) ? 1 : 0;
  return bHit - aHit;
}

function isBoundToCategory(t: TemplateListItem): boolean {
  return (
    props.categoryId != null &&
    (t.category_id === props.categoryId || t.category_ids.includes(props.categoryId))
  );
}

// ==========================================
// 数据加载
// ==========================================

async function loadTemplates() {
  loading.value = true;
  try {
    // 仅启用状态模板 (分页拉到上限, 模板数量级小)
    const res = await getTemplateListApi({ page: 1, page_size: 100, status: 1 });
    templates.value = res.data?.items || [];
  } finally {
    loading.value = false;
  }
}

function handleChange(value: number | null) {
  emit("update:modelValue", value);
  const selected = templates.value.find((t) => t.id === value) ?? null;
  emit("change", selected);
}

// 注: categoryId 变化时 systemOptions/customOptions 为 computed 自动重算, 无需额外 watch

onMounted(loadTemplates);
</script>

<template>
  <el-select
    :model-value="modelValue"
    :disabled="disabled"
    :placeholder="placeholder"
    :clearable="clearable"
    :loading="loading"
    style="width: 100%"
    @update:model-value="handleChange"
  >
    <el-option-group v-if="systemOptions.length > 0" label="系统预置模板">
      <el-option
        v-for="opt in systemOptions"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      >
        <span class="option-label">{{ opt.label }}</span>
        <el-tag v-if="opt.tag" size="small" type="success" effect="plain">
          {{ opt.tag }}
        </el-tag>
      </el-option>
    </el-option-group>
    <el-option-group v-if="customOptions.length > 0" label="自定义模板">
      <el-option
        v-for="opt in customOptions"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      >
        <span class="option-label">{{ opt.label }}</span>
        <el-tag v-if="opt.tag" size="small" type="success" effect="plain">
          {{ opt.tag }}
        </el-tag>
      </el-option>
    </el-option-group>
    <template #empty>
      <div class="select-empty">
        暂无可用的启用模板，请先在
        <router-link to="/templates" class="empty-link">提示词模板</router-link>
        页面创建
      </div>
    </template>
  </el-select>
</template>

<style lang="less" scoped>
.option-label {
  margin-right: 8px;
}

.select-empty {
  padding: 8px;
  font-size: 13px;
  color: @text-secondary;

  .empty-link {
    color: @primary-color;
  }
}
</style>
