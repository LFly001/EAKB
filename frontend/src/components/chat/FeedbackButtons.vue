<script setup lang="ts">
/**
 * 回答反馈组件 — 点赞/点踩 + 可选备注
 *
 * 点击 👍/👎 弹出备注输入框, 提交后调用方落库;
 * 已反馈状态高亮, 再次点击可修改反馈 (重复提交覆盖)。
 */
import { ref } from "vue";
import { ElMessage } from "element-plus";

// ==========================================
// Props / Emits
// ==========================================

defineProps<{
  messageId: number;
  feedback: "positive" | "negative" | null;
}>();

const emit = defineEmits<{
  (e: "submit", payload: { feedback: "positive" | "negative"; comment?: string }): void;
}>();

// ==========================================
// 状态
// ==========================================

const popoverVisible = ref(false);
const pendingFeedback = ref<"positive" | "negative">("positive");
const comment = ref("");
const submitting = ref(false);

function open(feedback: "positive" | "negative") {
  pendingFeedback.value = feedback;
  comment.value = "";
  popoverVisible.value = true;
}

async function submit() {
  submitting.value = true;
  try {
    emit("submit", {
      feedback: pendingFeedback.value,
      comment: comment.value.trim() || undefined,
    });
    popoverVisible.value = false;
    ElMessage.success("感谢您的反馈");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <el-popover
    v-model:visible="popoverVisible"
    placement="top"
    :width="320"
    trigger="click"
  >
    <template #reference>
      <div class="feedback-btns">
        <el-button
          text
          size="small"
          :type="feedback === 'positive' ? 'primary' : 'default'"
          :class="{ active: feedback === 'positive' }"
          @click.stop="open('positive')"
        >
          <el-icon><CaretTop /></el-icon>
          有帮助
        </el-button>
        <el-button
          text
          size="small"
          :type="feedback === 'negative' ? 'danger' : 'default'"
          :class="{ active: feedback === 'negative' }"
          @click.stop="open('negative')"
        >
          <el-icon><CaretBottom /></el-icon>
          无帮助
        </el-button>
      </div>
    </template>

    <div class="feedback-pop">
      <div class="feedback-pop-title">
        反馈：{{ pendingFeedback === "positive" ? "回答有帮助" : "回答无帮助" }}
      </div>
      <el-input
        v-model="comment"
        type="textarea"
        :rows="2"
        maxlength="1000"
        show-word-limit
        placeholder="可选备注，帮助改进回答质量"
      />
      <div class="feedback-pop-actions">
        <el-button size="small" @click="popoverVisible = false">取消</el-button>
        <el-button
          size="small"
          type="primary"
          :loading="submitting"
          @click="submit"
        >
          提交反馈
        </el-button>
      </div>
    </div>
  </el-popover>
</template>

<style lang="less" scoped>
.feedback-btns {
  display: flex;
  align-items: center;
  gap: 4px;

  :deep(.el-button) {
    margin-left: 0;
  }
}

.feedback-pop {
  &-title {
    font-size: 13px;
    color: @text-regular;
    margin-bottom: 8px;
  }

  &-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 10px;
  }
}
</style>
