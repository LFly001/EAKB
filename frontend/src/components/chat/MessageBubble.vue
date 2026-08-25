<script setup lang="ts">
/**
 * 消息气泡组件 (Phase 5 对话页)
 *
 * - 用户消息右侧展示, 助手消息左侧展示 (含头像)
 * - 流式生成中的助手消息显示打字光标; 生成失败显示错误提示
 * - 助手消息底部: 引用来源入口 + Token/耗时统计 + 点赞点踩反馈
 */
import { computed } from "vue";
import { formatDate } from "@/utils/format";
import FeedbackButtons from "./FeedbackButtons.vue";
import type { ChatMessage } from "@/types/chat";

// ==========================================
// Props / Emits
// ==========================================

const props = withDefaults(
  defineProps<{
    message: ChatMessage;
    /** 是否为流式生成中的助手占位消息 */
    streaming?: boolean;
    /** 流式生成中的文本内容 (streaming 时展示) */
    streamingContent?: string;
    /** 流式生成失败原因 (error 事件 / 断线) */
    streamError?: string | null;
  }>(),
  {
    streaming: false,
    streamingContent: "",
    streamError: null,
  }
);

const emit = defineEmits<{
  (e: "view-sources", message: ChatMessage): void;
  (
    e: "feedback",
    payload: { messageId: number; feedback: "positive" | "negative"; comment?: string }
  ): void;
}>();

// ==========================================
// 展示内容
// ==========================================

const isUser = computed(() => props.message.role === "user");

/** 气泡正文 (流式中取增量内容, 否则取落库 answer/question) */
const content = computed(() => {
  if (props.streaming) return props.streamingContent;
  return props.message.role === "user"
    ? props.message.question || ""
    : props.message.answer || "";
});

/** 是否显示失败状态 (流式失败 或 落库 error_message) */
const hasError = computed(
  () => !!props.streamError || !!props.message.error_message
);

const errorText = computed(
  () => props.streamError || props.message.error_message || "生成失败"
);

/** 引用来源数量 */
const sourceCount = computed(() => props.message.sources?.length || 0);

/** 统计摘要: 耗时 + Token */
const metaText = computed(() => {
  const parts: string[] = [];
  if (props.message.response_time_ms != null) {
    parts.push(`${(props.message.response_time_ms / 1000).toFixed(1)}s`);
  }
  const tokens = props.message.token_usage?.total_tokens;
  if (tokens != null) {
    parts.push(`${tokens} tokens`);
  }
  return parts.join(" · ");
});

function handleViewSources() {
  emit("view-sources", props.message);
}

function handleFeedback(payload: {
  feedback: "positive" | "negative";
  comment?: string;
}) {
  emit("feedback", { messageId: props.message.id, ...payload });
}
</script>

<template>
  <div class="message-bubble" :class="isUser ? 'is-user' : 'is-assistant'">
    <!-- 助手头像 -->
    <div v-if="!isUser" class="bubble-avatar">
      <el-icon><MagicStick /></el-icon>
    </div>

    <div class="bubble-body">
      <div class="bubble-meta">
        <span v-if="!isUser" class="bubble-name">智能助手</span>
        <span v-if="message.created_at && message.id > 0" class="bubble-time">
          {{ formatDate(message.created_at, "time") }}
        </span>
      </div>

      <div class="bubble-content" :class="{ 'is-error': hasError }">
        <template v-if="content">{{ content }}</template>
        <template v-else-if="streaming && !hasError">
          <span class="typing-cursor"></span>
        </template>

        <!-- 流式打字光标 -->
        <span v-if="streaming && !hasError" class="typing-cursor"></span>

        <!-- 失败提示 -->
        <div v-if="hasError" class="bubble-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ errorText }}</span>
        </div>
      </div>

      <!-- 助手消息底部操作区 -->
      <div v-if="!isUser && !streaming && message.id > 0" class="bubble-footer">
        <el-button
          v-if="sourceCount > 0"
          text
          size="small"
          class="source-btn"
          @click="handleViewSources"
        >
          <el-icon><Document /></el-icon>
          引用来源 ({{ sourceCount }})
        </el-button>

        <span v-if="metaText" class="bubble-stats">{{ metaText }}</span>

        <FeedbackButtons
          v-if="!hasError"
          :message-id="message.id"
          :feedback="message.feedback"
          @submit="handleFeedback"
        />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.message-bubble {
  display: flex;
  gap: 10px;
  padding: 12px 0;

  &.is-user {
    flex-direction: row-reverse;

    .bubble-body {
      align-items: flex-end;
    }

    .bubble-content {
      background: @primary-color;
      color: #fff;
      border-radius: @radius-normal @radius-normal @radius-small @radius-normal;
      max-width: 620px;
    }

    .bubble-meta {
      flex-direction: row-reverse;
    }
  }

  &.is-assistant {
    .bubble-content {
      background: @bg-white;
      color: @text-primary;
      border: 1px solid @border-light;
      border-radius: @radius-normal @radius-normal @radius-normal @radius-small;
    }
  }
}

.bubble-avatar {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, @primary-color, #7c4dff);
  color: #fff;
  font-size: 18px;
}

.bubble-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  max-width: calc(100% - 46px);
}

.bubble-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;

  .bubble-name {
    font-size: 12px;
    color: @text-secondary;
  }

  .bubble-time {
    font-size: 12px;
    color: @text-placeholder;
  }
}

.bubble-content {
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;

  &.is-error {
    border-color: @danger-color;
  }
}

.bubble-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 6px;
  font-size: 13px;
  color: @danger-color;
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.15em;
  background: @primary-color;
  animation: blink 0.8s infinite;
}

@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}

.bubble-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 4px;
  min-height: 28px;

  .source-btn {
    color: @primary-color;
  }

  .bubble-stats {
    font-size: 12px;
    color: @text-placeholder;
  }
}
</style>
