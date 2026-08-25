<script setup lang="ts">
/**
 * 提示词模板列表
 * 筛选 (关键词/类型/标签/分类) / 分页 / 编辑 / 删除 (系统模板隐藏删除按钮)
 */
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getTemplateListApi,
  deleteTemplateApi,
  updateTemplateApi,
} from "@/api/template";
import { getCategoryTreeApi } from "@/api/category";
import { formatDate } from "@/utils/format";
import type { CategoryNode } from "@/types/knowledge";
import type { TemplateListItem } from "@/types/template";

const router = useRouter();

// ==========================================
// 状态
// ==========================================

const loading = ref(false);
const templates = ref<TemplateListItem[]>([]);
const total = ref(0);
const categoryTree = ref<CategoryNode[]>([]);

const query = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  category_id: null as number | null,
  is_system: null as 0 | 1 | null,
  tag: "",
});

// ==========================================
// 数据加载
// ==========================================

async function loadTemplates() {
  loading.value = true;
  try {
    const res = await getTemplateListApi({
      page: query.page,
      page_size: query.page_size,
      keyword: query.keyword || undefined,
      category_id: query.category_id ?? undefined,
      is_system: query.is_system ?? undefined,
      tag: query.tag || undefined,
    });
    templates.value = res.data?.items || [];
    total.value = res.data?.total || 0;
  } finally {
    loading.value = false;
  }
}

async function loadCategories() {
  const res = await getCategoryTreeApi();
  categoryTree.value = res.data || [];
}

function handleSearch() {
  query.page = 1;
  loadTemplates();
}

function handleReset() {
  query.keyword = "";
  query.category_id = null;
  query.is_system = null;
  query.tag = "";
  query.page = 1;
  loadTemplates();
}

// ==========================================
// 操作
// ==========================================

function goCreate() {
  router.push("/templates/create");
}

function goEdit(row: TemplateListItem) {
  router.push(`/templates/${row.id}/edit`);
}

async function handleDelete(row: TemplateListItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除模板 '${row.name}' 吗？删除后其分类绑定将一并清除。`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  await deleteTemplateApi(row.id);
  ElMessage.success(`模板 '${row.name}' 已删除`);
  loadTemplates();
}

async function handleToggleStatus(row: TemplateListItem) {
  // 状态切换走更新接口 (系统模板同样允许启停)
  await updateTemplateApi(row.id, { status: row.status === 1 ? 0 : 1 });
  ElMessage.success(row.status === 1 ? "模板已禁用" : "模板已启用");
  loadTemplates();
}

onMounted(() => {
  loadCategories();
  loadTemplates();
});
</script>

<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">提示词模板</span>
          <div class="header-actions">
            <el-button @click="loadTemplates" :loading="loading">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
            <el-button type="primary" @click="goCreate">
              <el-icon><Plus /></el-icon>新建模板
            </el-button>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索名称 / 描述 / 标签"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select
          v-model="query.is_system"
          placeholder="全部类型"
          clearable
          style="width: 130px"
          @change="handleSearch"
        >
          <el-option label="系统预置" :value="1" />
          <el-option label="自定义" :value="0" />
        </el-select>
        <el-input
          v-model="query.tag"
          placeholder="标签"
          clearable
          style="width: 130px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-tree-select
          v-model="query.category_id"
          :data="categoryTree"
          :props="({ label: 'name', children: 'children', value: 'id' } as any)"
          node-key="id"
          check-strictly
          clearable
          placeholder="关联分类"
          style="width: 180px"
          @change="handleSearch"
        />
        <el-button type="primary" @click="handleSearch">
          <el-icon><Search /></el-icon>查询
        </el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>

      <!-- 模板表格 -->
      <el-table :data="templates" v-loading="loading" row-key="id">
        <el-table-column label="模板名称" min-width="180">
          <template #default="{ row }">
            <el-link type="primary" @click="goEdit(row as TemplateListItem)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_system === 1" size="small" type="warning" effect="plain">
              系统预置
            </el-tag>
            <el-tag v-else size="small" type="info" effect="plain">自定义</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="120">
          <template #default="{ row }">
            <template v-if="row.tags">
              <el-tag
                v-for="tag in row.tags.split(',').filter(Boolean)"
                :key="tag"
                size="small"
                effect="plain"
                class="tag-item"
              >
                {{ tag }}
              </el-tag>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="关联分类" min-width="160">
          <template #default="{ row }">
            <template v-if="row.category_names.length > 0">
              <el-tooltip :content="row.category_names.join('、')" placement="top">
                <span class="category-names">{{ row.category_names.join('、') }}</span>
              </el-tooltip>
            </template>
            <span v-else class="text-muted">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column label="使用次数" width="90" align="center" sortable prop="usage_count" />
        <el-table-column label="创建人" width="110">
          <template #default="{ row }">
            {{ row.creator_name || "系统" }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.status === 1"
              @change="handleToggleStatus(row as TemplateListItem)"
            />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="goEdit(row as TemplateListItem)">编辑</el-button>
            <!-- 系统预置模板隐藏删除按钮 (接口层同样禁止删除) -->
            <el-button
              v-if="row.is_system !== 1"
              link
              type="danger"
              size="small"
              @click="handleDelete(row as TemplateListItem)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadTemplates"
          @size-change="handleSearch"
        />
      </div>
    </el-card>
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

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: @spacing-md;
}

.tag-item {
  margin-right: 4px;
}

.category-names {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.text-muted {
  color: @text-secondary;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: @spacing-md;
}
</style>
