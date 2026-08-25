<script setup lang="ts">
/**
 * 对话输入区 — 问题输入 + 模板选择 + 分类筛选 + 发送/停止/重试
 *
 * - Enter 发送, Shift+Enter 换行 (兼容中文输入法组合态)
 * - 流式生成中显示「停止」按钮 (中止请求)
 * - 流式失败后显示错误条 + 重试按钮 (断线不自动重发, 手动重试)
 */
import { computed, ref } from "vue";
import TemplateSelector from "@/components/chat/TemplateSelector.vue";
import CategoryFilter from "@/components/chat/CategoryFilter.vue";
import { useChatStore } from "@/stores/chat";

const emit = defineEmits<{
  (e: "send", question: string): void;
  (e: "stop"): void;
  (e: "retry"): void;
}>();

const chatStore = useChatStore();

const question = ref("");

const canSend = computed(
  () => !chatStore.streaming && question.value.trim().length > 0
);

/** 流失败后展示的错误 (断线/生成失败, 提示手动重试) */
const streamError = computed(() => {
  if (chatStore.streaming) return null;
  return chatStore.streamingMessage?.error || null;
});

function handleSend() {
  const text = question.value.trim();
  if (!text || chatStore.streaming) return;
  emit("send", text);
  question.value = "";
}

/** Enter 发送 (Shift+Enter 换行; 中文输入法组合中不触发)
 *  el-input 的 keydown 事件类型为 Event | KeyboardEvent, 内部收窄为 KeyboardEvent */
function handleKeydown(e: Event | KeyboardEvent) {
  const evt = e as KeyboardEvent;
  if (
    evt.key !== "Enter" ||
    evt.shiftKey ||
    (evt as KeyboardEvent & { isComposing?: boolean }).isComposing
  ) {
    return;
  }
  evt.preventDefault();
  handleSend();
}

function handleRetry() {
  emit("retry");
}
</script>

<template>
  <div class="chat-input">
    <!-- 流失败提示条 -->
    <div v-if="streamError" class="input-error-bar">
      <el-icon><WarningFilled /></el-icon>
      <span class="error-text">{{ streamError }}</span>
      <el-button size="small" type="primary" link @click="handleRetry">
        重试
      </el-button>
    </div>

    <!-- 选项行: 模板 + 分类筛选 -->
    <div class="input-options">
      <TemplateSelector
        v-model="chatStore.draftTemplateId"
        :category-id="chatStore.draftCategoryIds[0] ?? null"
        :disabled="chatStore.streaming"
        class="template-select"
      />
      <CategoryFilter
        v-model="chatStore.draftCategoryIds"
        :disabled="chatStore.streaming"
      />
    </div>

    <!-- 输入行 -->
    <div class="input-row">
      <el-input
        v-model="question"
        type="textarea"
        :rows="2"
        maxlength="4000"
        resize="none"
        placeholder="请输入您的问题，Enter 发送，Shift+Enter 换行"
        class="question-input"
        @keydown="handleKeydown"
      />

      <el-button
        v-if="!chatStore.streaming"
        type="primary"
        class="send-btn"
        :disabled="!canSend"
        @click="handleSend"
      >
        <el-icon><Promotion /></el-icon>
        发送
      </el-button>
      <el-button v-else type="danger" class="send-btn" @click="emit('stop')">
        <el-icon><VideoPause /></el-icon>
        停止
      </el-button>
    </div>
  </div>
</template>

<style lang="less" scoped>
.chat-input {
  flex-shrink: 0;
  padding: 12px 24px 16px;
  background: @bg-white;
  border-top: 1px solid @border-light;

  .input-error-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    max-width: 860px;
    margin: 0 auto 8px;
    padding: 6px 12px;
    border-radius: @radius-small;
    background: #fef0f0;
    color: @danger-color;
    font-size: 13px;

    .error-text {
      flex: 1;
    }
  }

  .input-options {
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 860px;
    margin: 0 auto 8px;

    .template-select {
      width: 260px;
    }
  }

  .input-row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    max-width: 860px;
    margin: 0 auto;

    .question-input {
      flex: 1;

      :deep(.el-textarea__inner) {
        border-radius: @radius-normal;
        line-height: 1.6;
      }
    }

    .send-btn {
      height: 40px;
      padding: 0 20px;
    }
  }
}
</style>
