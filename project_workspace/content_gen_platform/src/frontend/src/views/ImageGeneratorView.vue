<template>
  <div class="image-generator-view">
    <div class="page-header">
      <h2>AI 图片生成</h2>
      <span class="page-subtitle">使用豆包 Seedream 系列模型根据文字描述生成图片</span>
    </div>

    <!-- 预检 Banner：API Key 未配置时常驻显示（FR-7.1，OQ-7=A，US-08 AC-08-1）-->
    <!-- v-if 控制渲染：is_configured=false 时显示，true 时不渲染（无关闭按钮需求）-->
    <PreflightBanner v-if="!doubaoIsConfigured" />

    <!-- Tab 页：生成 / 批次管理 -->
    <el-tabs v-model="activeTab" class="main-tabs">
      <!-- Tab 1：图片生成 -->
      <el-tab-pane label="生成图片" name="generate">
        <div class="generator-layout">
          <!-- 左侧面板：输入设置 -->
          <div class="input-panel">
            <el-card class="input-card" shadow="never">
              <template #header>
                <span class="card-title">生成设置</span>
              </template>

              <!-- 提示词输入 -->
              <div class="form-section">
                <label class="field-label">描述提示词 <span class="required">*</span></label>
                <el-input
                  v-model="prompt"
                  type="textarea"
                  :rows="4"
                  :maxlength="500"
                  show-word-limit
                  placeholder="请描述您想生成的图片内容，如：日落时分的海边灯塔，油画风格..."
                  :disabled="isGenerating"
                />
              </div>

              <!-- 模型选择（FR-1，AC-01-1）-->
              <div class="form-section">
                <ModelSelector
                  v-model="selectedModel"
                  :disabled="isGenerating"
                />
              </div>

              <!-- 生成模式切换（v1.2，FR-1.4，FR-2.4）-->
              <div class="form-section">
                <GenerationModeSelector
                  v-model="batchCount"
                  :disabled="isGenerating"
                />
              </div>

              <!-- 图片尺寸（v1.2，FR-1.2，ADR-v1.2-01）-->
              <div class="form-section">
                <SizeSelector
                  v-model="sizeValue"
                  :disabled="isGenerating"
                />
              </div>

              <!-- 参考图上传（FR-3）-->
              <div class="form-section">
                <label class="field-label">参考图片（可选，图生图）</label>
                <div
                  class="upload-zone"
                  :class="{
                    'upload-zone--dragging': isDragging,
                    'upload-zone--filled': refImagePreview,
                  }"
                  @dragover.prevent="isDragging = true"
                  @dragleave.prevent="isDragging = false"
                  @drop.prevent="handleDrop"
                  @click="triggerFileInput"
                >
                  <template v-if="refImagePreview">
                    <img :src="refImagePreview" class="ref-preview" alt="参考图片预览" />
                    <div class="preview-overlay">
                      <el-button
                        circle
                        type="danger"
                        :icon="Delete"
                        size="small"
                        @click.stop="clearRefImage"
                      />
                    </div>
                  </template>
                  <template v-else>
                    <el-icon class="upload-icon"><Upload /></el-icon>
                    <p class="upload-hint">点击或拖拽上传参考图片</p>
                    <p class="upload-hint upload-hint--small">支持 JPG / PNG，最大 10 MB</p>
                  </template>
                </div>
                <input
                  ref="fileInputRef"
                  type="file"
                  accept="image/jpeg,image/png"
                  style="display: none"
                  @change="handleFileSelect"
                />
              </div>

              <!-- 高级参数折叠面板（OQ-2，AC-01-3）-->
              <div class="form-section">
                <AdvancedParamsPanel
                  v-model="advancedParams"
                  :selected-model="selectedModel"
                  :disabled="isGenerating"
                />
              </div>

              <!-- 提交按钮 -->
              <el-button
                type="primary"
                size="large"
                class="generate-btn"
                :loading="isGenerating"
                :disabled="!prompt.trim() || isGenerating"
                @click="submitGeneration"
              >
                {{ isGenerating ? '生成中...' : '开始生成' }}
              </el-button>
            </el-card>
          </div>

          <!-- 右侧面板：生成结果 -->
          <div class="result-panel">
            <el-card class="result-card" shadow="never">
              <template #header>
                <div class="result-header">
                  <span class="card-title">生成结果</span>
                  <span v-if="currentBatch" class="batch-name-tag">
                    <el-tag type="info" size="small">{{ currentBatch.batch_name }}</el-tag>
                  </span>
                </div>
              </template>

              <!-- 空闲状态 -->
              <div v-if="!currentBatch && !isGenerating" class="result-empty">
                <el-icon class="result-empty-icon"><Picture /></el-icon>
                <p>输入提示词后点击「开始生成」</p>
              </div>

              <!-- 生成中 -->
              <div v-else-if="isGenerating" class="result-progress">
                <div class="progress-animation">
                  <el-icon class="spinning-icon"><Loading /></el-icon>
                </div>
                <p class="progress-text">AI 正在创作您的图片...</p>
                <el-progress
                  :percentage="batchProgress"
                  :stroke-width="8"
                  status="active"
                  class="progress-bar"
                />
                <p class="progress-hint">
                  已完成 {{ completedImages.length }} / {{ currentBatch?.total_count || batchCount }} 张
                </p>
              </div>

              <!-- 结果图片网格（批次内多张，AC-04-2）-->
              <div v-else-if="completedImages.length > 0" class="result-grid">
                <div
                  v-for="img in completedImages"
                  :key="img.request_id"
                  class="result-image-item"
                >
                  <img :src="img.file_url" class="result-image" :alt="`生成图片 #${img.request_id}`" />
                  <div class="image-actions">
                    <el-button
                      size="small"
                      :icon="Download"
                      @click="downloadImage(img.file_url)"
                    >下载</el-button>
                  </div>
                </div>
              </div>

              <!-- 失败 -->
              <div v-else-if="generationError" class="result-error">
                <el-icon class="error-icon"><CircleClose /></el-icon>
                <p class="error-text">生成失败：{{ generationError }}</p>
                <el-button @click="resetGeneration">重试</el-button>
              </div>
            </el-card>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2：批次管理（US-05，AC-05-1）-->
      <el-tab-pane label="批次管理" name="batches">
        <BatchListPage />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  Upload, Delete, Picture, Loading, Download, CircleClose,
} from '@element-plus/icons-vue'
import { imageAPI, settingsAPI } from '@/api'
import { useAuthStore } from '@/stores/auth'
import ModelSelector from '@/components/ImageGenerator/ModelSelector.vue'
import AdvancedParamsPanel from '@/components/ImageGenerator/AdvancedParamsPanel.vue'
import GenerationModeSelector from '@/components/ImageGenerator/GenerationModeSelector.vue'
import SizeSelector from '@/components/ImageGenerator/SizeSelector.vue'
import BatchListPage from '@/views/ImageGeneratorView/BatchListPage.vue'
import PreflightBanner from '@/components/ImageGenerator/PreflightBanner.vue'

