<script setup lang="ts">
/**
 * 来源引用面板 — 展示回答引用的文档来源与检索分块
 * 来源按文档聚合 (relevance_score = 该文档命中分块最高分),
 * 展开来源查看具体分块文本与相似度。
 */
import { computed, ref } from "vue";
import type { MessageSource, RetrievedChunk } from "@/types/chat";

const props = defineProps<{
  sources: MessageSource[];
  retrievedChunks: RetrievedChunk[];
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

/** 分块按文档分组 */
const chunksByDocument = computed<Record<number, RetrievedChunk[]>>(() => {
  const grouped: Record<number, RetrievedChunk[]> = {};
  for (const chunk of props.retrievedChunks) {
    const docId = chunk.document_id;
    if (docId == null) continue;
    (grouped[docId] ||= []).push(chunk);
  }
  return grouped;
});

/** 展开的文档 ID 列表 (el-collapse 受控) */
const activeDocs = ref<number[]>(props.sources.map((s) => s.document_id));

function formatScore(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}
</script>

<template>
  <aside class="source-panel">
    <div class="panel-header">
      <span class="panel-title">
        <el-icon><Document /></el-icon>
        引用来源 ({{ sources.length }})
      </span>
      <el-icon class="close-icon" @click="emit('close')"><Close /></el-icon>
    </div>

    <el-scrollbar class="panel-body">
      <el-empty
        v-if="sources.length === 0"
        description="本次回答未引用知识库内容"
        :image-size="60"
      />
      <el-collapse v-else v-model="activeDocs" class="source-collapse">
        <el-collapse-item
          v-for="source in sources"
          :key="source.document_id"
          :name="source.document_id"
        >
          <template #title>
            <div class="source-title">
              <span class="source-name">{{ source.title }}</span>
              <el-tag size="small" type="success" effect="plain">
                {{ formatScore(source.relevance_score) }}
              </el-tag>
            </div>
            <div class="source-file">{{ source.file_name }}</div>
          </template>

          <div class="chunk-list">
            <div
              v-for="(chunk, index) in chunksByDocument[source.document_id] || []"
              :key="chunk.chunk_id"
              class="chunk-item"
            >
              <div class="chunk-head">
                <span class="chunk-index">分块 {{ index + 1 }}</span>
                <span class="chunk-score">{{ formatScore(chunk.score) }}</span>
              </div>
              <div class="chunk-text">{{ chunk.text }}</div>
            </div>
            <el-empty
              v-if="!(chunksByDocument[source.document_id] || []).length"
              description="暂无分块明细"
              :image-size="40"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-scrollbar>
  </aside>
</template>

<style lang="less" scoped>
.source-panel {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: @bg-white;
  border-left: 1px solid @border-light;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid @border-light;

  .panel-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    font-weight: 600;
    color: @text-primary;
  }

  .close-icon {
    font-size: 16px;
    color: @text-secondary;
    cursor: pointer;

    &:hover {
      color: @text-primary;
    }
  }
}

.panel-body {
  flex: 1;
  overflow: hidden;
  padding: 8px;
}

.source-collapse {
  border: none;

  :deep(.el-collapse-item__header) {
    height: auto;
    line-height: 1.5;
    align-items: flex-start;
    padding: 10px 8px;
  }

  :deep(.el-collapse-item__wrap) {
    border-bottom: none;
  }
}

.source-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;

  .source-name {
    font-size: 13px;
    font-weight: 500;
    color: @text-primary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.source-file {
  font-size: 12px;
  color: @text-placeholder;
  margin-top: 2px;
}

.chunk-list {
  padding: 0 8px;
}

.chunk-item {
  padding: 8px 0;
  border-bottom: 1px dashed @border-light;

  &:last-child {
    border-bottom: none;
  }
}

.chunk-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;

  .chunk-index {
    font-size: 12px;
    color: @text-secondary;
  }

  .chunk-score {
    font-size: 12px;
    color: @success-color;
  }
}

.chunk-text {
  font-size: 12px;
  line-height: 1.6;
  color: @text-regular;
  max-height: 96px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
