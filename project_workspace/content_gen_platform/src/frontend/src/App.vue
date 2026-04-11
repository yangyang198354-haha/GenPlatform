<template>
  <router-view />
</template>

<script setup>
import { onMounted } from "vue";
import { useAuthStore } from "@/stores/auth";
import { ensureTokenRefreshed } from "@/api";

const authStore = useAuthStore();

onMounted(async () => {
  if (!authStore.accessToken) return;
  // Proactively refresh JWT if it has expired or will expire within 5 minutes.
  // Use ensureTokenRefreshed() so this shares the same mutex as the response
  // interceptor — prevents a double-refresh race if API calls are already
  // in-flight when the page mounts.
  try {
    const payload = JSON.parse(atob(authStore.accessToken.split('.')[1]));
    const expiresSoon = Date.now() / 1000 >= payload.exp - 300;
    if (expiresSoon) {
      await ensureTokenRefreshed(authStore);
    }
  } catch {
    // Malformed token — let the response interceptor handle 401
  }
  if (!authStore.user) {
    await authStore.fetchProfile();
  }
});
</script>
