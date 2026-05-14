<template>
  <!-- 生成模式选择器（v1.2 新增，FR-1.4，FR-2.4）
       主图模式（n=1）和多图模式（n=2/3/4）切换，使用 Radio Group。
       替代原 BatchCountSelector 中的 Slider/InputNumber 控件。
  -->
  <div class="generation-mode-selector">
    <label class="field-label">生成模式</label>
    <el-radio-group
      v-model="localValue"
      class="mode-group"
      :disabled="disabled"
    >
      <el-radio-button :value="1">主图 ×1</el-radio-button>
      <el-radio-button :value="2">多图 ×2</el-radio-button>
      <el-radio-button :value="3">多图 ×3</el-radio-button>
      <el-radio-button :value="4">多图 ×4</el-radio-button>
    </el-radio-group>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Number,
    default: 1,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const localValue = ref(props.modelValue ?? 1)

watch(localValue, (val) => {
  emit('update:modelValue', val)
})

watch(
  () => props.modelValue,
  (val) => {
    if (val !== localValue.value) localValue.value = val
  },
)
</script>

<style scoped>
.generation-mode-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.mode-group {
  display: flex;
  width: 100%;
}

.mode-group :deep(.el-radio-button) {
  flex: 1;
}

.mode-group :deep(.el-radio-button__inner) {
  width: 100%;
  text-align: center;
  font-size: 13px;
}
</style>
