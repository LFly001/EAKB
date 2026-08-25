<script setup lang="ts">
/**
 * 个人信息页面
 * 显示用户信息、修改个人资料、修改密码
 */
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { updateProfileApi, changePasswordApi } from "@/api/auth";
import type { FormInstance, FormRules } from "element-plus";
import { ROLE_LABELS, ROLE_TAG_TYPES } from "@/utils/constants";

const router = useRouter();
const authStore = useAuthStore();
const profileFormRef = ref<FormInstance>();
const passwordFormRef = ref<FormInstance>();
const loading = ref(false);
const savingPassword = ref(false);

const profileForm = reactive({
  real_name: "",
  email: "",
  phone: "",
});

const passwordForm = reactive({
  old_password: "",
  new_password: "",
  confirm_password: "",
});

const profileRules: FormRules = {
  email: [{ type: "email", message: "邮箱格式不正确", trigger: "blur" }],
};

const passwordRules: FormRules = {
  old_password: [
    { required: true, message: "请输入旧密码", trigger: "blur" },
  ],
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, message: "新密码不能少于6位", trigger: "blur" },
  ],
  confirm_password: [
    { required: true, message: "请确认新密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== passwordForm.new_password) {
          callback(new Error("两次密码输入不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

onMounted(() => {
  loadProfile();
});

function loadProfile() {
  if (authStore.userInfo) {
    profileForm.real_name = authStore.userInfo.real_name || "";
    profileForm.email = authStore.userInfo.email || "";
    profileForm.phone = authStore.userInfo.phone || "";
  }
}

async function handleUpdateProfile() {
  const valid = await profileFormRef.value?.validate().catch(() => false);
  if (!valid) return;

  loading.value = true;
  try {
    const res = await updateProfileApi({
      real_name: profileForm.real_name || undefined,
      email: profileForm.email || undefined,
      phone: profileForm.phone || undefined,
    });
    if (res.code === 200) {
      authStore.setUserInfo(res.data);
      ElMessage.success("个人信息更新成功");
    }
  } finally {
    loading.value = false;
  }
}

async function handleChangePassword() {
  const valid = await passwordFormRef.value?.validate().catch(() => false);
  if (!valid) return;

  savingPassword.value = true;
  try {
    const res = await changePasswordApi({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
      confirm_password: passwordForm.confirm_password,
    });
    if (res.code === 200) {
      // 清除本地登录态，强制重新登录
      authStore.clearAuth();
      ElMessage.success("密码修改成功，请使用新密码重新登录");
      router.push("/login");
    }
  } finally {
    savingPassword.value = false;
  }
}
</script>

<template>
  <div class="profile-page">
    <h2>个人信息</h2>

    <div class="profile-content">
      <!-- 基本信息 -->
      <el-card class="info-card">
        <template #header>
          <span>基本信息</span>
        </template>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户名">
            {{ authStore.userInfo?.username || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag
              :type="ROLE_TAG_TYPES[authStore.userInfo?.role || ''] || 'info'"
              size="small"
            >
              {{ ROLE_LABELS[authStore.userInfo?.role || ""] || "-" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="部门">
            {{ authStore.userInfo?.department || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="职位">
            {{ authStore.userInfo?.position || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="最后登录">
            {{ authStore.userInfo?.last_login_at || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">
            {{ authStore.userInfo?.created_at || "-" }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 编辑资料 -->
      <el-card class="info-card">
        <template #header>
          <span>编辑资料</span>
        </template>

        <el-form
          ref="profileFormRef"
          :model="profileForm"
          :rules="profileRules"
          label-width="100px"
          style="max-width: 480px"
        >
          <el-form-item label="真实姓名" prop="real_name">
            <el-input v-model="profileForm.real_name" placeholder="请输入姓名" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="profileForm.email" placeholder="请输入邮箱" />
          </el-form-item>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="profileForm.phone" placeholder="请输入手机号" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" @click="handleUpdateProfile">
              保存
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 修改密码 -->
      <el-card class="info-card">
        <template #header>
          <span>修改密码</span>
        </template>

        <el-form
          ref="passwordFormRef"
          :model="passwordForm"
          :rules="passwordRules"
          label-width="100px"
          style="max-width: 480px"
        >
          <el-form-item label="旧密码" prop="old_password">
            <el-input
              v-model="passwordForm.old_password"
              type="password"
              placeholder="请输入旧密码"
              show-password
            />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input
              v-model="passwordForm.new_password"
              type="password"
              placeholder="请输入新密码 (至少6位)"
              show-password
            />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm_password">
            <el-input
              v-model="passwordForm.confirm_password"
              type="password"
              placeholder="请确认新密码"
              show-password
            />
          </el-form-item>
          <el-form-item>
            <el-button
              type="danger"
              :loading="savingPassword"
              @click="handleChangePassword"
            >
              修改密码
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<style lang="less" scoped>
.profile-page {
  padding: 24px;
  max-width: 800px;

  h2 {
    margin-bottom: 24px;
  }
}

.profile-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.info-card {
  :deep(.el-card__header) {
    font-weight: 600;
  }
}
</style>
