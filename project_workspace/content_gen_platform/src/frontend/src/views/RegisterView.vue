<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h2>注册账号</h2>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleRegister"
      >
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" type="email" placeholder="your@email.com" />
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少8位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="form.confirm" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            class="submit-btn"
          >
            注册
          </el-button>
        </el-form-item>
      </el-form>
      <p class="switch-link">
        已有账号？<router-link to="/login">去登录</router-link>
      </p>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { authAPI } from "@/api";

const router = useRouter();
const formRef = ref();
const loading = ref(false);
const form = ref({ email: "", username: "", password: "", confirm: "" });

const validateConfirm = (rule, value, callback) => {
  if (value !== form.value.password) callback(new Error("两次密码不一致"));
  else callback();
};

const rules = {
  email: [{ required: true, type: "email", message: "请输入有效邮箱", trigger: "blur" }],
  username: [{ required: true, min: 2, message: "用户名至少2位", trigger: "blur" }],
  password: [{ required: true, min: 8, message: "密码至少8位", trigger: "blur" }],
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
    });
    ElMessage.success("注册成功，请登录");
    router.push("/login");
  } catch (e) {
    ElMessage.error(e.response?.data?.email?.[0] || "注册失败，请重试");
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
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}
.auth-card {
  width: 420px;
}
.auth-card h2 {
  text-align: center;
  margin-bottom: 24px;
}
.submit-btn {
  width: 100%;
}
.switch-link {
  text-align: center;
  margin-top: 12px;
  color: #909399;
  font-size: 14px;
}
</style>
