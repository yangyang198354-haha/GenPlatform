<template>
  <!-- 模型选择下拉框（FR-1，AC-01-1）
       支持 doubao-seedream-5-0-260128 / 4.5 / 4.0，默认 4.5
       无即梦相关选项（OQ-1）
  -->
  <div class="model-selector">
    <label class="field-label">
      模型版本 <span class="required">*</span>
    </label>
    <el-select
      v-model="selectedModel"
      placeholder="请选择模型"
      :disabled="disabled"
      style="width: 100%"
      @change="handleChange"
    >
      <el-option
        v-for="m in MODEL_OPTIONS"
        :key="m.value"
        :label="m.label"
        :value="m.value"
      >
        <div class="model-option">
          <span class="model-name">{{ m.label }}</span>
          <span class="model-desc">{{ m.desc }}</span>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

// 支持的模型列表（与后端 ImageGenerationSubmitSerializer.SUPPORTED_MODELS 保持一致）
const MODEL_OPTIONS = [
  {
    value: 'doubao-seedream-5-0-260128',
    label: 'Seedream 5.0 Lite',
    desc: '速度优先，适合快速预览',
  },
  {
    value: 'doubao-seedream-4-5-251128',
    label: 'Seedream 4.5',
    desc: '质量与速度均衡（推荐）',
  },
  {
    value: 'doubao-seedream-4-0-250828',
    label: 'Seedream 4.0',
    desc: '标准版，适合精细调整',
  },
]

const props = defineProps({
  modelValue: {
    type: String,
    default: 'doubao-seedream-4-5-251128',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const selectedModel = ref(props.modelValue)

watch(
  () => props.modelValue,
  (val) => {
    selectedModel.value = val
  }
)

function handleChange(val) {
  emit('update:modelValue', val)
}
</script>

<style scoped>
.model-selector {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}

.required {
  color: var(--el-color-danger);
}

.model-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-name {
  font-size: 13px;
  font-weight: 500;
}

.model-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
