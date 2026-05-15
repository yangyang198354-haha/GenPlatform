<template>
  <div class="llm-selector" data-testid="llm-selector">

    <!-- Warning banner: shown when backend falls back to whitelist for ≥1 provider -->
    <el-alert
      v-for="(warn, idx) in warnings"
      :key="idx"
      :title="warn"
      type="warning"
      :closable="false"
      show-icon
      class="llm-warning-banner"
      data-testid="llm-warning-banner"
    />

    <el-form-item :label="labelText" class="llm-form-item">
      <el-select
        v-model="selectedKey"
        :placeholder="placeholderText"
        :loading="isLoading"
        :disabled="disabled || noAvailableProviders"
        style="width: 100%"
        data-testid="llm-select"
        @change="onSelectionChange"
      >
        <!-- One option-group per provider, visible regardless of configured state
             so users know which services are available to configure. -->
        <el-option-group
          v-for="provider in providers"
          :key="provider.service_type"
          :label="provider.label"
          :data-testid="`llm-group-${provider.service_type}`"
        >
          <el-option
            v-for="m in provider.models"
            :key="`${provider.service_type}::${m.id}`"
            :value="`${provider.service_type}::${m.id}`"
            :label="`${provider.label} / ${m.label}`"
            :disabled="!provider.configured || !provider.last_test_ok"
            :data-testid="`llm-option-${provider.service_type}-${m.id}`"
          >
            <!-- Disabled options show a tooltip explaining why -->
            <el-tooltip
              v-if="!provider.configured || !provider.last_test_ok"
              :content="disabledTip(provider)"
              placement="right"
              effect="dark"
            >
              <span class="llm-option-disabled-wrap">
                {{ m.label }}
                <el-icon class="llm-disabled-icon"><WarningFilled /></el-icon>
              </span>
            </el-tooltip>
            <span v-else>{{ m.label }}</span>
          </el-option>
        </el-option-group>
      </el-select>

      <!-- Empty-state: no providers configured at all -->
      <div
        v-if="noAvailableProviders && !isLoading"
        class="llm-empty-state"
        data-testid="llm-empty-state"
      >
        <el-icon class="llm-empty-icon"><Setting /></el-icon>
        <span>请先在「设置」中配置 LLM 服务</span>
        <router-link to="/settings" class="llm-settings-link">前往设置</router-link>
      </div>
    </el-form-item>

  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { WarningFilled, Setting } from '@element-plus/icons-vue'
import { useLlmStore } from '@/stores/llm'

// ── Props ──────────────────────────────────────────────────────────────────
const props = defineProps({
  /**
   * v-model binding: { provider: string, model: string } | null
   */
  modelValue: {
    type: Object,
    default: null,
  },
  /**
   * When true the select is non-interactive (e.g. while generating content).
   */
  disabled: {
    type: Boolean,
    default: false,
  },
})

// ── Emits ──────────────────────────────────────────────────────────────────
const emit = defineEmits(['update:modelValue'])

// ── Store ──────────────────────────────────────────────────────────────────
const llmStore = useLlmStore()

// Expose store state as local computed refs for clarity inside template
const providers      = computed(() => llmStore.providers)
const warnings       = computed(() => llmStore.warnings)
const isLoading      = computed(() => llmStore.isLoading)
const noAvailableProviders = computed(() => llmStore.noAvailableProviders)

// ── Internal composite key ─────────────────────────────────────────────────
// el-select binds to a single string value: "{service_type}::{model_id}".
// This avoids managing two separate v-model bindings inside el-select.
const selectedKey = ref(null)

const labelText      = '选择 AI 模型'
const placeholderText = '请选择 AI 模型'

// ── Tooltip for disabled options ───────────────────────────────────────────
function disabledTip(provider) {
  if (!provider.configured) {
    return `请前往设置页配置 ${provider.label}`
  }
  return `${provider.label} 连接测试未通过，请前往设置页重新测试`
}

// ── Auto-select on providers load ─────────────────────────────────────────
/**
 * After providers are fetched, pick the best option in this priority order:
 *   1. user_preference (if the corresponding provider is configured & last_test_ok)
 *   2. system default (service_type + model from backend)
 *   3. null  →  emit null so parent disables the generate button
 */
function autoSelect() {
  if (llmStore.providers.length === 0) {
    // No providers at all – propagate null
    if (props.modelValue !== null) {
      emit('update:modelValue', null)
    }
    selectedKey.value = null
    return
  }

  // Helper: check if a given {service_type, model} combo is usable
  function isUsable(serviceType, model) {
    const p = llmStore.providers.find((p) => p.service_type === serviceType)
    if (!p || !p.configured || !p.last_test_ok) return false
    return p.models.some((m) => m.id === model)
  }

  let chosen = null

  // Priority 1 – user preference
  const pref = llmStore.userPreference
  if (pref && isUsable(pref.service_type, pref.model)) {
    chosen = { provider: pref.service_type, model: pref.model }
  }

  // Priority 2 – system default
  if (!chosen) {
    const def = llmStore.systemDefault
    if (def && isUsable(def.service_type, def.model)) {
      chosen = { provider: def.service_type, model: def.model }
    }
  }

  if (chosen) {
    selectedKey.value = `${chosen.provider}::${chosen.model}`
    emit('update:modelValue', chosen)
  } else {
    selectedKey.value = null
    emit('update:modelValue', null)
  }
}

// ── Handle user selection change ───────────────────────────────────────────
function onSelectionChange(key) {
  if (!key) {
    emit('update:modelValue', null)
    return
  }
  const [provider, model] = key.split('::')
  emit('update:modelValue', { provider, model })
}

// ── Sync selectedKey when parent programmatically changes modelValue ────────
watch(
  () => props.modelValue,
  (val) => {
    if (!val) {
      selectedKey.value = null
    } else {
      const key = `${val.provider}::${val.model}`
      if (selectedKey.value !== key) {
        selectedKey.value = key
      }
    }
  },
  { deep: true }
)

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(async () => {
  await llmStore.fetchProviders()
  autoSelect()
})

// Re-run auto-select if providers reload (force refresh from parent, etc.)
watch(
  () => llmStore.providers,
  () => {
    // Only auto-select when user has not already made a manual choice
    if (!props.modelValue) {
      autoSelect()
    }
  }
)
</script>

<style scoped>
.llm-selector {
  width: 100%;
}

.llm-warning-banner {
  margin-bottom: 8px;
  font-size: 13px;
}

.llm-form-item {
  margin-bottom: 0;
  width: 100%;
}

/* Disabled option inner layout */
.llm-option-disabled-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-disabled, #c0c4cc);
}
.llm-disabled-icon {
  font-size: 13px;
  color: var(--el-color-warning);
}

/* Empty state shown below the (disabled) select */
.llm-empty-state {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary, #909399);
}
.llm-empty-icon {
  font-size: 15px;
  color: var(--el-color-warning);
}
.llm-settings-link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 500;
}
.llm-settings-link:hover {
  text-decoration: underline;
}
</style>
