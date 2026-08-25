<script setup lang="ts">
/**
 * 文档上传
 * 选择分类 → 多文件选择 (格式/大小校验) → 上传 → 后台自动向量化
 */
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import FileUploader from "@/components/common/FileUploader.vue";
import { getCategoryTreeApi } from "@/api/category";
import { uploadDocumentsApi } from "@/api/document";
import type { CategoryNode } from "@/types/knowledge";

const router = useRouter();

// ==========================================
// 状态
// ==========================================

const categoryTree = ref<CategoryNode[]>([]);
const files = ref<File[]>([]);
const uploading = ref(false);

const form = reactive({
  category_id: null as number | null,
  title: "",
  description: "",
  tags: "",
});

// 上传格式/大小限制 (与后端 settings 对齐)
const ALLOWED_EXTENSIONS = ["pdf", "docx", "txt", "md", "xlsx"];
const MAX_SIZE_MB = 50;

// ==========================================
// 分类加载
// ==========================================

onMounted(async () => {
  const res = await getCategoryTreeApi();
  categoryTree.value = res.data || [];
});

// ==========================================
// 上传
// ==========================================

async function handleUpload() {
  if (!form.category_id) {
    ElMessage.warning("请选择所属分类");
    return;
  }
  if (files.value.length === 0) {
    ElMessage.warning("请选择要上传的文件");
    return;
  }

  const formData = new FormData();
  files.value.forEach((file) => formData.append("files", file));
  formData.append("category_id", String(form.category_id));
  // 标题仅单文件上传时生效
  if (files.value.length === 1 && form.title.trim()) {
    formData.append("title", form.title.trim());
  }
  if (form.description.trim()) {
    formData.append("description", form.description.trim());
  }
  if (form.tags.trim()) {
    formData.append("tags", form.tags.trim());
  }

  uploading.value = true;
  try {
    const res = await uploadDocumentsApi(formData);
    const docs = res.data || [];
    ElMessage.success(
      `上传成功 ${docs.length} 个文档，向量化任务已在后台执行，可前往文档列表查看进度`
    );
    // 跳转到文档列表跟踪向量化状态
    setTimeout(() => router.push("/knowledge/documents"), 800);
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">上传文档</span>
          <el-button link type="primary" @click="router.push('/knowledge/documents')">
            前往文档列表
          </el-button>
        </div>
      </template>

      <el-form :model="form" label-width="90px" class="upload-form">
        <el-form-item label="所属分类" required>
          <el-tree-select
            v-model="form.category_id"
            :data="categoryTree"
            :props="({ label: 'name', children: 'children', value: 'id' } as any)"
            node-key="id"
            check-strictly
            placeholder="请选择知识库分类"
            style="width: 400px"
          />
        </el-form-item>

        <el-form-item label="文档标题">
          <el-input
            v-model="form.title"
            placeholder="不填则使用文件名 (仅单文件上传时生效)"
            maxlength="255"
            style="width: 400px"
          />
        </el-form-item>

        <el-form-item label="标签">
          <el-input
            v-model="form.tags"
            placeholder="多个标签用逗号分隔 (可选)"
            maxlength="500"
            style="width: 400px"
          />
        </el-form-item>

        <el-form-item label="文档描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="文档描述 (可选)"
            maxlength="5000"
            style="width: 600px"
          />
        </el-form-item>

        <el-form-item label="选择文件" required>
          <FileUploader
            v-model:files="files"
            :accept="ALLOWED_EXTENSIONS"
            :max-size-mb="MAX_SIZE_MB"
            multiple
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="uploading" @click="handleUpload">
            <el-icon><Upload /></el-icon>
            {{ uploading ? "上传中..." : `上传 (${files.length} 个文件)` }}
          </el-button>
          <span class="upload-hint">上传完成后系统将自动解析、分块并向量化入库</span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style lang="less" scoped>
.page-container {
  padding: @spacing-md;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .card-title {
    font-size: 15px;
    font-weight: 600;
    color: @text-primary;
  }
}

.upload-form {
  max-width: 760px;
}

.upload-hint {
  margin-left: 12px;
  font-size: 12px;
  color: @text-secondary;
}
</style>
