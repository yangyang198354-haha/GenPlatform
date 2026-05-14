<template>
  <!-- 图片尺寸选择器（v1.2 新增，FR-1.2，ADR-v1.2-01）
       支持三种输入方式：
         pixel  → 精确像素，从白名单下拉选择
         tier   → 档位（2K / 3K / 4K）
         ratio  → 比例（1:1 / 16:9 / 9:16 / 4:3 / 3:4）× 档位（2K / 3K / 4K）
  -->
  <div class="size-selector">
    <label class="field-label">图片尺寸</label>

    <!-- 模式切换 -->
    <el-radio-group
      v-model="localMode"
      size="small"
      class="mode-radio"
      :disabled="disabled"
    >
      <el-radio-button value="pixel">精确像素</el-radio-button>
      <el-radio-button value="tier">档位</el-radio-button>
      <el-radio-button value="ratio">比例</el-radio-button>
    </el-radio-group>

    <!-- pixel 模式：下拉选择枚举像素 -->
    <div v-if="localMode === 'pixel'" class="mode-content">
      <el-select
        v-model="localSize"
        placeholder="选择像素尺寸"
        style="width: 100%"
        :disabled="disabled"
      >
        <el-option
          v-for="opt in pixelOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>

    <!-- tier 模式：档位 Radio Group -->
    <div v-else-if="localMode === 'tier'" class="mode-content">
      <el-radio-group
        v-model="localTier"
        class="tier-radio"
        :disabled="disabled"
      >
        <el-radio-button value="2K">2K（约 4 MP）</el-radio-button>
        <el-radio-button value="3K">3K（约 9 MP）</el-radio-button>
        <el-radio-button value="4K">4K（约 17 MP）</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ratio 模式：比例 + 档位 -->
    <div v-else-if="localMode === 'ratio'" class="mode-content">
      <div class="ratio-section">
        <span class="sub-label">比例</span>
        <el-radio-group
          v-model="localRatio"
          class="ratio-radio"
          :disabled="disabled"
        >
          <el-radio-button value="1:1">1:1</el-radio-button>
          <el-radio-button value="16:9">16:9</el-radio-button>
          <el-radio-button value="9:16">9:16</el-radio-button>
          <el-radio-button value="4:3">4:3</el-radio-button>
          <el-radio-button value="3:4">3:4</el-radio-button>
        </el-radio-group>
      </div>
      <div class="tier-section">
        <span class="sub-label">分辨率档位</span>
        <el-radio-group
          v-model="localTier"
          class="tier-radio"
          :disabled="disabled"
        >
          <el-radio-button value="2K">2K</el-radio-button>
          <el-radio-button value="3K">3K</el-radio-button>
          <el-radio-button value="4K">4K</el-radio-button>
        </el-radio-group>
      </div>
      <div class="preview-hint">
        预计尺寸：<strong>{{ ratioPreview }}</strong>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

// ── 常量：与后端 size_normalizer.py 保持一致 ────────────────────────────────

const PIXEL_OPTIONS = [
  { value: '2048x2048', label: '2048×2048（1:1，4.2 MP）' },
  { value: '2880x1620', label: '2880×1620（16:9，4.7 MP）' },
  { value: '1620x2880', label: '1620×2880（9:16，4.7 MP）' },
  { value: '2880x2160', label: '2880×2160（4:3，6.2 MP）' },
  { value: '2160x2880', label: '2160×2880（3:4，6.2 MP）' },
  { value: '3072x3072', label: '3072×3072（1:1，9.4 MP）' },
  { value: '3840x2160', label: '3840×2160（16:9，8.3 MP）' },
  { value: '2160x3840', label: '2160×3840（9:16，8.3 MP）' },
  { value: '3072x2304', label: '3072×2304（4:3，7.1 MP）' },
  { value: '2304x3072', label: '2304×3072（3:4，7.1 MP）' },
  { value: '4096x4096', label: '4096×4096（1:1，16.8 MP）' },
  { value: '4096x2304', label: '4096×2304（16:9，9.4 MP）' },
  { value: '2304x4096', label: '2304×4096（9:16，9.4 MP）' },
  { value: '4096x3072', label: '4096×3072（4:3，12.6 MP）' },
  { value: '3072x4096', label: '3072×4096（3:4，12.6 MP）' },
]

// 比例 × 档位 → 像素（前端预览用，与后端 RATIO_TIER_MAP 同步）
const RATIO_TIER_MAP = {
  '1:1':  { '2K': '2048×2048', '3K': '3072×3072', '4K': '4096×4096' },
  '16:9': { '2K': '2880×1620', '3K': '3840×2160', '4K': '4096×2304' },
  '9:16': { '2K': '1620×2880', '3K': '2160×3840', '4K': '2304×4096' },
  '4:3':  { '2K': '2880×2160', '3K': '3072×2304', '4K': '4096×3072' },
  '3:4':  { '2K': '2160×2880', '3K': '2304×3072', '4K': '3072×4096' },
}

// ── Props / Emits ────────────────────────────────────────────────────────────

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({
      size_mode: 'pixel',
      size: '2048x2048',
      size_tier: '2K',
      size_ratio: '1:1',
    }),
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

// ── 本地状态 ─────────────────────────────────────────────────────────────────

const localMode  = ref(props.modelValue?.size_mode  || 'pixel')
const localSize  = ref(props.modelValue?.size        || '2048x2048')
const localTier  = ref(props.modelValue?.size_tier  || '2K')
const localRatio = ref(props.modelValue?.size_ratio || '1:1')

// ── 计算属性 ─────────────────────────────────────────────────────────────────

const pixelOptions = computed(() => PIXEL_OPTIONS)

const ratioPreview = computed(() => {
  const map = RATIO_TIER_MAP[localRatio.value]
  return map ? map[localTier.value] || '—' : '—'
})

// ── 向父组件同步 ─────────────────────────────────────────────────────────────

function emitValue() {
  emit('update:modelValue', {
    size_mode:  localMode.value,
    size:       localSize.value,
    size_tier:  localTier.value,
    size_ratio: localRatio.value,
  })
}

// 切换 mode 时重置子字段到默认值
watch(localMode, (newMode) => {
  if (newMode === 'pixel')  { localSize.value = '2048x2048' }
  if (newMode === 'tier')   { localTier.value = '2K' }
  if (newMode === 'ratio')  { localRatio.value = '1:1'; localTier.value = '2K' }
  emitValue()
})

watch(localSize,  () => emitValue())
watch(localTier,  () => emitValue())
watch(localRatio, () => emitValue())

// 响应外部 modelValue 变化
watch(
  () => props.modelValue,
  (val) => {
    if (!val) return
    if (val.size_mode  !== localMode.value)  localMode.value  = val.size_mode
    if (val.size       !== localSize.value)  localSize.value  = val.size
    if (val.size_tier  !== localTier.value)  localTier.value  = val.size_tier
    if (val.size_ratio !== localRatio.value) localRatio.value = val.size_ratio
  },
  { deep: true },
)
</script>

<style scoped>
.size-selector {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.mode-radio {
  display: flex;
  width: 100%;
}

.mode-radio :deep(.el-radio-button) {
  flex: 1;
}

.mode-radio :deep(.el-radio-button__inner) {
  width: 100%;
  text-align: center;
}

.mode-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tier-radio,
.ratio-radio {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ratio-section,
.tier-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.preview-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 4px 8px;
  background: var(--surface-base, #f0f4fa);
  border-radius: 6px;
}
</style>
