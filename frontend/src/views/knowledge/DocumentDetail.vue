<script setup lang="ts">
/**
 * 文档详情
 * 元数据 / 向量化状态 (处理中自动轮询) / 分块查看 / 下载 / 重试 / 删除
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  getDocumentDetailApi,
  getDocumentChunksApi,
  getDocumentDownloadApi,
  deleteDocumentApi,
  vectorizeDocumentApi,
} from "@/api/document";
import { formatFileSize, formatDate } from "@/utils/format";
import { vectorStatusMeta } from "@/utils/constants";
import { confirmDanger } from "@/utils/feedback";
import type { DocumentChunkInfo, DocumentInfo } from "@/types/knowledge";

const route = useRoute();
const router = useRouter();

// computed 而非 setup 期取值: 同路由记录下 1 → 2 复用组件实例时能跟随变化
const documentId = computed(() => Number(route.params.id));

// ==========================================
// 状态
// ==========================================

const doc = ref<DocumentInfo | null>(null);
const loading = ref(false);
const chunks = ref<DocumentChunkInfo[]>([]);
const chunksTotal = ref(0);
const chunksPage = ref(1);
const chunksPageSize = ref(10);
const chunksLoading = ref(false);

let pollTimer: number | null = null;

// ==========================================
// 展示辅助 (状态元数据统一在 utils/constants.ts, Phase 8 去重)
// ==========================================

/** 状态标签元数据 (异常值兜底, 防止查表 undefined 导致整表渲染崩溃) */
function statusMeta(status: string) {
  return vectorStatusMeta(status);
}

// ==========================================
// 数据加载
// ==========================================

async function loadDetail() {
  loading.value = true;
  try {
    const res = await getDocumentDetailApi(documentId.value);
    doc.value = res.data;
    // 状态变化时重新调度轮询
    syncPolling();
    // 向量化完成后刷新分块列表
    if (doc.value?.vector_status === "completed") {
      loadChunks();
    }
  } finally {
    loading.value = false;
  }
}

async function loadChunks() {
  chunksLoading.value = true;
  try {
    const res = await getDocumentChunksApi(documentId.value, {
      page: chunksPage.value,
      page_size: chunksPageSize.value,
    });
    chunks.value = res.data?.items || [];
    chunksTotal.value = res.data?.total || 0;
  } finally {
    chunksLoading.value = false;
  }
}

