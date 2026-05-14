<template>
  <!-- 高级参数折叠面板（OQ-2，AC-01-3，AC-02-2）
       默认收起，用户点击展开后显示 seed / negative_prompt / guidance_scale / steps / watermark
       以 el-collapse 实现，无即梦相关参数
  -->
  <div class="advanced-params-panel">
    <el-collapse v-model="activePanel" class="params-collapse">
      <el-collapse-item name="advanced" class="collapse-item">
        <template #title>
          <span class="collapse-title">高级选项</span>
          <el-tag
            v-if="hasAdvancedParams"
            type="info"
            size="small"
            class="params-tag"
          >已设置</el-tag>
        </template>

        <div class="params-grid">
          <!-- seed：随机种子 -->
          <div class="param-item">
            <label class="param-label">随机种子 (seed)</label>
            <el-input-number
              v-model="params.seed"
              :min="0"
              :max="2147483647"
              :step="1"
              placeholder="留空则随机"
              controls-position="right"
              style="width: 100%"
              :disabled="disabled"
            />
            <span class="param-hint">固定种子可复现相同结果</span>
          </div>

          <!-- negative_prompt：负向提示词 -->
          <div class="param-item param-item--full">
            <label class="param-label">负向提示词 (negative_prompt)</label>
            <el-input
              v-model="params.negative_prompt"
              type="textarea"
              :rows="2"
              placeholder="描述不希望出现的内容，如：模糊、变形、低质量"
              :disabled="disabled"
            />
          </div>

          <!-- guidance_scale：CFG Scale -->
          <div class="param-item">
            <label class="param-label">引导强度 (guidance_scale)</label>
            <el-slider
              v-model="params.guidance_scale"
              :min="1"
              :max="20"
              :step="0.5"
              show-input
              :disabled="disabled"
            />
            <span class="param-hint">默认 7.5，越高越贴近提示词</span>
          </div>

          <!-- steps：推理步数（4.0 / 4.5 支持，5.0-lite 忽略） -->
          <div class="param-item" v-if="modelSupportsSteps">
            <label class="param-label">推理步数 (steps)</label>
            <el-input-number
              v-model="params.steps"
              :min="10"
              :max="100"
              :step="5"
              placeholder="默认"
              controls-position="right"
              style="width: 100%"
              :disabled="disabled"
            />
            <span class="param-hint">步数越高质量越好，耗时越长</span>
          </div>

          <!-- watermark：水印 -->
          <div class="param-item param-item--inline">
            <label class="param-label">添加水印 (watermark)</label>
            <el-switch v-model="params.watermark" :disabled="disabled" />
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({}),
  },
  selectedModel: {
    type: String,
    default: 'doubao-seedream-4-5-251128',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

// 折叠面板默认收起（OQ-2 要求）
const activePanel = ref([])

const params = ref({
  seed: null,
  negative_prompt: '',
  guidance_scale: 7.5,
  steps: null,
  watermark: false,
  ...props.modelValue,
})

// 5.0-lite 不支持 steps（ADR-05）
const modelSupportsSteps = computed(() => {
  return props.selectedModel !== 'doubao-seedream-5-0-260128'
})

// 判断是否设置了任何非默认值
const hasAdvancedParams = computed(() => {
  return (
    params.value.seed !== null ||
    (params.value.negative_prompt && params.value.negative_prompt.trim()) ||
    params.value.guidance_scale !== 7.5 ||
    params.value.steps !== null ||
    params.value.watermark === true
  )
})

// 向父组件同步高级参数
watch(
  params,
  (val) => {
    emit('update:modelValue', { ...val })
  },
  { deep: true }
)

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      Object.assign(params.value, val)
    }
  },
  { deep: true }
)
</script>

<style scoped>
.advanced-params-panel {
  margin-top: 4px;
}

.params-collapse {
  border: none;
}

.params-collapse :deep(.el-collapse-item__header) {
  background: transparent;
  border-bottom: none;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  padding: 8px 0;
  height: auto;
  line-height: 1.4;
}

.params-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}

.params-collapse :deep(.el-collapse-item__content) {
  padding-top: 12px;
  padding-bottom: 0;
}

.collapse-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-color-primary);
}

.params-tag {
  margin-left: 8px;
}

.params-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.param-item--full {
  grid-column: span 2;
}

.param-item--inline {
  display: flex;
  align-items: center;
  gap: 12px;
}

.param-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin-bottom: 6px;
}

.param-hint {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}
</style>
