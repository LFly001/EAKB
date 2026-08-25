<script setup lang="ts">
/**
 * 操作日志页 — 管理员 (Phase 7)
 * 分页 + 多条件筛选 (模块/用户/操作类型/结果/时间范围), 详情抽屉
 * 审计要求: 仅查询, 不提供删除
 */
import { ref, onMounted } from "vue";
import { getLogListApi } from "@/api/admin";
import type { OperationLogInfo } from "@/types/admin";

// ==========================================
// 模块选项 (与后端埋点 module 取值对齐)
// ==========================================
const MODULE_OPTIONS = [
  { label: "认证", value: "auth" },
  { label: "用户管理", value: "user" },
  { label: "知识库", value: "knowledge" },
  { label: "提示词模板", value: "template" },
  { label: "RAG 问答", value: "rag" },
  { label: "知识图谱", value: "graph" },
  { label: "系统配置", value: "system" },
];

const MODULE_LABELS: Record<string, string> = Object.fromEntries(
  MODULE_OPTIONS.map((m) => [m.value, m.label])
);

// ==========================================
// 查询条件
// ==========================================
const loading = ref(false);
const logs = ref<OperationLogInfo[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);

const filterModule = ref("");
const filterUsername = ref("");
const filterStatus = ref("");
const timeRange = ref<[Date, Date] | null>(null);

// ==========================================
// 详情抽屉
// ==========================================
const drawerVisible = ref(false);
const currentLog = ref<OperationLogInfo | null>(null);

function openDetail(log: OperationLogInfo) {
  currentLog.value = log;
  drawerVisible.value = true;
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").slice(0, 19);
}

/**
 * Date → 本地时间字符串 (无时区后缀)
 * 后端 MySQL DATETIME 存本地 naive 时间, 传 UTC ISO 会偏移 8 小时
 */
function toLocalTimeString(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

// ==========================================
// 数据请求
// ==========================================
async function fetchLogs() {
  loading.value = true;
  try {
    const res = await getLogListApi({
      page: page.value,
      page_size: pageSize.value,
      module: filterModule.value || undefined,
      username: filterUsername.value || undefined,
      status: filterStatus.value || undefined,
      start_time: timeRange.value?.[0] ? toLocalTimeString(timeRange.value[0]) : undefined,
      end_time: timeRange.value?.[1] ? toLocalTimeString(timeRange.value[1]) : undefined,
    });
    if (res.code === 200) {
      logs.value = res.data.items;
      total.value = res.data.total;
    }
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  fetchLogs();
}

function handleReset() {
  filterModule.value = "";
  filterUsername.value = "";
  filterStatus.value = "";
  timeRange.value = null;
  page.value = 1;
  fetchLogs();
}

onMounted(() => {
  fetchLogs();
});
</script>

<template>
  <div class="page-container">
    <h2 style="margin-bottom: 16px">操作日志</h2>

    <!-- 筛选栏 -->
    <div class="page-toolbar">
      <el-select
        v-model="filterModule"
        placeholder="模块"
        clearable
        style="width: 140px"
        @change="handleSearch"
      >
        <el-option
          v-for="m in MODULE_OPTIONS"
          :key="m.value"
          :label="m.label"
          :value="m.value"
        />
      </el-select>
      <el-input
        v-model="filterUsername"
        placeholder="操作人用户名"
        clearable
        style="width: 160px"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      />
      <el-select
        v-model="filterStatus"
        placeholder="执行结果"
        clearable
        style="width: 120px"
        @change="handleSearch"
      >
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-date-picker
        v-model="timeRange"
        type="datetimerange"
        start-placeholder="操作时间起"
        end-placeholder="操作时间止"
        style="width: 360px"
        @change="handleSearch"
      />
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <!-- 日志表格 -->
    <el-card>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="操作日志仅用于审计查询，不支持删除"
        style="margin-bottom: 12px"
      />
      <el-table :data="logs" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="操作人" width="120">
          <template #default="{ row }">
            {{ row.username || "—" }}
          </template>
        </el-table-column>
        <el-table-column prop="module" label="模块" width="110">
          <template #default="{ row }">
            <el-tag size="small" type="info">
              {{ MODULE_LABELS[row.module] || row.module || "—" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="操作类型" min-width="150" />
        <el-table-column prop="target_id" label="目标ID" width="110">
          <template #default="{ row }">
            <span class="text-ellipsis" style="max-width: 100px; display: inline-block">
              {{ row.target_id || "—" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === "success" ? "成功" : "失败" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP" width="130">
          <template #default="{ row }">
            {{ row.ip_address || "—" }}
          </template>
        </el-table-column>
        <el-table-column label="操作时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openDetail(row as OperationLogInfo)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div style="margin-top: 16px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @change="fetchLogs"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="操作日志详情" size="480px">
      <template v-if="currentLog">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="日志ID">{{ currentLog.id }}</el-descriptions-item>
          <el-descriptions-item label="操作人">
            {{ currentLog.username || "—" }} (ID: {{ currentLog.user_id ?? "—" }})
          </el-descriptions-item>
          <el-descriptions-item label="模块">
            {{ MODULE_LABELS[currentLog.module || ""] || currentLog.module || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="操作类型">{{ currentLog.action }}</el-descriptions-item>
          <el-descriptions-item label="目标">
            {{ currentLog.target_type || "—" }} / {{ currentLog.target_id || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="结果">
            <el-tag
              :type="currentLog.status === 'success' ? 'success' : 'danger'"
              size="small"
            >
              {{ currentLog.status === "success" ? "成功" : "失败" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="IP">{{ currentLog.ip_address || "—" }}</el-descriptions-item>
          <el-descriptions-item label="UserAgent">
            <div style="word-break: break-all; font-size: 12px">
              {{ currentLog.user_agent || "—" }}
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="操作时间">
            {{ formatTime(currentLog.created_at) }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="currentLog.error_info" style="margin-top: 12px">
          <div class="detail-label">错误信息</div>
          <pre class="detail-pre error">{{ currentLog.error_info }}</pre>
        </div>

        <div style="margin-top: 12px">
          <div class="detail-label">操作详情</div>
          <pre class="detail-pre">{{ JSON.stringify(currentLog.detail ?? {}, null, 2) }}</pre>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.detail-label {
  font-size: 13px;
  font-weight: 600;
  color: @text-primary;
  margin-bottom: 6px;
}

.detail-pre {
  margin: 0;
  padding: 10px 12px;
  background-color: @bg-page;
  border-radius: @radius-small;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;

  &.error {
    color: @danger-color;
  }
}
</style>