const auth = useAuthStore()
const router = useRouter()

// Tab 状态
const activeTab = ref('generate')

// 表单状态
const prompt = ref('')
const selectedModel = ref('doubao-seedream-4-5-251128')
const batchCount = ref(1)
const advancedParams = ref({})
// v1.2：尺寸三模式（SizeSelector 绑定值）
const sizeValue = ref({
  size_mode:  'pixel',
  size:       '2048x2048',
  size_tier:  '2K',
  size_ratio: '1:1',
})
const refImageFile = ref(null)
const refImagePreview = ref('')
const isDragging = ref(false)
const fileInputRef = ref(null)

// 生成状态
const isGenerating = ref(false)
const currentBatch = ref(null)   // 当前批次信息（batch_id / batch_name / total_count）
const completedImages = ref([])  // 已完成的图片列表 [{request_id, file_url}]
const generationError = ref('')

// 预检状态：doubao_image API Key 是否已配置（FR-7.1，US-08 AC-08-1）
const doubaoIsConfigured = ref(true)  // 默认 true，避免首次加载时闪烁

// WebSocket
let ws = null

const batchProgress = computed(() => {
  if (!currentBatch.value) return 0
  return Math.round((completedImages.value.length / (currentBatch.value.total_count || 1)) * 100)
})

onMounted(async () => {
  connectWebSocket()
  await fetchDoubaoStatus()
})

// 从设置页返回时由 onMounted 触发刷新（AppLayout 未启用 keep-alive，组件每次进入都重新挂载）。
// US-08 AC-08-4 验收：用户配置 Key 成功 → 返回 /image-generator → onMounted → fetchDoubaoStatus → Banner 消失。

onUnmounted(() => {
  if (ws) ws.close()
})

