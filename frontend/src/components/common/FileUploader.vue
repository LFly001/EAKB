<script setup lang="ts">
/**
 * 通用文件上传组件
 * 统一校验文件格式 / 大小, 手动上传模式 (父组件调用 API 提交)
 *
 * 用法:
 *   <FileUploader
 *     v-model:files="selectedFiles"
 *     :accept="['pdf', 'docx', 'txt', 'md', 'xlsx']"
 *     :max-size-mb="50"
 *     multiple
 *   />
 *
 * 注意: element-plus 2.9.x 的 el-upload 在 auto-upload=false 时,
 * on-change 触发早于 v-model:file-list 同步, 因此这里通过 watch(fileList)
 * 统一向父组件转发有效文件, on-change 仅做校验。
 */
import { computed, nextTick, ref, watch } from "vue";
import {
  ElMessage,
  type UploadFile,
  type UploadInstance,
  type UploadRawFile,
  type UploadUserFile,
} from "element-plus";

const props = defineProps({
  /** 允许的文件后缀 (不含点, 小写) */
  accept: {
    type: Array as () => string[],
    default: () => ["pdf", "docx", "txt", "md", "xlsx"],
  },
  /** 单文件大小上限 (MB) */
  maxSizeMb: {
    type: Number,
    default: 50,
  },
  /** 是否多选 */
  multiple: {
    type: Boolean,
    default: true,
  },
  /** 最大文件数量 */
  limit: {
    type: Number,
    default: 20,
  },
  /** 是否禁用 */
  disabled: {
    type: Boolean,
    default: false,
  },
  /** 已选文件 (v-model) */
  files: {
    type: Array as () => File[],
    default: () => [],
  },
});

const emit = defineEmits<{
  (e: "update:files", files: File[]): void;
}>();

const uploadRef = ref<UploadInstance>();
const fileList = ref<UploadUserFile[]>([]);

// ==========================================
// 校验
// ==========================================

function getFileExt(name: string): string {
  const match = name.match(/\.([a-zA-Z0-9]+)$/);
  return match ? match[1].toLowerCase() : "";
}

function validateFile(file: File): string | null {
  const ext = getFileExt(file.name);
  if (!ext || !props.accept.includes(ext)) {
    return `文件 '${file.name}' 格式不支持，允许: ${props.accept.join(", ")}`;
  }
  if (file.size > props.maxSizeMb * 1024 * 1024) {
    return `文件 '${file.name}' 超过 ${props.maxSizeMb}MB 大小限制`;
  }
  return null;
}

// ==========================================
// 事件处理
// ==========================================

function handleChange(uploadFile: UploadUserFile) {
  const raw = uploadFile.raw as File | undefined;
  if (!raw) return;

  const error = validateFile(raw);
  if (error) {
    ElMessage.error(error);
    // v-model 同步发生在 on-change 之后, 延迟到下一拍再移除非法文件
    // UploadUserFile → UploadFile 结构兼容 (status 等字段 EP 定义必填, 实际可缺省)
    nextTick(() => {
      uploadRef.value?.handleRemove(uploadFile as UploadFile);
    });
  }
}

function handleExceed() {
  ElMessage.warning(`最多上传 ${props.limit} 个文件`);
}

/** 清空已选文件 */
function clearFiles() {
  fileList.value = [];
}

defineExpose({ clearFiles });

// ==========================================
// 双向同步
// ==========================================

// el-upload 内部列表变化 (新增/移除/清空) → 转发有效文件给父组件
watch(fileList, () => {
  emit(
    "update:files",
    fileList.value
      .map((f) => f.raw)
      // raw 类型为 UploadRawFile (File & {uid}) | undefined, 谓词需与元素类型兼容
      .filter((f): f is UploadRawFile => f instanceof File)
  );
});

// 父组件 v-model:files 重置为空 → 同步清空内部列表
watch(
  () => props.files,
  (files) => {
    if (!files || files.length === 0) {
      fileList.value = [];
    }
  }
);

// 提示文案
const tipText = computed(
  () =>
    `支持格式: ${props.accept.join(" / ")}，单个文件不超过 ${props.maxSizeMb}MB` +
    (props.multiple ? `，最多 ${props.limit} 个` : "")
);
</script>

<template>
  <div class="file-uploader">
    <el-upload
      ref="uploadRef"
      v-model:file-list="fileList"
      drag
      :auto-upload="false"
      :multiple="multiple"
      :limit="limit"
      :disabled="disabled"
      :on-change="handleChange"
      :on-exceed="handleExceed"
      :accept="'.' + accept.join(',.')"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">
        将文件拖到此处，或<em>点击选择文件</em>
      </div>
    </el-upload>
    <div class="uploader-tip">{{ tipText }}</div>
  </div>
</template>

<style lang="less" scoped>
.file-uploader {
  width: 100%;

  .uploader-tip {
    margin-top: 8px;
    font-size: 12px;
    color: @text-secondary;
  }
}
</style>
