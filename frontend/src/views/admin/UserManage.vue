<script setup lang="ts">
/**
 * 用户管理页 — 管理员 (Phase 7 完整版)
 * 搜索筛选 / 创建 / 编辑 / 单条启停删除 / 批量启停删除
 */
import { ref, reactive, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import {
  batchUserApi,
  createUserApi,
  deleteUserApi,
  getUserListApi,
  toggleUserStatusApi,
  updateUserApi,
} from "@/api/user";
import type { UserInfo } from "@/types/user";
import { ROLE_LABELS } from "@/utils/constants";

// ==========================================
// 列表状态
// ==========================================
const loading = ref(false);
const users = ref<UserInfo[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const filterRole = ref("");
const filterStatus = ref<number | undefined>(undefined);

// 批量选择
const selectedRows = ref<UserInfo[]>([]);
const batchLoading = ref(false);

// ==========================================
// 创建 / 编辑弹窗
// ==========================================
const dialogVisible = ref(false);
const dialogMode = ref<"create" | "edit">("create");
const dialogTitle = ref("创建用户");
const saving = ref(false);
const formRef = ref<FormInstance>();

interface UserFormModel {
  username: string;
  password: string;
  email: string;
  phone: string;
  real_name: string;
  department: string;
  position: string;
  role: "admin" | "employee";
  status: 0 | 1;
}

const emptyForm = (): UserFormModel => ({
  username: "",
  password: "",
  email: "",
  phone: "",
  real_name: "",
  department: "",
  position: "",
  role: "employee",
  status: 1,
});

const form = reactive<UserFormModel>(emptyForm());
const editingUser = ref<UserInfo | null>(null);

/** 动态校验规则: 编辑模式不校验用户名与密码 (弹窗中隐藏) */
const formRules = computed<FormRules>(() => ({
  username: dialogMode.value === "create"
    ? [
        { required: true, message: "请输入用户名", trigger: "blur" },
        { min: 3, max: 50, message: "长度 3-50 个字符", trigger: "blur" },
      ]
    : [],
  password: dialogMode.value === "create"
    ? [
        { required: true, message: "请输入初始密码", trigger: "blur" },
        { min: 6, max: 128, message: "长度 6-128 个字符", trigger: "blur" },
      ]
    : [],
}));

// ==========================================
// 数据请求
// ==========================================
async function fetchUsers() {
  loading.value = true;
  try {
    const res = await getUserListApi({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      role: filterRole.value || undefined,
      status: filterStatus.value,
    });
    if (res.code === 200) {
      users.value = res.data.items;
      total.value = res.data.total;
    }
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  fetchUsers();
}

function handleReset() {
  keyword.value = "";
  filterRole.value = "";
  filterStatus.value = undefined;
  page.value = 1;
  fetchUsers();
}

function handleSelectionChange(rows: UserInfo[]) {
  selectedRows.value = rows;
}

// ==========================================
// 创建 / 编辑
// ==========================================
function openCreate() {
  dialogMode.value = "create";
  dialogTitle.value = "创建用户";
  Object.assign(form, emptyForm());
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

function openEdit(user: UserInfo) {
  editingUser.value = user;
  dialogMode.value = "edit";
  dialogTitle.value = `编辑用户 — ${user.username}`;
  Object.assign(form, {
    username: user.username,
    password: "",
    email: user.email || "",
    phone: user.phone || "",
    real_name: user.real_name || "",
    department: user.department || "",
    position: user.position || "",
    role: user.role,
    status: user.status,
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  saving.value = true;
  try {
    if (dialogMode.value === "create") {
      const res = await createUserApi({
        username: form.username,
        password: form.password,
        email: form.email || undefined,
        phone: form.phone || undefined,
        real_name: form.real_name || undefined,
        department: form.department || undefined,
        position: form.position || undefined,
        role: form.role,
        status: form.status,
      });
      if (res.code === 200) {
        ElMessage.success(res.msg);
        dialogVisible.value = false;
        fetchUsers();
      }
    } else {
      const res = await updateUserApi(editingUser.value!.id, {
        email: form.email || undefined,
        phone: form.phone || undefined,
        real_name: form.real_name || undefined,
        department: form.department || undefined,
        position: form.position || undefined,
        role: form.role,
        status: form.status,
      });
      if (res.code === 200) {
        ElMessage.success(res.msg);
        dialogVisible.value = false;
        fetchUsers();
      }
    }
  } finally {
    saving.value = false;
  }
}

// ==========================================
// 单条操作
// ==========================================
async function handleToggleStatus(user: UserInfo) {
  const newStatus = user.status === 1 ? 0 : 1;
  const action = newStatus === 1 ? "启用" : "禁用";
  try {
    await ElMessageBox.confirm(`确定要${action}用户 "${user.username}" 吗？`, "确认操作");
    const res = await toggleUserStatusApi(user.id, newStatus);
    if (res.code === 200) {
      ElMessage.success(res.msg);
      fetchUsers();
    }
  } catch {
    // 取消操作
  }
}

async function handleDelete(user: UserInfo) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${user.username}" 吗？此操作不可逆！`,
      "危险操作",
      { type: "warning" }
    );
    const res = await deleteUserApi(user.id);
    if (res.code === 200) {
      ElMessage.success(res.msg);
      fetchUsers();
    }
  } catch {
    // 取消
  }
}

// ==========================================
// 批量操作 (Phase 7)
// ==========================================
async function handleBatch(action: "enable" | "disable" | "delete") {
  if (selectedRows.value.length === 0) {
    ElMessage.warning("请先勾选要操作的用户");
    return;
  }
  const actionText = action === "enable" ? "启用" : action === "disable" ? "禁用" : "删除";
  try {
    await ElMessageBox.confirm(
      `确定要批量${actionText}已选中的 ${selectedRows.value.length} 个用户吗？${
        action === "delete" ? "此操作不可逆！" : ""
      }`,
      "批量操作确认",
      { type: action === "delete" ? "warning" : undefined }
    );
  } catch {
    return;
  }

  batchLoading.value = true;
  try {
    const res = await batchUserApi({
      user_ids: selectedRows.value.map((u) => u.id),
      action,
    });
    if (res.code === 200) {
      ElMessage.success(res.msg);
      fetchUsers();
    }
  } finally {
    batchLoading.value = false;
  }
}

onMounted(() => {
  fetchUsers();
});
</script>

<template>
  <div class="page-container">
    <div class="flex-between" style="margin-bottom: 16px">
      <h2>用户管理</h2>
      <div>
        <el-button
          type="success"
          :disabled="selectedRows.length === 0"
          :loading="batchLoading"
          @click="handleBatch('enable')"
        >
          批量启用
        </el-button>
        <el-button
          type="warning"
          :disabled="selectedRows.length === 0"
          :loading="batchLoading"
          @click="handleBatch('disable')"
        >
          批量禁用
        </el-button>
        <el-button
          type="danger"
          :disabled="selectedRows.length === 0"
          :loading="batchLoading"
          @click="handleBatch('delete')"
        >
          批量删除
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          <span style="margin-left: 4px">创建用户</span>
        </el-button>
      </div>
    </div>

    <!-- 搜索栏 -->
    <div class="page-toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名/姓名/部门"
        clearable
        style="width: 240px"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      />
      <el-select
        v-model="filterRole"
        placeholder="角色"
        clearable
        style="width: 130px"
        @change="handleSearch"
      >
        <el-option :label="ROLE_LABELS.admin" value="admin" />
        <el-option label="员工" value="employee" />
      </el-select>
      <el-select
        v-model="filterStatus"
        placeholder="状态"
        clearable
        style="width: 130px"
        @change="handleSearch"
      >
        <el-option label="启用" :value="1" />
        <el-option label="禁用" :value="0" />
      </el-select>
      <el-button type="primary" @click="handleSearch">搜索</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <!-- 用户表格 -->
    <el-card>
      <el-table
        :data="users"
        v-loading="loading"
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" width="130" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="department" label="部门" width="130" />
        <el-table-column prop="position" label="职位" width="110" />
        <el-table-column prop="role" label="角色" width="90">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ ROLE_LABELS[row.role] || row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">
              {{ row.status === 1 ? "启用" : "禁用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="170" />
        <el-table-column label="操作" min-width="190" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row as UserInfo)">编辑</el-button>
            <el-button
              size="small"
              :type="row.status === 1 ? 'warning' : 'success'"
              @click="handleToggleStatus(row as UserInfo)"
            >
              {{ row.status === 1 ? "禁用" : "启用" }}
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row as UserInfo)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div style="margin-top: 16px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @change="fetchUsers"
        />
      </div>
    </el-card>

    <!-- 创建 / 编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item v-if="dialogMode === 'create'" label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="3-50 个字符" />
        </el-form-item>
        <el-form-item v-if="dialogMode === 'create'" label="初始密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="6-128 个字符" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.real_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="example@company.com" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="手机号码" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="form.department" placeholder="所属部门" />
        </el-form-item>
        <el-form-item label="职位">
          <el-input v-model="form.position" placeholder="职位名称" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="form.role">
            <el-radio value="employee">员工</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch
            v-model="form.status"
            :active-value="1"
            :inactive-value="0"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