/**
 * 查询 doubao_image 服务配置状态（FR-7.1，ADR-09）。
 * 成功：根据 is_configured 控制 PreflightBanner 的显隐。
 * 失败：保守处理，doubaoIsConfigured=true（不误显示 Banner）。
 */
const fetchDoubaoStatus = async () => {
  try {
    const { data } = await settingsAPI.getServiceStatus('doubao_image')
    doubaoIsConfigured.value = data.is_configured
  } catch (_) {
    // 网络错误等异常：保守处理，不显示 Banner（避免误报）
    doubaoIsConfigured.value = true
  }
}

const connectWebSocket = () => {
  const token = auth.accessToken
  const wsUrl = token
    ? `ws://${location.host}/ws/notifications/?token=${token}`
    : `ws://${location.host}/ws/notifications/`
  ws = new WebSocket(wsUrl)
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    handleWebSocketMessage(msg)
  }
  ws.onerror = () => {
    // WebSocket 不可用时，依赖轮询状态接口（NFR-2）
  }
}

const handleWebSocketMessage = (msg) => {
  const { event_type, payload } = msg

  if (!currentBatch.value) return
  if (payload.batch_id !== currentBatch.value.batch_id) return

  if (event_type === 'batch_progress') {
    // 批次开始处理
  }

  if (event_type === 'image_completed') {
    // 单张图片完成（AC-03-4）
    completedImages.value.push({
      request_id: payload.request_id,
      file_url: payload.file_url,
      media_item_id: payload.media_item_id,
    })
    ElMessage.success(`第 ${completedImages.value.length} 张图片已生成`)
  }

  if (event_type === 'image_failed') {
    generationError.value = payload.error || '图片生成失败'
    ElMessage.error(`图片生成失败：${payload.error}`)
  }

  if (event_type === 'batch_completed') {
    isGenerating.value = false
    const { status } = payload
    if (status === 'completed') {
      ElMessage.success(`${completedImages.value.length} 张图片已全部生成完成，已自动保存到素材库！`)
    } else if (status === 'partial_failed') {
      ElMessage.warning(`批次部分完成：${completedImages.value.length} 张成功，请检查失败原因`)
    } else {
      isGenerating.value = false
      generationError.value = '所有图片生成失败，请稍后重试'
    }
  }
}

const triggerFileInput = () => {
  if (!isGenerating.value) fileInputRef.value?.click()
}

const handleFileSelect = (event) => {
  const file = event.target.files?.[0]
  if (file) loadRefImage(file)
}

const handleDrop = (event) => {
  isDragging.value = false
  const file = event.dataTransfer.files?.[0]
  if (file) loadRefImage(file)
}

const loadRefImage = (file) => {
  if (!['image/jpeg', 'image/png'].includes(file.type)) {
    ElMessage.error('仅支持 JPG 和 PNG 格式（AC-02-3）')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 10 MB（AC-02-4）')
    return
  }
  refImageFile.value = file
  const reader = new FileReader()
  reader.onload = (e) => { refImagePreview.value = e.target.result }
  reader.readAsDataURL(file)
}

const clearRefImage = () => {
  refImageFile.value = null
  refImagePreview.value = ''
  if (fileInputRef.value) fileInputRef.value.value = ''
}

