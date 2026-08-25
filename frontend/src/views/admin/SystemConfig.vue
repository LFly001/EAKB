<script setup lang="ts">
/**
 * 系统配置页 — 管理员 (Phase 7)
 * 可视化表单修改 sys_config; 保存后后端实时生效 (无需重启服务)
 * 按 config_type 渲染控件: number 数字 / json 多行 / string 单行
 */
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getConfigsApi, updateConfigApi } from "@/api/admin";
import type { ConfigItem } from "@/types/admin";

const loading = ref(false);
const saving = ref(false);
const configs = ref<ConfigItem[]>([]);

/** 行内编辑状态: 编辑中的键 + 草稿值 */
const editingKey = ref<string | null>(null);
const draftValue = ref("");

const TYPE_LABELS: Record<string, string> = {
  string: "字符串",
  number: "数字",
  json: "JSON",
};

// ==========================================
// 数据请求
// ==========================================
async function fetchConfigs() {
  loading.value = true;
  try {
    const res = await getConfigsApi();
    if (res.code === 200) {
      configs.value = res.data;
    }
  } finally {
    loading.value = false;
  }
}

// ==========================================
// 行内编辑
// ==========================================
function startEdit(item: ConfigItem) {
  editingKey.value = item.config_key;
  draftValue.value = item.config_value ?? "";
}

function cancelEdit() {
  editingKey.value = null;
  draftValue.value = "";
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").slice(0, 19);
}

/** 按 config_type 校验草稿值, 返回错误信息或 null */
function validateDraft(item: ConfigItem): string | null {
  const value = draftValue.value.trim();
  if (value === "") {
    return "配置值不能为空";
  }
  if (item.config_type === "number") {
    const num = Number(value);
    if (Number.isNaN(num)) {
      return "该配置为数字类型，请输入合法数字";
    }
  } else if (item.config_type === "json") {
    try {
      JSON.parse(value);
    } catch {
      return "该配置为 JSON 类型，请输入合法 JSON";
    }
  }
  return null;
}

async function saveEdit(item: ConfigItem) {
  const error = validateDraft(item);
  if (error) {
    ElMessage.error(error);
    return;
  }

  saving.value = true;
  try {
    const res = await updateConfigApi(item.config_key, draftValue.value.trim());
    if (res.code === 200) {
      ElMessage.success(res.msg);
      cancelEdit();
      fetchConfigs();
    }
  } finally {
    saving.value = false;
  }
}

/** 恢复默认值说明 — 配置在数据库中无值时自动回退 .env 默认值 */
async function showResetHint() {
  await ElMessageBox.alert(
    "配置值保存后立即生效，无需重启服务。\n" +
      "若删除数据库中的配置值（置空不允许），各业务模块将回退到 .env 环境变量的默认值。\n" +
      "修改 chunk_size / chunk_overlap 仅影响之后新上传文档的向量化，已分块文档不受影响。",
    "配置生效说明",
    { confirmButtonText: "知道了" }
  );
}

onMounted(() => {
  fetchConfigs();
});
</script>

<template>
  <div class="page-container">
    <div class="flex-between" style="margin-bottom: 16px">
      <h2>系统配置</h2>
      <div>
        <el-button @click="showResetHint">
          <el-icon><QuestionFilled /></el-icon>
          <span style="margin-left: 4px">生效说明</span>
        </el-button>
        <el-button type="primary" :loading="loading" @click="fetchConfigs">
          <el-icon><Refresh /></el-icon>
          <span style="margin-left: 4px">刷新</span>
        </el-button>
      </div>
    </div>

    <el-alert
      type="success"
      :closable="false"
      show-icon
      title="配置修改实时全局生效：分块参数 / 检索参数 / 上传大小等由各业务模块每次从数据库读取"
      style="margin-bottom: 16px"
    />

    <el-card v-loading="loading">
      <el-table :data="configs" stripe>
        <el-table-column prop="config_key" label="配置键" width="200" />
        <el-table-column prop="description" label="说明" width="200">
          <template #default="{ row }">
            {{ row.description || "—" }}
          </template>
        </el-table-column>
        <el-table-column label="值" min-width="280">
          <template #default="{ row }">
            <!-- 编辑态 -->
            <template v-if="editingKey === row.config_key">
              <el-input
                v-if="row.config_type === 'json'"
                v-model="draftValue"
                type="textarea"
                :rows="3"
                placeholder="合法 JSON，如 {&quot;key&quot;: &quot;value&quot;}"
              />
              <el-input
                v-else
                v-model="draftValue"
                style="width: 100%"
                :placeholder="row.config_type === 'number' ? '数字，如 512 / 0.7' : ''"
              />
            </template>
            <!-- 展示态 -->
            <span v-else class="value-text text-ellipsis">
              {{ row.config_value ?? "—" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.config_type === 'number' ? 'success' : row.config_type === 'json' ? 'warning' : 'info'">
              {{ TYPE_LABELS[row.config_type] || row.config_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <template v-if="editingKey === row.config_key">
              <el-button size="small" type="primary" :loading="saving" @click="saveEdit(row as ConfigItem)">
                保存
              </el-button>
              <el-button size="small" @click="cancelEdit">取消</el-button>
            </template>
            <el-button v-else size="small" @click="startEdit(row as ConfigItem)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style lang="less" scoped>
.value-text {
  display: inline-block;
  max-width: 420px;
  vertical-align: middle;
  font-size: 13px;
  color: @text-regular;
}
</style>
