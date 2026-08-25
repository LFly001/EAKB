<script setup lang="ts">
/**
 * 智能问答主页面 — 侧边栏 / 消息主区 / 来源面板三栏布局
 *
 * - 路由 /chat 为新对话, /chat/:conversationId 加载历史会话
 * - SSE 流式编排: 发送问题 → useSSE 事件流 → chat store 状态更新
 * - 流式过程中 onMeta 自动跳转新会话路由 (不打断当前流)
 */
import { watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChatSidebar from "./ChatSidebar.vue";
import ChatMain from "./ChatMain.vue";
import ChatInput from "./ChatInput.vue";
import SourcePanel from "./SourcePanel.vue";
import { useSSE } from "@/composables/useSSE";
import { CHAT_STREAM_PATH } from "@/api/rag";
import { useChatStore } from "@/stores/chat";
import type { ChatMessage } from "@/types/chat";

const route = useRoute();
const router = useRouter();
const chatStore = useChatStore();
const { start, stop } = useSSE();

// ==========================================
// 路由监听 — 切换会话 / 新对话
// ==========================================

watch(
  () => route.params.conversationId,
  async (id) => {
    // onMeta 触发的路由跳转: 目标即当前流式会话, 不打断
    if (chatStore.streaming) {
      if (id && chatStore.currentConversationId === Number(id)) return;
      stop();
      chatStore.abortStream();
    }

    if (id) {
      await chatStore.loadDetail(Number(id));
    } else {
      chatStore.resetConversation();
    }
  },
  { immediate: true }
);

// ==========================================
// 问答流式编排
// ==========================================

async function sendQuestion(question: string) {
  if (chatStore.streaming) return;

  chatStore.beginStream(question);

  await start(
    CHAT_STREAM_PATH,
    {
      question,
      conversation_id: chatStore.currentConversationId,
      template_id: chatStore.draftTemplateId,
      category_ids: chatStore.draftCategoryIds,
    },
    {
      onMeta: (data) => {
        chatStore.applyMeta(data.conversation_id, data.user_message_id);
        // 自动新建的会话: 路由补上会话 ID (watcher 因 streaming 跳过不打断)
        if (!route.params.conversationId) {
          router.replace(`/chat/${data.conversation_id}`);
        }
      },
      onSources: (data) => chatStore.applySources(data),
      onDelta: (content) => chatStore.appendDelta(content),
      onDone: (data) => chatStore.finishStream(data),
      onError: (message) => chatStore.failStream(message),
    }
  );
}

/** 停止生成 (用户主动中止) */
function handleStop() {
  stop();
  chatStore.abortStream();
}

/** 断线/失败重试 — 重新发送最近一次问题 */
function handleRetry() {
  if (chatStore.lastQuestion) {
    sendQuestion(chatStore.lastQuestion);
  }
}

// ==========================================
// 来源 / 反馈事件
// ==========================================

function handleViewSources(message: ChatMessage) {
  chatStore.openSources({
    sources: message.sources || [],
    retrieved_chunks: message.retrieved_chunks || [],
  });
}

async function handleFeedback(payload: {
  messageId: number;
  feedback: "positive" | "negative";
  comment?: string;
}) {
  try {
    await chatStore.submitFeedback(payload.messageId, payload.feedback, payload.comment);
  } catch {
    // request 拦截器已提示错误
  }
}
</script>

<template>
  <div class="chat-view">
    <ChatSidebar />

    <div class="chat-body">
      <ChatMain
        @view-sources="handleViewSources"
        @feedback="handleFeedback"
      />
      <ChatInput @send="sendQuestion" @stop="handleStop" @retry="handleRetry" />
    </div>

    <SourcePanel
      v-if="chatStore.selectedSources"
      :sources="chatStore.selectedSources.sources"
      :retrieved-chunks="chatStore.selectedSources.retrieved_chunks"
      @close="chatStore.clearSelectedSources()"
    />
  </div>
</template>

<style lang="less" scoped>
.chat-view {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: @bg-page;
}
</style>
