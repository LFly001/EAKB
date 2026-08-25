<script setup lang="ts">
/**
 * 对话侧边栏 — 历史会话列表 + 新建对话 + 重命名 + 删除
 * 点击会话切换路由 /chat/:id, ChatView 监听路由加载详情。
 * Phase 8: useVirtualList 虚拟滚动 — 历史对话一次拉取 100 条, 只渲染可视区行。
 */
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useVirtualList } from "@vueuse/core";
import { ElMessage, ElMessageBox } from "element-plus";
import { useChatStore } from "@/stores/chat";
import { formatDate } from "@/utils/format";
import { confirmDanger } from "@/utils/feedback";

const router = useRouter();
const route = useRoute();
const chatStore = useChatStore();

// 会话行高 (padding 10*2 + 两行文本 ≈ 54px, 取 58 留 4px 余量避免行间重叠)
const CONV_ITEM_HEIGHT = 58;

// 虚拟滚动: 仅渲染可视区内的会话项
const { list: visibleConversations, containerProps, wrapperProps } = useVirtualList(
  computed(() => chatStore.conversations),
  { itemHeight: CONV_ITEM_HEIGHT }
);

onMounted(() => {
  chatStore.loadConversations();
});

/** 新建对话: 路由到 /chat, ChatView 重置状态 */
function handleCreate() {
  if (route.path === "/chat") return;
  router.push("/chat");
}

function handleSelect(id: number) {
  if (Number(route.params.conversationId) === id) return;
  router.push(`/chat/${id}`);
}

/** 重命名 — 弹窗输入新标题 */
async function handleRename(id: number, title: string) {
  try {
    const { value } = await ElMessageBox.prompt("请输入新的对话标题", "重命名对话", {
      inputValue: title,
      inputValidator: (v: string) =>
        v && v.trim().length > 0 && v.trim().length <= 100 ? true : "标题需为 1-100 字",
      confirmButtonText: "保存",
      cancelButtonText: "取消",
    });
    await chatStore.renameConversation(id, value.trim());
    ElMessage.success("标题已更新");
  } catch {
    // 用户取消
  }
}

/** 删除 — 二次确认 (统一封装, Phase 8) */
async function handleDelete(id: number, title: string) {
  const confirmed = await confirmDanger(
    `确定删除对话「${title}」吗？删除后消息记录不可恢复。`
  );
  if (!confirmed) return;
  await chatStore.removeConversation(id);
  ElMessage.success("对话已删除");
  // 删除当前对话时回到新对话页
  if (Number(route.params.conversationId) === id) {
    router.push("/chat");
  }
}
</script>

<template>
  <div class="chat-sidebar">
    <div class="sidebar-header">
      <el-button type="primary" class="create-btn" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        新建对话
      </el-button>
    </div>

    <div class="sidebar-title">
      历史对话
      <span class="sidebar-count">{{ chatStore.conversations.length }}</span>
    </div>

    <div v-loading="chatStore.conversationsLoading" v-bind="containerProps" class="sidebar-list">
      <div v-bind="wrapperProps" class="sidebar-list-inner">
        <el-empty
          v-if="!chatStore.conversationsLoading && chatStore.conversations.length === 0"
          description="暂无历史对话"
          :image-size="60"
        />
        <div
          v-for="{ data: conv } in visibleConversations"
          :key="conv.id"
          class="conv-item"
          :style="{ height: `${CONV_ITEM_HEIGHT}px` }"
          :class="{ active: Number(route.params.conversationId) === conv.id }"
          @click="handleSelect(conv.id)"
        >
          <div class="conv-main">
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-meta">
              {{ conv.message_count }} 轮 · {{ formatDate(conv.updated_at, "relative") }}
            </div>
          </div>
          <div class="conv-actions" @click.stop>
            <el-icon class="action-icon" @click="handleRename(conv.id, conv.title)">
              <EditPen />
            </el-icon>
            <el-icon class="action-icon danger" @click="handleDelete(conv.id, conv.title)">
              <Delete />
            </el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.chat-sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: @bg-white;
  border-right: 1px solid @border-light;
}

.sidebar-header {
  padding: 12px;

  .create-btn {
    width: 100%;
  }
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 16px 8px;
  font-size: 13px;
  color: @text-secondary;

  .sidebar-count {
    font-size: 12px;
    color: @text-placeholder;
  }
}

.sidebar-list {
  flex: 1;
  /* 虚拟滚动: 容器高度由 flex 撑开, overflow-y 由 useVirtualList 的 containerProps 注入 */
  padding-top: 8px;

  &-inner {
    /* wrapper 为定位元素, 不能加 padding (会破坏虚拟行偏移计算) */
  }
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 8px 2px;
  padding: 10px 12px;
  border-radius: @radius-small;
  cursor: pointer;
  transition: background-color 0.2s;
  box-sizing: border-box;

  &:hover {
    background: @bg-hover;

    .conv-actions {
      opacity: 1;
    }
  }

  &.active {
    background: @bg-active;

    .conv-title {
      color: @primary-color;
    }
  }
}

.conv-main {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 14px;
  color: @text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  margin-top: 2px;
  font-size: 12px;
  color: @text-placeholder;
}

.conv-actions {
  display: flex;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.2s;

  .action-icon {
    font-size: 14px;
    color: @text-secondary;

    &:hover {
      color: @primary-color;
    }

    &.danger:hover {
      color: @danger-color;
    }
  }
}
</style>
