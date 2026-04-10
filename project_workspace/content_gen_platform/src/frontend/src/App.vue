<template>
  <router-view />
</template>

<script setup>
import { onMounted } from "vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

onMounted(async () => {
  // Only fetch profile if token exists but user data is not yet cached
  if (authStore.accessToken && !authStore.user) {
    await authStore.fetchProfile();
  }
});
</script>
