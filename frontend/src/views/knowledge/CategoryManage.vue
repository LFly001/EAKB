<script setup lang="ts">
/**
 * 知识库分类管理
 * 树形展示 / 新增 / 编辑 / 删除 / 拖拽排序 (变更父级与同级顺序)
 */
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type ElTree } from "element-plus";
import {
  getCategoryTreeApi,
  createCategoryApi,
  updateCategoryApi,
  moveCategoryApi,
  deleteCategoryApi,
} from "@/api/category";
import type { CategoryNode } from "@/types/knowledge";

// el-tree 节点类型 (避免深路径类型导入, 版本兼容)
type TreeNode = any;

// ==========================================
// 状态
// ==========================================

const loading = ref(false);
const treeData = ref<CategoryNode[]>([]);
const treeRef = ref<InstanceType<typeof ElTree>>();

/** 弹窗状态 */
const dialogVisible = ref(false);
const dialogMode = ref<"create" | "edit">("create");
const editingId = ref<number | null>(null);
const submitting = ref(false);

const form = reactive({
  name: "",
  parent_id: null as number | null,
  description: "",
  icon: "",
  sort_order: 0,
});

// ==========================================
// 数据加载
// ==========================================

async function loadTree() {
  loading.value = true;
  try {
    const res = await getCategoryTreeApi();
    treeData.value = res.data || [];
  } finally {
    loading.value = false;
  }
}

// ==========================================
// 新增 / 编辑
// ==========================================

function openCreateDialog(parentId: number | null = null) {
  dialogMode.value = "create";
  editingId.value = null;
  form.name = "";
  form.parent_id = parentId;
  form.description = "";
  form.icon = "";
  form.sort_order = 0;
  dialogVisible.value = true;
}

function openEditDialog(node: CategoryNode) {
  dialogMode.value = "edit";
  editingId.value = node.id;
  form.name = node.name;
  form.parent_id = node.parent_id;
  form.description = node.description || "";
  form.icon = node.icon || "";
  form.sort_order = node.sort_order;
  dialogVisible.value = true;
}

async function submitForm() {
  if (!form.name.trim()) {
    ElMessage.warning("请输入分类名称");
    return;
  }

  submitting.value = true;
  try {
    if (dialogMode.value === "create") {
      await createCategoryApi({
        name: form.name.trim(),
        parent_id: form.parent_id,
        description: form.description || undefined,
        icon: form.icon || undefined,
        sort_order: form.sort_order,
      });
      ElMessage.success("分类创建成功");
    } else if (editingId.value !== null) {
      await updateCategoryApi(editingId.value, {
        name: form.name.trim(),
        parent_id: form.parent_id,
        description: form.description || undefined,
        icon: form.icon || undefined,
        sort_order: form.sort_order,
      });
      ElMessage.success("分类更新成功");
    }
    dialogVisible.value = false;
    await loadTree();
  } finally {
    submitting.value = false;
  }
}

// ==========================================
// 删除
// ==========================================

