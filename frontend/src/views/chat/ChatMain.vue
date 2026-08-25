<script setup lang="ts">
/**
 * 对话主区 — 消息气泡列表 + 流式渲染 + 空状态
 * 自动滚动到底部; 来源引用与反馈事件上抛 ChatView 处理。
 */
import { nextTick, ref, watch } from "vue";
import MessageBubble from "@/components/chat/MessageBubble.vue";
import { useChatStore } from "@/stores/chat";
import type { ChatMessage } from "@/types/chat";

const emit = defineEmits<{
  (e: "view-sources", message: ChatMessage): void;
  (
    e: "feedback",
    payload: { messageId: number; feedback: "positive" | "negative"; comment?: string }
  ): void;
}>();

const chatStore = useChatStore();

// ==========================================
// 自动滚动
// ==========================================

const scrollRef = ref<HTMLElement | null>(null);

async function scrollToBottom() {
  await nextTick();
  if (scrollRef.value) {
    scrollRef.value.scrollTop = scrollRef.value.scrollHeight;
  }
}

// 消息数量变化 / 流式内容增长时滚动到底部
watch(
  () => [
    chatStore.messages.length,
    chatStore.streamingMessage?.content,
    chatStore.streamingMessage?.error,
  ],
  scrollToBottom
);

// ==========================================
// 事件转发
// ==========================================

function handleViewSources(message: ChatMessage) {
  emit("view-sources", message);
}

function handleFeedback(payload: {
  messageId: number;
  feedback: "positive" | "negative";
  comment?: string;
}) {
  emit("feedback", payload);
}

/** 流式占位消息构造 (传给 MessageBubble 的伪消息) */
function buildStreamingPlaceholder(): ChatMessage {
  return {
    id: -2,
    conversation_id: chatStore.currentConversationId ?? -1,
    role: "assistant",
    question: null,
    answer: null,
    prompt_full: null,
    retrieved_chunks: [],
    sources: [],
    model_name: null,
    token_usage: null,
    response_time_ms: null,
    feedback: null,
    feedback_comment: null,
    error_message: null,
    created_at: null,
  };
}
</script>

<template>
  <div ref="scrollRef" class="chat-main">
    <!-- 空状态 -->
    <div v-if="chatStore.messages.length === 0 && !chatStore.streaming" class="chat-empty">
      <el-icon class="empty-icon"><MagicStick /></el-icon>
      <div class="empty-title">EAKB 智能问答</div>
      <div class="empty-sub">
        基于企业知识库的检索增强问答，回答附带文档来源引用
      </div>
      <div class="empty-tips">
        <el-tag size="small" type="info">支持多轮对话</el-tag>
        <el-tag size="small" type="info">限定知识库分类</el-tag>
        <el-tag size="small" type="info">切换提示词模板</el-tag>
      </div>
    </div>

    <div v-else class="chat-messages" v-loading="chatStore.detailLoading">
      <MessageBubble
        v-for="message in chatStore.messages"
        :key="message.id"
        :message="message"
        @view-sources="handleViewSources"
        @feedback="handleFeedback"
      />

      <!-- 流式生成中的助手占位 -->
      <MessageBubble
        v-if="chatStore.streamingMessage"
        :message="buildStreamingPlaceholder()"
        streaming
        :streaming-content="chatStore.streamingMessage.content"
        :stream-error="chatStore.streamingMessage.error"
      />
    </div>
  </div>
</template>

<style lang="less" scoped>
.chat-main {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.chat-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;

  .empty-icon {
    font-size: 48px;
    color: @primary-light;
  }

  .empty-title {
    font-size: 22px;
    font-weight: 600;
    color: @text-primary;
  }

  .empty-sub {
    font-size: 14px;
    color: @text-secondary;
  }

  .empty-tips {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
}

.chat-messages {
  max-width: 860px;
  margin: 0 auto;
}
</style>
