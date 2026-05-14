<template>
  <div class="doubao-image-key-panel">
    <!-- 引导文案（FR-6.2，US-08 AC-08-2）-->
    <el-alert
      type="info"
      :closable="false"
      class="guide-alert"
    >
      <template #default>
        豆包图片生成使用独立 API Key，以便单独管理配额和账单。
        若您已在"大语言模型 — 火山引擎"中配置了 Ark Key，可在此处填写相同的值。
      </template>
    </el-alert>

    <el-form
      ref="formRef"
      :model="form"
      label-width="120px"
      class="key-form"
      @submit.prevent="handleTestAndSave"
    >
      <!-- API Key 输入框（FR-6.1，密码掩码 + 切换显示）-->
      <el-form-item
        label="Ark API Key"
        prop="apiKey"
        :rules="[{ required: true, message: '请输入 API Key', trigger: 'blur' }]"
      >
        <el-input
          v-model="form.apiKey"
          type="password"
          show-password
          placeholder="请输入豆包图片生成 Ark API Key"
          :disabled="isTesting"
          clearable
          style="max-width: 480px"
        />
      </el-form-item>

      <!-- 当前配置状态提示 -->
      <el-form-item v-if="isConfigured" label="">
        <el-tag type="success" size="small">
          已配置
          <template v-if="lastValidatedAt">
            ，上次验证：{{ formatDate(lastValidatedAt) }}
          </template>
        </el-tag>
      </el-form-item>

      <!-- 操作区：仅"测试并保存"按钮（OQ-8=A，无独立保存按钮）-->
      <el-form-item label="">
        <el-button
          type="primary"
          :loading="isTesting"
          :disabled="!form.apiKey.trim()"
          @click="handleTestAndSave"
        >
          {{ isTesting ? '测试中...' : '测试并保存' }}
        </el-button>
        <span class="btn-hint">测试通过后自动保存</span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { settingsAPI } from '@/api'

// ── Props（FR-7.1：父组件传入初始配置状态）──────────────────────────────────
const props = defineProps({
  /** 初始是否已配置（来自 ServiceStatusView 查询结果） */
  initialConfigured: {
    type: Boolean,
    default: false,
  },
  /** 初始最后验证时间 */
  initialLastValidatedAt: {
    type: String,
    default: null,
  },
})

// ── Emits ────────────────────────────────────────────────────────────────────
// 测试成功且 Key 已保存后触发，通知父组件刷新状态（US-08 AC-08-4）
const emit = defineEmits(['configured'])

// ── 本地状态 ────────────────────────────────────────────────────────────────
const formRef = ref(null)
const form = ref({ apiKey: '' })
const isTesting = ref(false)
const isConfigured = ref(props.initialConfigured)
const lastValidatedAt = ref(props.initialLastValidatedAt)

// ── 错误码 → 中文提示映射（FR-7.2，US-08 AC-08-3）────────────────────────
const ERROR_MESSAGES = {
  ARK_KEY_INVALID:    'Key 无效或已吊销，请检查 Ark 控制台',
  ARK_QUOTA_EXCEEDED: '账号欠费或权限受限，请检查账户余额',
  ARK_UNREACHABLE:    'Ark 服务暂时不可达，请稍后重试',
}

// ── 方法：测试并保存（OQ-8=A，ADR-10）───────────────────────────────────────
async function handleTestAndSave() {
  if (!form.value.apiKey.trim()) return

  isTesting.value = true
  try {
    const { data } = await settingsAPI.testAndSaveServiceKey('doubao_image', form.value.apiKey)

    if (data.saved) {
      // 测试通过，Key 已原子保存
      isConfigured.value = true
      lastValidatedAt.value = data.last_validated_at
      // 清空输入框（安全：不在前端缓存 Key 内容）
      form.value.apiKey = ''
      ElMessage.success('连接成功，Key 已自动保存')
      // 通知父组件（US-08 AC-08-4：配置完成后 Banner 应消失）
      emit('configured')
    }
  } catch (err) {
    const errorCode = err.response?.data?.error
    const detail = err.response?.data?.detail
    // 优先使用后端 detail，fallback 到前端映射，再 fallback 到通用提示
    const message =
      detail ||
      ERROR_MESSAGES[errorCode] ||
      '测试失败，请稍后重试'
    ElMessage.error(message)
  } finally {
    isTesting.value = false
  }
}

// ── 工具函数：格式化 ISO 日期字符串为本地日期 ────────────────────────────────
function formatDate(isoStr) {
  if (!isoStr) return ''
  try {
    return new Date(isoStr).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}
</script>

<style scoped>
.doubao-image-key-panel {
  max-width: 600px;
}

.guide-alert {
  margin-bottom: 24px;
}

.key-form {
  margin-top: 8px;
}

.btn-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