async function handleDelete(node: CategoryNode) {
  const hasChildren = (node.children || []).length > 0;
  const tip = hasChildren
    ? `分类 '${node.name}' 下存在 ${node.children.length} 个子分类，无法删除。`
    : node.document_count > 0
      ? `分类 '${node.name}' 下存在 ${node.document_count} 篇文档，无法删除。`
      : null;

  if (tip) {
    ElMessage.warning(tip);
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定删除分类 '${node.name}' 吗？`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }

  await deleteCategoryApi(node.id);
  ElMessage.success(`分类 '${node.name}' 已删除`);
  await loadTree();
}

// ==========================================
// 拖拽排序
// ==========================================

/**
 * 拖拽结束回调:
 * - inner   → 移入 dropNode 内部, 新父级 = dropNode
 * - before/after → 与 dropNode 同级, 新父级 = dropNode 的父级
 * 新的 sort_order = 拖动节点在新父级 children 中的下标 (el-tree 已就地重排)
 */
async function handleNodeDrop(
  draggingNode: TreeNode,
  dropNode: TreeNode,
  dropType: "before" | "after" | "inner"
) {
  const draggingId = Number(draggingNode.data.id);

  let parentId: number | null;
  let siblings: CategoryNode[];

  if (dropType === "inner") {
    parentId = Number(dropNode.data.id);
    siblings = dropNode.data.children || [];
  } else {
    parentId = dropNode.data.parent_id ?? null;
    // 从树数据中定位新父级节点
    const parentData = findNodeById(treeData.value, parentId);
    siblings = parentData ? parentData.children || [] : treeData.value;
  }

  const sortOrder = siblings.findIndex(
    (item) => Number(item.id) === draggingId
  );

  try {
    await moveCategoryApi(draggingId, {
      parent_id: parentId,
      sort_order: Math.max(0, sortOrder),
    });
    ElMessage.success("分类排序已更新");
  } catch {
    // 后端校验失败 (如移动到自己的子分类下) → 回滚树
    ElMessage.error("移动失败，请检查目标位置是否合法");
  }
  await loadTree();
}

/** 按 ID 在树中查找节点 (含子级递归) */
function findNodeById(
  nodes: CategoryNode[],
  id: number | null
): CategoryNode | null {
  if (id === null) return null;
  for (const node of nodes) {
    if (Number(node.id) === id) return node;
    const found = findNodeById(node.children || [], id);
    if (found) return found;
  }
  return null;
}

/** 拖拽合法性: 禁止把节点拖到自己的子孙节点下 (inner 模式) */
function allowDrop(
  draggingNode: TreeNode,
  dropNode: TreeNode,
  type: "prev" | "inner" | "next"
) {
  if (type !== "inner") return true;
  // 向上回溯 dropNode 的祖先链, 若包含拖动节点则禁止
  let cursor: TreeNode | null = dropNode;
  while (cursor) {
    if (cursor.data.id === draggingNode.data.id) return false;
    cursor = cursor.parent;
  }
  return true;
}

onMounted(loadTree);
</script>

<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">知识库分类管理</span>
          <div class="header-actions">
            <el-button @click="loadTree" :loading="loading">刷新</el-button>
            <el-button type="primary" @click="openCreateDialog(null)">
              <el-icon><Plus /></el-icon>新增一级分类
            </el-button>
          </div>
        </div>
      </template>

      <el-tree
        ref="treeRef"
        :data="treeData"
        node-key="id"
        default-expand-all
        draggable
        :allow-drop="allowDrop"
        :expand-on-click-node="false"
        @node-drop="handleNodeDrop"
        v-loading="loading"
      >
        <template #default="{ data }">
          <div class="tree-node">
            <span class="node-icon">
              <el-icon><Folder /></el-icon>
            </span>
            <span class="node-name">{{ data.name }}</span>
            <el-tag v-if="data.document_count > 0" size="small" type="info" effect="plain">
              {{ data.document_count }} 篇
            </el-tag>
            <span class="node-actions">
              <el-button
                link
                type="primary"
                size="small"
                title="新增子分类"
                @click.stop="openCreateDialog(data.id)"
              >
                <el-icon><Plus /></el-icon>
              </el-button>
              <el-button
                link
                type="primary"
                size="small"
                title="编辑"
                @click.stop="openEditDialog(data)"
              >
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button
                link
                type="danger"
                size="small"
                title="删除"
                @click.stop="handleDelete(data)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </span>
          </div>
        </template>
      </el-tree>

      <el-empty
        v-if="!loading && treeData.length === 0"
        description="暂无分类，点击右上角按钮创建"
      />
    </el-card>

    <!-- 新增 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增分类' : '编辑分类'"
      width="480px"
      destroy-on-close
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="分类名称" required>
          <el-input v-model="form.name" placeholder="请输入分类名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="上级分类">
          <el-tree-select
            v-model="form.parent_id"
            :data="treeData"
            :props="({ label: 'name', children: 'children', value: 'id' } as any)"
            node-key="id"
            check-strictly
            clearable
            placeholder="不选则为一级分类"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="Element Plus 图标名 (可选)" />
        </el-form-item>
        <el-form-item label="排序值">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="分类描述 (可选)"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">
          确定
        </el-button>
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

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 8px;

  .node-icon {
    color: @warning-color;
    display: inline-flex;
  }

  .node-name {
    font-size: 14px;
    color: @text-primary;
  }

  .node-actions {
    margin-left: auto;
    display: none;
  }

  &:hover .node-actions {
    display: inline-flex;
  }
}
</style>
