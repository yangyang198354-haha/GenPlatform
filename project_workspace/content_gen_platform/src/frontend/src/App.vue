<template>
  <router-view />
</template>

<script setup>
import { onMounted } from "vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

onMounted(async () => {
  if (!authStore.accessToken) return;
  // Proactively refresh JWT if it has expired or will expire within 5 minutes
  try {
    const payload = JSON.parse(atob(authStore.accessToken.split('.')[1]));
    const expiresSoon = Date.now() / 1000 >= payload.exp - 300;
    if (expiresSoon) {
      await authStore.refreshToken();
    }
  } catch {
    // Malformed token — let the response interceptor handle 401
  }
  if (!authStore.user) {
    await authStore.fetchProfile();
  }
});
</script>
