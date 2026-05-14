<template>
  <!--
    预检 Banner：当豆包图片生成 API Key 未配置时常驻显示。
    由父组件 ImageGeneratorView 通过 v-if="!doubaoIsConfigured" 控制渲染，
    Banner 本身无关闭逻辑（OQ-7=A：常驻显示）。

    关联需求：FR-7.1、US-08 AC-08-1/AC-08-2、OQ-7=A
    关联 ADR：ADR-09（is_configured 来源）
  -->
  <el-alert
    type="warning"
    :closable="false"
    class="preflight-banner"
    show-icon
  >
    <template #default>
      <span class="banner-text">
        未配置豆包图片生成 API Key，无法发起生成。
      </span>
      <el-button
        type="warning"
        size="small"
        plain
        class="banner-btn"
        @click="goToSettings"
      >
        前往配置
      </el-button>
    </template>
  </el-alert>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

/**
 * 跳转到设置页并自动激活"豆包图片生成"Tab。
 * 使用 query 参数 ?tab=doubao_image，SettingsView 会在 onMounted 时读取并激活对应 Tab。
 * 关联需求：FR-7.1、US-08 AC-08-2
 */
function goToSettings() {
  router.push({ path: '/settings', query: { tab: 'doubao_image' } })
}
</script>

<style scoped>
.preflight-banner {
  margin-bottom: 16px;
}

.banner-text {
  margin-right: 12px;
  font-size: 14px;
}

.banner-btn {
  vertical-align: middle;
}
</style>
