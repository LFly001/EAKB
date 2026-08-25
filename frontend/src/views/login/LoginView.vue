<script setup lang="ts">
/**
 * 登录页面
 */
import { ref, reactive } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { loginApi } from "@/api/auth";
import type { FormInstance, FormRules } from "element-plus";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const loginFormRef = ref<FormInstance>();
const loading = ref(false);

const form = reactive({
  username: "",
  password: "",
});

const rules: FormRules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, message: "密码不能少于6位", trigger: "blur" },
  ],
};

async function handleLogin() {
  const valid = await loginFormRef.value?.validate().catch(() => false);
  if (!valid) return;

  loading.value = true;
  try {
    const res = await loginApi({
      username: form.username,
      password: form.password,
    });

    if (res.code === 200) {
      const { access_token, refresh_token, user } = res.data;
      authStore.setTokens(access_token, refresh_token);
      authStore.setUserInfo(user);
      ElMessage.success("登录成功");

      // 跳转到重定向页面或首页
      const redirect = (route.query.redirect as string) || "/dashboard";
      router.push(redirect);
    }
  } catch {
    // 错误已在 request 拦截器中统一提示
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1>EAKB</h1>
        <p>企业知识库智能助手</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            prefix-icon="User"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            style="width: 100%"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <span>还没有账号？</span>
        <router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.login-page {
  width: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%);
}

.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;

  h1 {
    font-size: 32px;
    color: #1a1a2e;
    margin: 0;
    letter-spacing: 4px;
  }

  p {
    color: #909399;
    margin-top: 8px;
    font-size: 14px;
  }
}

.login-footer {
  text-align: center;
  margin-top: 16px;
  color: #909399;
  font-size: 14px;

  a {
    color: #409eff;
    margin-left: 4px;
  }
}
</style>