/** 处理中 / 待处理时每 3s 轮询详情, 否则停止 */
function syncPolling() {
  stopPolling();
  const status = doc.value?.vector_status;
  if (status === "pending" || status === "processing") {
    pollTimer = window.setInterval(loadDetail, 3000);
  }
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

async function handleDownload() {
  if (!doc.value) return;
  const res = await getDocumentDownloadApi(doc.value.id);
  if (res.data?.download_url) {
    window.open(res.data.download_url, "_blank");
  }
}

async function handleVectorize() {
  if (!doc.value) return;
  if (
    doc.value.vector_status === "pending" ||
    doc.value.vector_status === "processing"
  ) {
    ElMessage.warning("文档正在向量化处理中，请稍后");
    return;
  }
  await vectorizeDocumentApi(doc.value.id);
  ElMessage.success("向量化任务已下发");
  await loadDetail();
}

async function handleDelete() {
  if (!doc.value) return;
  const confirmed = await confirmDanger(`确定删除文档 '${doc.value.title}' 吗？`);
  if (!confirmed) return;
  await deleteDocumentApi(doc.value.id);
  ElMessage.success("文档已删除");
  router.push("/knowledge/documents");
}

// 路由参数变化 (详情 → 详情) 时重新加载
watch(
  () => route.params.id,
  () => {
    stopPolling();
    doc.value = null;
    chunks.value = [];
    chunksTotal.value = 0;
    chunksPage.value = 1;
    loadDetail();
  }
);

onMounted(loadDetail);
onUnmounted(stopPolling);
</script>

<template>
  <!-- loading 遮罩仅在首次加载时显示, 轮询刷新不遮整页 -->
  <div class="page-container" v-loading="loading && !doc">
    <template v-if="doc">
      <!-- 操作栏 -->
      <div class="action-bar">
        <el-page-header @back="router.push('/knowledge/documents')">
          <template #content>
            <span class="page-title">{{ doc.title }}</span>
          </template>
        </el-page-header>
        <div class="actions">
          <el-button @click="handleDownload">
            <el-icon><Download /></el-icon>下载
          </el-button>
          <el-button
            type="warning"
            :disabled="doc.vector_status === 'pending' || doc.vector_status === 'processing'"
            @click="handleVectorize"
          >
            <el-icon><Refresh /></el-icon>
            {{ doc.vector_status === "failed" ? "重新向量化" : "重建向量" }}
          </el-button>
          <el-button type="danger" @click="handleDelete">
            <el-icon><Delete /></el-icon>删除
          </el-button>
        </div>
      </div>

      <!-- 元数据 -->
      <el-card shadow="never" class="section">
        <template #header>
          <span class="card-title">基本信息</span>
        </template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="文档ID">{{ doc.id }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ doc.title }}</el-descriptions-item>
          <el-descriptions-item label="所属分类">{{ doc.category_name || doc.category_id }}</el-descriptions-item>
          <el-descriptions-item label="文件名">{{ doc.file_name }}</el-descriptions-item>
          <el-descriptions-item label="文件类型">{{ doc.file_type.toUpperCase() }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatFileSize(doc.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="向量化状态">
            <el-tag :type="statusMeta(doc.vector_status).type" size="small">
              {{ statusMeta(doc.vector_status).label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="分块数量">{{ doc.chunk_count }}</el-descriptions-item>
          <el-descriptions-item label="向量化完成时间">{{ formatDate(doc.vectorized_at) }}</el-descriptions-item>
          <el-descriptions-item label="SHA256" :span="3">
            <span class="hash-text">{{ doc.file_hash }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="标签">{{ doc.tags || "-" }}</el-descriptions-item>
          <el-descriptions-item label="上传人">{{ doc.uploader_name || doc.uploaded_by || "-" }}</el-descriptions-item>
          <el-descriptions-item label="上传时间">{{ formatDate(doc.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="浏览次数">{{ doc.view_count }}</el-descriptions-item>
          <el-descriptions-item label="下载次数">{{ doc.download_count }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="3">{{ doc.description || "-" }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="doc.vector_status === 'failed'"
          type="error"
          :closable="false"
          class="error-alert"
          title="向量化失败"
          :description="doc.error_message || '未知错误'"
          show-icon
        />
      </el-card>

      <!-- 分块列表 -->
      <el-card shadow="never" class="section">
        <template #header>
          <div class="card-header">
            <span class="card-title">分块记录 (共 {{ chunksTotal }} 块)</span>
            <el-button size="small" @click="loadChunks">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
          </div>
        </template>

        <el-table :data="chunks" v-loading="chunksLoading">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="chunk-full-text">{{ row.chunk_text }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="chunk_index" label="序号" width="70" align="center" />
          <el-table-column label="分块文本" min-width="320">
            <template #default="{ row }">
              <span class="chunk-preview">{{ row.chunk_text }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="token_count" label="Token" width="80" align="center" />
          <el-table-column prop="chunk_hash" label="分块哈希" width="130">
            <template #default="{ row }">
              <span class="hash-text">{{ row.chunk_hash ? row.chunk_hash.slice(0, 12) + "..." : "-" }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="chroma_chunk_id" label="Chroma ID" width="170">
            <template #default="{ row }">{{ row.chroma_chunk_id || "-" }}</template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="chunksPage"
            v-model:page-size="chunksPageSize"
            :total="chunksTotal"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="loadChunks"
            @size-change="loadChunks"
          />
        </div>
      </el-card>
    </template>
  </div>
</template>

<style lang="less" scoped>
.page-container {
  padding: @spacing-md;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: @spacing-md;

  .page-title {
    font-size: 16px;
    font-weight: 600;
    color: @text-primary;
  }
}

.section {
  margin-bottom: @spacing-md;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: @text-primary;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.hash-text {
  font-family: "Courier New", Consolas, monospace;
  font-size: 12px;
  color: @text-secondary;
  word-break: break-all;
}

.error-alert {
  margin-top: @spacing-md;
}

.chunk-preview {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 13px;
  color: @text-regular;
}

.chunk-full-text {
  padding: @spacing-sm @spacing-md;
  font-size: 13px;
  line-height: 1.8;
  color: @text-regular;
  white-space: pre-wrap;
  word-break: break-all;
  background-color: @bg-page;
  border-radius: @radius-small;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: @spacing-md;
}
</style>
