<template>
  <div class="auth-page">
    <!-- Animated background orbs -->
    <div class="orb orb-1" />
    <div class="orb orb-2" />
    <div class="orb orb-3" />

    <!-- Card -->
    <div class="auth-card">
      <!-- Header -->
      <div class="auth-header">
        <div class="auth-logo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
              stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h1 class="auth-title">欢迎回来</h1>
        <p class="auth-subtitle">登录你的内容生成平台账号</p>
      </div>

      <!-- Form -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="auth-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="email">
          <template #label><span class="field-label">邮箱地址</span></template>
          <el-input
            v-model="form.email"
            type="email"
            placeholder="your@email.com"
            size="large"
            :prefix-icon="Message"
          />
        </el-form-item>

        <el-form-item prop="password">
          <template #label>
            <span class="field-label">密码</span>
          </template>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="输入密码"
            size="large"
            :prefix-icon="Lock"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="loading"
          @click="handleLogin"
        >
          <span v-if="!loading">登录</span>
          <span v-else>验证中...</span>
        </el-button>
      </el-form>

      <p class="switch-link">
        还没有账号？
        <router-link to="/register" class="switch-action">立即注册</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Message, Lock } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";

const router    = useRouter();
const authStore = useAuthStore();

const formRef = ref();
const loading = ref(false);
const form    = ref({ email: "", password: "" });

const rules = {
  email:    [{ required: true, type: "email", message: "请输入有效邮箱", trigger: "blur" }],
  password: [{ required: true, min: 6, message: "密码至少 6 位", trigger: "blur" }],
};

async function handleLogin() {
  await formRef.value.validate();
  loading.value = true;
  try {
    await authStore.login(form.value.email, form.value.password);
    router.push("/workspace");
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "邮箱或密码错误，请重试");
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

/* Orbs */
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
  top: -150px; left: -150px;
  animation-duration: 14s;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(139,92,246,0.2) 0%, transparent 70%);
  bottom: -100px; right: -100px;
  animation-duration: 10s;
  animation-delay: -4s;
}
.orb-3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(236,72,153,0.12) 0%, transparent 70%);
  top: 40%; left: 60%;
  animation-duration: 16s;
  animation-delay: -8s;
}

/* Card */
.auth-card {
  position: relative;
  z-index: 1;
  width: 420px;
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

/* Header */
.auth-header { text-align: center; margin-bottom: 32px; }
.auth-logo {
  width: 52px; height: 52px;
  background: var(--brand-gradient);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin: 0 auto 20px;
  box-shadow: 0 8px 24px rgba(99,102,241,0.4);
}
.auth-title {
  font-size: 24px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}
.auth-subtitle {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

/* Form overrides for dark bg */
.auth-form :deep(.el-form-item__label) {
  color: #94a3b8 !important;
  font-size: 13px !important;
  font-weight: 500 !important;
}
.auth-form :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.06) !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1) !important;
  border-radius: 10px !important;
  height: 44px;
}
.auth-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(255,255,255,0.2) !important;
}
.auth-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--brand-primary) !important;
}
.auth-form :deep(.el-input__inner) {
  color: #f1f5f9 !important;
  font-size: 14px !important;
}
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
  letter-spacing: 0.02em;
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
