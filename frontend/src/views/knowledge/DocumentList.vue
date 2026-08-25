<script setup lang="ts">
/**
 * 文档分页列表
 * 筛选 / 批量向量化 / 详情 / 下载 / 删除 / 向量化状态自动轮询
 */
import { onMounted, onUnmounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { getCategoryTreeApi } from "@/api/category";
import {
  getDocumentListApi,
  getDocumentDownloadApi,
  deleteDocumentApi,
  vectorizeDocumentApi,
  batchVectorizeApi,
} from "@/api/document";
import { formatFileSize, formatDate } from "@/utils/format";
import { CATEGORY_TREE_PROPS, VECTOR_STATUS_META, vectorStatusMeta } from "@/utils/constants";
import { confirmDanger } from "@/utils/feedback";
import type { CategoryNode, DocumentInfo, VectorStatus } from "@/types/knowledge";

const router = useRouter();

// ==========================================
// 状态
// ==========================================

const loading = ref(false);
const documents = ref<DocumentInfo[]>([]);
const total = ref(0);
const categoryTree = ref<CategoryNode[]>([]);
const selectedRows = ref<DocumentInfo[]>([]);

const query = reactive({
  page: 1,
  page_size: 20,
  keyword: "",
  category_id: null as number | null,
  vector_status: "" as "" | VectorStatus,
  file_type: "",
});

// 自动轮询定时器 (向量化状态变化)
let pollTimer: number | null = null;

// ==========================================
// 数据加载
// ==========================================

async function loadDocuments() {
  loading.value = true;
  try {
    const res = await getDocumentListApi({
      page: query.page,
      page_size: query.page_size,
      keyword: query.keyword || undefined,
      category_id: query.category_id ?? undefined,
      vector_status: query.vector_status || undefined,
      file_type: query.file_type || undefined,
    });
    documents.value = res.data?.items || [];
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
  loadDocuments();
}

function handleReset() {
  query.keyword = "";
  query.category_id = null;
  query.vector_status = "";
  query.file_type = "";
  query.page = 1;
  loadDocuments();
}

// ==========================================
// 向量化状态轮询 (列表存在处理中/待处理文档时每 5s 刷新)
// ==========================================

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(() => {
    const hasActive = documents.value.some(
      (d) => d.vector_status === "pending" || d.vector_status === "processing"
    );
    if (hasActive) {
      loadDocuments();
    }
  }, 5000);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ==========================================
// 操作
// ==========================================

function goDetail(doc: DocumentInfo) {
  router.push(`/knowledge/documents/${doc.id}`);
}

async function handleDownload(doc: DocumentInfo) {
  const res = await getDocumentDownloadApi(doc.id);
  if (res.data?.download_url) {
    window.open(res.data.download_url, "_blank");
  }
}

async function handleVectorize(doc: DocumentInfo) {
  if (doc.vector_status === "pending" || doc.vector_status === "processing") {
    ElMessage.warning("文档正在向量化处理中，请稍后");
    return;
  }
  await vectorizeDocumentApi(doc.id);
  ElMessage.success("向量化任务已下发，请稍后刷新查看进度");
  setTimeout(loadDocuments, 1000);
}

async function handleBatchVectorize() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning("请先勾选文档");
    return;
  }
  const ids = selectedRows.value.map((d) => d.id);
  const res = await batchVectorizeApi(ids);
  const results = res.data || [];
  const triggered = results.filter((r) => r.triggered).length;
  const skipped = results.length - triggered;
  ElMessage.success(`已下发 ${triggered} 个向量化任务${skipped > 0 ? `，跳过 ${skipped} 个` : ""}`);
  setTimeout(loadDocuments, 1000);
}

async function handleDelete(doc: DocumentInfo) {
  const confirmed = await confirmDanger(
    `确定删除文档 '${doc.title}' 吗？删除后向量数据将同步清理。`
  );
  if (!confirmed) return;
  await deleteDocumentApi(doc.id);
  ElMessage.success(`文档 '${doc.title}' 已删除`);
  loadDocuments();
}

function handleSelectionChange(rows: DocumentInfo[]) {
  selectedRows.value = rows;
}

// ==========================================
// 展示辅助 (状态元数据统一在 utils/constants.ts, Phase 8 去重)
// ==========================================

function statusMeta(status: string) {
  return vectorStatusMeta(status);
}

onMounted(() => {
  loadCategories();
  loadDocuments();
  startPolling();
});

onUnmounted(stopPolling);
</script>

<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">文档管理</span>
          <div class="header-actions">
            <el-button @click="loadDocuments" :loading="loading">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
            <el-button type="primary" @click="router.push('/knowledge/documents/upload')">
              <el-icon><Upload /></el-icon>上传文档
            </el-button>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索标题 / 文件名 / 标签"
          clearable
          style="width: 240px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-tree-select
          v-model="query.category_id"
          :data="categoryTree"
          :props="CATEGORY_TREE_PROPS"
          node-key="id"
          check-strictly
          clearable
          placeholder="全部分类"
          style="width: 200px"
          @change="handleSearch"
        />
        <el-select
          v-model="query.vector_status"
          placeholder="向量化状态"
          clearable
          style="width: 140px"
          @change="handleSearch"
        >
          <el-option
            v-for="(meta, status) in VECTOR_STATUS_META"
            :key="status"
            :label="meta.label"
            :value="status"
          />
        </el-select>
        <el-select
          v-model="query.file_type"
          placeholder="文件类型"
          clearable
          style="width: 120px"
          @change="handleSearch"
        >
          <el-option label="PDF" value="pdf" />
          <el-option label="DOCX" value="docx" />
          <el-option label="TXT" value="txt" />
          <el-option label="MD" value="md" />
          <el-option label="XLSX" value="xlsx" />
        </el-select>
        <el-button type="primary" @click="handleSearch">
          <el-icon><Search /></el-icon>查询
        </el-button>
        <el-button @click="handleReset">重置</el-button>
        <el-button
          type="warning"
          :disabled="selectedRows.length === 0"
          @click="handleBatchVectorize"
        >
          批量向量化 ({{ selectedRows.length }})
        </el-button>
      </div>

      <!-- 文档表格 -->
      <el-table
        :data="documents"
        v-loading="loading"
        @selection-change="handleSelectionChange"
        row-key="id"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column label="标题" min-width="180">
          <template #default="{ row }">
            <el-link type="primary" @click="goDetail(row as DocumentInfo)">{{ row.title }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="category_name" label="分类" width="120" />
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.file_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100" align="right">
          <template #default="{ row }">{{ formatFileSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="向量化状态" width="110" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.vector_status === 'failed' && row.error_message"
              :content="row.error_message"
              placement="top"
            >
              <el-tag :type="statusMeta(row.vector_status).type" size="small">
                {{ statusMeta(row.vector_status).label }}
              </el-tag>
            </el-tooltip>
            <el-tag v-else :type="statusMeta(row.vector_status).type" size="small">
              {{ statusMeta(row.vector_status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块数" width="80" align="center" />
        <el-table-column label="上传时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="goDetail(row as DocumentInfo)">详情</el-button>
            <el-button link type="primary" size="small" @click="handleDownload(row as DocumentInfo)">下载</el-button>
            <el-button link type="warning" size="small" @click="handleVectorize(row as DocumentInfo)">
              {{ row.vector_status === "failed" ? "重试" : "向量化" }}
            </el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row as DocumentInfo)">删除</el-button>
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
          @current-change="loadDocuments"
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

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: @spacing-md;
}
</style>
