<template>
  <!-- 生成张数选择器（OQ-4，AC-04-5）
       前端第二层约束：min=1 max=4（第一层为 Serializer，第三层为 DB CheckConstraint）
  -->
  <div class="batch-count-selector">
    <label class="field-label">生成张数</label>
    <el-input-number
      v-model="count"
      :min="1"
      :max="4"
      :step="1"
      :precision="0"
      controls-position="right"
      style="width: 100%"
      :disabled="disabled"
      @change="handleChange"
    />
    <span class="count-hint">每批次最多 4 张（AC-04-5）</span>
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

const count = ref(props.modelValue)

watch(
  () => props.modelValue,
  (val) => {
    count.value = val
  }
)

function handleChange(val) {
  // 前端双保险：确保不超出范围
  const safeVal = Math.max(1, Math.min(4, Math.floor(val || 1)))
  count.value = safeVal
  emit('update:modelValue', safeVal)
}
</script>

<style scoped>
.batch-count-selector {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.count-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