const submitGeneration = async () => {
  if (!prompt.value.trim()) return

  // 前端二层校验：张数上限（前端第二层防护，OQ-4）
  if (batchCount.value > 4) {
    ElMessage.error('每批次最多生成 4 张图片')
    return
  }

  isGenerating.value = true
  completedImages.value = []
  generationError.value = ''
  currentBatch.value = null

  const formData = new FormData()
  formData.append('prompt', prompt.value.trim())
  formData.append('model', selectedModel.value)
  formData.append('n', String(batchCount.value))

  // v1.2：尺寸三模式参数（SizeSelector，FR-1.2）
  const sv = sizeValue.value
  formData.append('size_mode', sv.size_mode)
  if (sv.size_mode === 'pixel')  formData.append('size', sv.size)
  if (sv.size_mode === 'tier')   formData.append('size_tier', sv.size_tier)
  if (sv.size_mode === 'ratio') {
    formData.append('size_ratio', sv.size_ratio)
    formData.append('size_tier', sv.size_tier)
  }

  // 高级参数（折叠面板传入，非空才追加）
  const ap = advancedParams.value
  if (ap.seed !== null && ap.seed !== undefined) formData.append('seed', String(ap.seed))
  if (ap.negative_prompt) formData.append('negative_prompt', ap.negative_prompt)
  if (ap.guidance_scale !== null && ap.guidance_scale !== undefined) {
    formData.append('guidance_scale', String(ap.guidance_scale))
  }
  if (ap.steps !== null && ap.steps !== undefined) formData.append('steps', String(ap.steps))
  if (ap.watermark) formData.append('watermark', 'true')

  // 参考图（图生图）
  if (refImageFile.value) {
    formData.append('ref_image', refImageFile.value)
  }

  try {
    const { data } = await imageAPI.generate(formData)
    currentBatch.value = {
      batch_id: data.batch_id,
      batch_name: data.batch_name,
      total_count: data.total_count,
    }
  } catch (err) {
    isGenerating.value = false
    const errorCode = err.response?.data?.error || ''
    const errMsg = err.response?.data?.detail || err.response?.data?.error || '提交失败，请检查豆包 API Key 是否已配置'

    // ARK_KEY_INVALID 或未配置类错误：提供"前往配置"可点击提示（FR-7.2，US-08 AC-08-3）
    const isKeyError = ['ARK_KEY_INVALID', 'DOUBAO_IMAGE_NOT_CONFIGURED'].includes(errorCode) ||
      errMsg.includes('未配置') || errMsg.includes('API Key')
    if (isKeyError) {
      ElMessageBox.confirm(
        errMsg + '\n\n是否立即前往设置页配置 API Key？',
        '豆包图片生成 Key 未配置',
        {
          confirmButtonText: '前往配置',
          cancelButtonText: '稍后再说',
          type: 'warning',
        }
      ).then(() => {
        router.push({ path: '/settings', query: { tab: 'doubao_image' } })
      }).catch(() => {/* 用户选择稍后，忽略 */})
    } else {
      ElMessage.error(errMsg)
    }

    generationError.value = errMsg
  }
}

const resetGeneration = () => {
  currentBatch.value = null
  completedImages.value = []
  generationError.value = ''
  isGenerating.value = false
}

const downloadImage = (url) => {
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = `ai_image_${Date.now()}.jpg`
  a.click()
}
</script>

<style scoped>
.image-generator-view {
  padding: 0;
}

.page-header {
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.page-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.main-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.generator-layout {
  display: grid;
  grid-template-columns: 480px 1fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 1100px) {
  .generator-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .generator-layout {
    grid-template-columns: 1fr;
  }
}

.input-card,
.result-card {
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--el-border-color-lighter);
}

.card-title {
  font-weight: 600;
  font-size: 14px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.batch-name-tag {
  flex: 1;
}

.form-section {
  margin-bottom: 16px;
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

/* 参考图上传区 */
.upload-zone {
  border: 2px dashed var(--el-border-color);
  border-radius: var(--radius-lg, 14px);
  height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
  background: var(--surface-base, #f0f4fa);
}

.upload-zone:hover,
.upload-zone--dragging {
  border-color: var(--brand-primary, #6366f1);
  background: rgba(99, 102, 241, 0.04);
}

.upload-zone--filled {
  border-style: solid;
  border-color: var(--el-border-color-lighter);
}

.upload-icon {
  font-size: 24px;
  color: var(--el-text-color-placeholder);
  margin-bottom: 6px;
}

.upload-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 2px 0;
}

.upload-hint--small {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.ref-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-overlay {
  position: absolute;
  top: 6px;
  right: 6px;
}

.generate-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  background: var(--brand-primary, #6366f1);
  border-color: var(--brand-primary, #6366f1);
}

/* 结果区 */
.result-card {
  min-height: 400px;
}

.result-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  color: var(--el-text-color-placeholder);
}

.result-empty-icon {
  font-size: 56px;
  margin-bottom: 12px;
}

.result-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 40px;
}

.spinning-icon {
  font-size: 48px;
  color: var(--brand-primary, #6366f1);
  animation: spin 1.5s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.progress-text {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 16px;
}

.progress-bar {
  width: 100%;
  max-width: 360px;
  margin-bottom: 8px;
}

.progress-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* 结果图片网格 */
.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 8px 0;
}

.result-image-item {
  position: relative;
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.result-image {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}

.image-actions {
  position: absolute;
  bottom: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.result-image-item:hover .image-actions {
  opacity: 1;
}

.result-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 40px;
  color: var(--el-color-danger);
}

.error-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.error-text {
  font-size: 14px;
  margin-bottom: 16px;
  text-align: center;
}
</style>
