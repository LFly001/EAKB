<script setup lang="ts">
/**
 * 数据看板 — 管理后台统计页 (Phase 7)
 * 6 个统计卡: 用户 / 文档 / 会话 / 今日问答 / 向量化 / 今日操作
 * 规范: stat tile = label(次要墨色) + value(大号 semibold, 千分位) + 单一品牌色 accent
 */
import { ref, onMounted } from "vue";
import { getDashboardApi } from "@/api/admin";
import type { DashboardStats } from "@/types/admin";

const loading = ref(false);
const stats = ref<DashboardStats | null>(null);
const updatedAt = ref("");

/** 统计卡配置: label + 图标 */
const CARDS: { key: keyof DashboardStats; label: string; icon: string }[] = [
  { key: "user_count", label: "用户总数", icon: "User" },
  { key: "document_count", label: "文档总量", icon: "Document" },
  { key: "conversation_count", label: "问答会话", icon: "ChatDotRound" },
  { key: "today_question_count", label: "今日问答量", icon: "Message" },
  { key: "vectorized_document_count", label: "向量化文档", icon: "MagicStick" },
  { key: "today_operation_count", label: "今日操作", icon: "Monitor" },
];

async function fetchStats() {
  loading.value = true;
  try {
    const res = await getDashboardApi();
    if (res.code === 200) {
      stats.value = res.data;
      updatedAt.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    }
  } finally {
    loading.value = false;
  }
}

function formatValue(value: number): string {
  return value.toLocaleString("zh-CN");
}

onMounted(() => {
  fetchStats();
});
</script>

<template>
  <div class="page-container">
    <div class="flex-between" style="margin-bottom: 16px">
      <h2>数据看板</h2>
      <div style="display: flex; align-items: center; gap: 12px">
        <span v-if="updatedAt" class="updated-at">更新于 {{ updatedAt }}</span>
        <el-button :loading="loading" @click="fetchStats">
          <el-icon><Refresh /></el-icon>
          <span style="margin-left: 4px">刷新</span>
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="stat-grid">
      <el-card
        v-for="card in CARDS"
        :key="card.key"
        class="stat-card"
        shadow="hover"
      >
        <div class="stat-body">
          <div class="stat-icon">
            <el-icon :size="22"><component :is="card.icon" /></el-icon>
          </div>
          <div class="stat-meta">
            <div class="stat-value">
              {{ formatValue(stats?.[card.key] ?? 0) }}
            </div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </div>
      </el-card>
    </div>

    <el-card style="margin-top: 16px" shadow="never">
      <template #header>
        <span class="panel-title">统计口径说明</span>
      </template>
      <ul class="stat-note">
        <li>用户总数：系统全部注册用户（含禁用账号）</li>
        <li>文档总量：未软删的文档（status ≠ -1），含草稿与向量化中</li>
        <li>问答会话：RAG 对话会话总量</li>
        <li>今日问答量：今天内用户发出的提问消息数</li>
        <li>向量化文档：向量化状态为 completed 的未删文档</li>
        <li>今日操作：今天写入的操作日志条数</li>
      </ul>
    </el-card>
  </div>
</template>

<style lang="less" scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  min-height: 120px;
}

.stat-card {
  border-radius: @radius-normal;

  .stat-body {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .stat-icon {
    width: 48px;
    height: 48px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: @radius-normal;
    background-color: @bg-active;
    color: @primary-color;
  }

  .stat-meta {
    min-width: 0;
  }

  .stat-value {
    font-size: 28px;
    font-weight: 600;
    line-height: 1.2;
    color: @text-primary;
  }

  .stat-label {
    margin-top: 4px;
    font-size: 13px;
    color: @text-secondary;
  }
}

.updated-at {
  font-size: 12px;
  color: @text-secondary;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: @text-primary;
}

.stat-note {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: @text-regular;
  line-height: 1.9;
}

// 窄屏降为两列
@media (max-width: 1200px) {
  .stat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
