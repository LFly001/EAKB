<script setup lang="ts">
/**
 * 知识库分类筛选组件 (Phase 5 问答输入区)
 *
 * - 加载分类树, 弹窗内多选 (父子独立勾选, 精确匹配)
 * - v-model 绑定选中的分类 ID 列表, 传给 chat-stream 的 category_ids
 *   空列表 = 不限范围 (检索全库)
 */
import { onMounted, ref, watch } from "vue";
import { getCategoryTreeApi } from "@/api/category";
import type { CategoryNode } from "@/types/knowledge";

// ==========================================
// Props / Emits
// ==========================================

const props = defineProps<{
  modelValue: number[];
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: number[]): void;
}>();

// ==========================================
// 状态
// ==========================================

/** el-tree 实例 (仅声明使用到的方法, 全局组件注册场景下避免值导入) */
interface TreeInstance {
  getCheckedKeys: () => Array<string | number>;
  setCheckedKeys: (keys: Array<string | number>, leafOnly?: boolean) => void;
}

const treeRef = ref<TreeInstance | null>(null);
const popoverVisible = ref(false);
const loading = ref(false);
const treeData = ref<CategoryNode[]>([]);
const selectedNames = ref<string[]>([]);

// ==========================================
// 数据加载
// ==========================================

async function loadTree() {
  loading.value = true;
  try {
    const res = await getCategoryTreeApi();
    treeData.value = res.data || [];
    syncNames();
  } finally {
    loading.value = false;
  }
}

/** 选中 ID → 名称 (用于输入框标签展示) */
function syncNames() {
  const idSet = new Set(props.modelValue);
  const names: string[] = [];
  const walk = (nodes: CategoryNode[]) => {
    for (const node of nodes) {
      if (idSet.has(node.id)) names.push(node.name);
      walk(node.children || []);
    }
  };
  walk(treeData.value);
  selectedNames.value = names;
}

// ==========================================
// 勾选处理 (父子独立, 精确匹配)
// ==========================================

function handleCheck() {
  const keys = treeRef.value?.getCheckedKeys() ?? [];
  const ids = keys.filter((k): k is number => typeof k === "number");
  emit("update:modelValue", ids);
}

watch(
  () => props.modelValue,
  () => {
    syncNames();
    treeRef.value?.setCheckedKeys(props.modelValue, false);
  }
);

onMounted(loadTree);
</script>

<template>
  <el-popover
    v-model:visible="popoverVisible"
    placement="top-start"
    :width="260"
    trigger="click"
  >
    <!-- 注意: #reference 内不能再套 el-tooltip 等组件, 否则 popover 的
         click 触发指令挂不上 (Element Plus 警告: Runtime directive used
         on component with non-element root node), 表现为点击无反应 -->
    <template #reference>
      <div
        class="category-filter"
        :class="{ 'has-value': selectedNames.length > 0, 'is-disabled': disabled }"
        :title="
          selectedNames.length
            ? selectedNames.join('、')
            : '限定问答检索的知识库分类范围（精确匹配，不勾选则检索全库）'
        "
      >
        <el-icon><Folder /></el-icon>
        <template v-if="selectedNames.length > 0">
          <span class="filter-text">{{ selectedNames.slice(0, 2).join("、") }}</span>
          <span v-if="selectedNames.length > 2" class="filter-more">
            +{{ selectedNames.length - 2 }}
          </span>
        </template>
        <span v-else class="filter-text placeholder">分类筛选</span>
        <el-icon v-if="selectedNames.length > 0" class="clear-icon" @click.stop="emit('update:modelValue', [])">
          <CircleCloseFilled />
        </el-icon>
      </div>
    </template>

    <div v-loading="loading" class="category-pop">
      <div v-if="treeData.length === 0 && !loading" class="category-empty">
        暂无分类，请先在
        <router-link to="/knowledge/categories">分类管理</router-link>
        创建
      </div>
      <el-tree
        v-else
        ref="treeRef"
        :data="treeData"
        node-key="id"
        show-checkbox
        check-strictly
        default-expand-all
        :props="{ label: 'name', children: 'children' }"
        @check="handleCheck"
      />
      <div class="category-tip">勾选后仅在被选分类的文档中检索</div>
    </div>
  </el-popover>
</template>

<style lang="less" scoped>
.category-filter {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid @border-color;
  border-radius: @radius-small;
  background: @bg-white;
  cursor: pointer;
  color: @text-secondary;
  transition: border-color 0.2s;

  &:hover {
    border-color: @primary-color;
  }

  &.has-value {
    border-color: @primary-light;
    color: @primary-color;
    background: @bg-active;
  }

  &.is-disabled {
    pointer-events: none;
    opacity: 0.6;
  }

  .filter-text {
    font-size: 12px;
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &.placeholder {
      color: @text-secondary;
    }
  }

  .filter-more {
    font-size: 12px;
  }

  .clear-icon {
    font-size: 14px;
    color: @text-placeholder;

    &:hover {
      color: @danger-color;
    }
  }
}

.category-pop {
  max-height: 320px;
  overflow-y: auto;

  .category-empty {
    font-size: 13px;
    color: @text-secondary;
    padding: 8px 0;

    a {
      color: @primary-color;
    }
  }

  .category-tip {
    margin-top: 6px;
    font-size: 12px;
    color: @text-placeholder;
  }
}
</style>
