<template>
  <div class="auth-page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />
    <div class="orb orb-3" />

    <div class="auth-card">
      <div class="auth-header">
        <div class="auth-logo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
              stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h1 class="auth-title">创建账号</h1>
        <p class="auth-subtitle">加入内容生成平台，开启创作之旅</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="auth-form"
        @submit.prevent="handleRegister"
      >
        <el-form-item prop="email">
          <template #label><span class="field-label">邮箱地址</span></template>
          <el-input v-model="form.email" type="email" placeholder="your@email.com"
            size="large" :prefix-icon="Message" />
        </el-form-item>

        <el-form-item prop="username">
          <template #label><span class="field-label">用户名</span></template>
          <el-input v-model="form.username" placeholder="至少 2 个字符"
            size="large" :prefix-icon="User" />
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item prop="password">
              <template #label><span class="field-label">密码</span></template>
              <el-input v-model="form.password" type="password" show-password
                placeholder="至少 8 位" size="large" :prefix-icon="Lock" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item prop="confirm">
              <template #label><span class="field-label">确认密码</span></template>
              <el-input v-model="form.confirm" type="password" show-password
                placeholder="再次输入" size="large" :prefix-icon="Lock" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="loading"
          @click="handleRegister"
        >
          <span v-if="!loading">创建账号</span>
          <span v-else>注册中...</span>
        </el-button>
      </el-form>

      <p class="switch-link">
        已有账号？
        <router-link to="/login" class="switch-action">去登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Message, Lock, User } from "@element-plus/icons-vue";
import { authAPI } from "@/api";

const router  = useRouter();
const formRef = ref();
const loading = ref(false);
const form    = ref({ email: "", username: "", password: "", confirm: "" });

const validateConfirm = (rule, value, callback) => {
  if (value !== form.value.password) callback(new Error("两次密码不一致"));
  else callback();
};

const rules = {
  email:    [{ required: true, type: "email", message: "请输入有效邮箱", trigger: "blur" }],
  username: [{ required: true, min: 2, message: "用户名至少 2 位", trigger: "blur" }],
  password: [
    { required: true, min: 8, message: "密码至少 8 位", trigger: "blur" },
    { validator: (r, v, cb) => /^\d+$/.test(v) ? cb(new Error("密码不能为纯数字")) : cb(), trigger: "blur" },
  ],
  confirm: [{ validator: validateConfirm, trigger: "blur" }],
};

async function handleRegister() {
  await formRef.value.validate();
  loading.value = true;
  try {
    await authAPI.register({
      email: form.value.email,
      username: form.value.username,
      password: form.value.password,
      password2: form.value.confirm,
    });
    ElMessage.success("注册成功，请登录");
    router.push("/login");
  } catch (e) {
    const data = e.response?.data;
    const msg  = data && typeof data === "object"
      ? Object.values(data).flat().join("；")
      : "注册失败，请重试";
    ElMessage.error(msg);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #050508;
  position: relative;
  overflow: hidden;
}
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  animation: orb-drift 12s ease-in-out infinite;
  pointer-events: none;
}
.orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(99,102,241,0.25) 0%, transparent 70%);
  top: -150px; right: -100px;
  animation-duration: 14s;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(139,92,246,0.2) 0%, transparent 70%);
  bottom: -100px; left: -100px;
  animation-duration: 10s;
  animation-delay: -4s;
}
.orb-3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(6,182,212,0.1) 0%, transparent 70%);
  top: 30%; right: 20%;
  animation-duration: 18s;
  animation-delay: -6s;
}
.auth-card {
  position: relative;
  z-index: 1;
  width: 460px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 24px;
  padding: 40px;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow:
    0 0 0 1px rgba(255,255,255,0.05) inset,
    0 32px 64px rgba(0,0,0,0.5),
    0 0 80px rgba(99,102,241,0.08);
  animation: fadeInUp 400ms cubic-bezier(0.4,0,0.2,1) forwards;
}
.auth-header { text-align: center; margin-bottom: 32px; }
.auth-logo {
  width: 52px; height: 52px;
  background: var(--brand-gradient);
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  margin: 0 auto 20px;
  box-shadow: 0 8px 24px rgba(99,102,241,0.4);
}
.auth-title {
  font-size: 24px; font-weight: 700;
  color: #f8fafc; margin: 0 0 8px;
  letter-spacing: -0.02em;
}
.auth-subtitle { font-size: 14px; color: #64748b; margin: 0; }

.auth-form :deep(.el-form-item__label) { color: #94a3b8 !important; font-size: 13px !important; font-weight: 500 !important; }
.auth-form :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.06) !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1) !important;
  border-radius: 10px !important;
  height: 44px;
}
.auth-form :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px rgba(255,255,255,0.2) !important; }
.auth-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 2px var(--brand-primary) !important; }
.auth-form :deep(.el-input__inner) { color: #f1f5f9 !important; font-size: 14px !important; }
.auth-form :deep(.el-input__inner::placeholder) { color: #475569 !important; }
.auth-form :deep(.el-input__prefix-icon) { color: #475569 !important; }
.auth-form :deep(.el-form-item) { margin-bottom: 20px; }
.field-label { font-size: 13px; font-weight: 500; color: #94a3b8; }

.submit-btn {
  width: 100%;
  height: 46px !important;
  font-size: 15px !important;
  font-weight: 600 !important;
  border-radius: 10px !important;
  margin-top: 8px;
}
.switch-link {
  text-align: center;
  margin-top: 24px;
  font-size: 13px;
  color: #475569;
}
.switch-action {
  color: var(--brand-primary-light);
  text-decoration: none;
  font-weight: 600;
  transition: color var(--transition-fast);
}
.switch-action:hover { color: #fff; text-decoration: underline; }
</style>
