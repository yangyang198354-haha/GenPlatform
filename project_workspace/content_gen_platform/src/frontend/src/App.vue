<template>
  <router-view />
</template>

<script setup>
import { onMounted } from "vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

onMounted(async () => {
  if (authStore.accessToken) {
    await authStore.fetchProfile();
  }
});
</script>
