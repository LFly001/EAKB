<script setup lang="ts">
/**
 * 注册页面
 */
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { registerApi } from "@/api/auth";
import type { FormInstance, FormRules } from "element-plus";

const router = useRouter();
const registerFormRef = ref<FormInstance>();
const loading = ref(false);

const form = reactive({
  username: "",
  password: "",
  confirmPassword: "",
  real_name: "",
  email: "",
  phone: "",
});

const rules: FormRules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { min: 3, max: 50, message: "用户名长度为 3-50 位", trigger: "blur" },
    {
      pattern: /^[a-zA-Z0-9_]+$/,
      message: "用户名只能包含字母、数字和下划线",
      trigger: "blur",
    },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, max: 128, message: "密码长度为 6-128 位", trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: "请确认密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) {
          callback(new Error("两次密码输入不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
  email: [{ type: "email", message: "邮箱格式不正确", trigger: "blur" }],
};

async function handleRegister() {
  const valid = await registerFormRef.value?.validate().catch(() => false);
  if (!valid) return;

  loading.value = true;
  try {
    const res = await registerApi({
      username: form.username,
      password: form.password,
      confirm_password: form.confirmPassword,
      real_name: form.real_name || undefined,
      email: form.email || undefined,
      phone: form.phone || undefined,
    });

    if (res.code === 200) {
      ElMessage.success("注册成功，请登录");
      router.push("/login");
    }
  } catch {
    // 错误已在 request 拦截器中统一提示
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="register-page">
    <div class="register-card">
      <div class="register-header">
        <h1>创建账号</h1>
        <p>注册 EAKB 企业知识库智能助手</p>
      </div>

      <el-form
        ref="registerFormRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
      >
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="form.username"
                placeholder="工号/英文名"
                prefix-icon="User"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="真实姓名" prop="real_name">
              <el-input
                v-model="form.real_name"
                placeholder="选填"
                prefix-icon="UserFilled"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少6位"
            prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="再次输入密码"
            prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input
                v-model="form.email"
                placeholder="选填"
                prefix-icon="Message"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input
                v-model="form.phone"
                placeholder="选填"
                prefix-icon="Phone"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            style="width: 100%"
            @click="handleRegister"
          >
            注 册
          </el-button>
        </el-form-item>
      </el-form>

      <div class="register-footer">
        <span>已有账号？</span>
        <router-link to="/login">去登录</router-link>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.register-page {
  width: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%);
}

.register-card {
  width: 500px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.register-header {
  text-align: center;
  margin-bottom: 32px;

  h1 {
    font-size: 24px;
    color: #1a1a2e;
    margin: 0;
  }

  p {
    color: #909399;
    margin-top: 8px;
    font-size: 14px;
  }
}

.register-footer {
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
