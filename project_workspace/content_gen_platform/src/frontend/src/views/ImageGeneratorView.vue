<template>
  <div class="image-generator-view">
    <div class="page-header">
      <h2>AI 图片生成</h2>
      <span class="page-subtitle">使用即梦（即创）AI 根据文字描述生成图片</span>
    </div>

    <div class="generator-layout">
      <!-- Left Panel: Input -->
      <div class="input-panel">
        <el-card class="input-card" shadow="never">
          <template #header>
            <span class="card-title">生成设置</span>
          </template>

          <!-- Prompt Input -->
          <div class="form-section">
            <label class="field-label">描述提示词 <span class="required">*</span></label>
            <el-input
              v-model="prompt"
              type="textarea"
              :rows="5"
              :maxlength="500"
              show-word-limit
              placeholder="请用英文描述您想生成的图片内容，例如：A serene mountain landscape at golden hour, oil painting style..."
              :disabled="isGenerating"
            />
          </div>

          <!-- Reference Image Upload -->
          <div class="form-section">
            <label class="field-label">参考图片（可选）</label>
            <div
              class="upload-zone"
              :class="{ 'upload-zone--dragging': isDragging, 'upload-zone--filled': refImagePreview }"
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

          <!-- Generate Button -->
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

        <!-- History List -->
        <el-card class="history-card" shadow="never" v-if="history.length">
          <template #header>
            <span class="card-title">历史记录</span>
          </template>
          <div class="history-list">
            <div
              v-for="item in history"
              :key="item.id"
              class="history-item"
              :class="{ 'history-item--active': activeRequestId === item.id }"
              @click="selectHistoryItem(item)"
            >
              <el-tag :type="statusTagType(item.status)" size="small">{{ statusLabel(item.status) }}</el-tag>
              <span class="history-prompt">{{ item.prompt }}</span>
              <span class="history-time">{{ formatTime(item.created_at) }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <!-- Right Panel: Result -->
      <div class="result-panel">
        <el-card class="result-card" shadow="never">
          <template #header>
            <span class="card-title">生成结果</span>
          </template>

          <!-- Idle state -->
          <div v-if="!activeRequestId && !isGenerating" class="result-empty">
            <el-icon class="result-empty-icon"><Picture /></el-icon>
            <p>输入提示词后点击「开始生成」</p>
          </div>

          <!-- In Progress -->
          <div v-else-if="isGenerating || currentRequest?.status === 'processing'" class="result-progress">
            <div class="progress-animation">
              <el-icon class="spinning-icon"><Loading /></el-icon>
            </div>
            <p class="progress-text">AI 正在创作您的图片...</p>
            <el-progress
              :percentage="currentProgress"
              :stroke-width="8"
              status="active"
              class="progress-bar"
            />
            <p class="progress-hint">生成通常需要 10-60 秒，请耐心等待</p>
          </div>

          <!-- Result Image -->
          <div v-else-if="resultImageUrl" class="result-image-container">
            <img :src="resultImageUrl" class="result-image" alt="AI 生成图片" />
            <div class="result-actions">
              <el-button type="primary" :icon="Download" @click="downloadImage">
                下载图片
              </el-button>
              <el-button type="success" :icon="Check" @click="showSavedSuccess" v-if="resultSavedToLibrary">
                已保存到素材库
              </el-button>
            </div>
          </div>

          <!-- Failed -->
          <div v-else-if="currentRequest?.status === 'failed'" class="result-error">
            <el-icon class="error-icon"><CircleClose /></el-icon>
            <p class="error-text">生成失败：{{ currentRequest.error_message || '未知错误' }}</p>
            <el-button @click="retryGeneration">重试</el-button>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, Delete, Picture, Loading, Download, Check, CircleClose
} from '@element-plus/icons-vue'
import { imageAPI } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

// Form state
const prompt = ref('')
const refImageFile = ref(null)
const refImagePreview = ref('')
const isDragging = ref(false)
const fileInputRef = ref(null)

// Generation state
const isGenerating = ref(false)
const currentProgress = ref(0)
const activeRequestId = ref(null)
const currentRequest = ref(null)
const resultImageUrl = ref('')
const resultSavedToLibrary = ref(false)
const history = ref([])

// WebSocket
let ws = null
let pollTimer = null

onMounted(async () => {
  await loadHistory()
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) ws.close()
  if (pollTimer) clearInterval(pollTimer)
})

const loadHistory = async () => {
  try {
    const { data } = await imageAPI.getHistory()
    history.value = data
  } catch {
    // ignore
  }
}

const connectWebSocket = () => {
  ws = new WebSocket(`ws://${location.host}/ws/notifications/`)
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.event_type === 'image_progress' && msg.payload.request_id === activeRequestId.value) {
      currentProgress.value = msg.payload.progress || 0
    }
    if (msg.event_type === 'image_completed' && msg.payload.request_id === activeRequestId.value) {
      handleGenerationComplete(msg.payload)
    }
    if (msg.event_type === 'image_failed' && msg.payload.request_id === activeRequestId.value) {
      handleGenerationFailed(msg.payload.error)
    }
  }
  ws.onerror = () => {
    // Fall back to polling if WebSocket unavailable
    startPolling()
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
    ElMessage.error('仅支持 JPG 和 PNG 格式')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 10 MB')
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

  isGenerating.value = true
  currentProgress.value = 0
  resultImageUrl.value = ''
  resultSavedToLibrary.value = false

  const formData = new FormData()
  formData.append('prompt', prompt.value.trim())
  if (refImageFile.value) {
    formData.append('ref_image', refImageFile.value)
  }

  try {
    const { data } = await imageAPI.generate(formData)
    activeRequestId.value = data.id
    currentRequest.value = data
    await loadHistory()
    startPolling()
  } catch (err) {
    isGenerating.value = false
    const msg = err.response?.data?.error || '提交失败，请检查即梦 API Key 是否已配置'
    ElMessage.error(msg)
  }
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  if (!activeRequestId.value) return

  pollTimer = setInterval(async () => {
    try {
      const { data } = await imageAPI.getStatus(activeRequestId.value)
      currentRequest.value = data
      currentProgress.value = data.progress || 0

      if (data.status === 'completed') {
        clearInterval(pollTimer)
        handleGenerationComplete({ media_item_id: data.media_item_id })
      } else if (data.status === 'failed') {
        clearInterval(pollTimer)
        handleGenerationFailed(data.error_message)
      }
    } catch {
      clearInterval(pollTimer)
    }
  }, 5000)
}

const handleGenerationComplete = async (payload) => {
  isGenerating.value = false
  currentProgress.value = 100
  resultSavedToLibrary.value = true

  // Fetch the actual file URL from media API
  if (payload.file_url) {
    resultImageUrl.value = payload.file_url
  } else if (payload.media_item_id) {
    try {
      const { data } = await imageAPI.getStatus(activeRequestId.value)
      currentRequest.value = data
    } catch { /* ignore */ }
  }

  ElMessage.success('图片生成完成，已自动保存到素材库！')
  await loadHistory()
}

const handleGenerationFailed = (error) => {
  isGenerating.value = false
  ElMessage.error(`生成失败：${error || '未知错误'}`)
  if (pollTimer) clearInterval(pollTimer)
}

const downloadImage = () => {
  if (!resultImageUrl.value) return
  const a = document.createElement('a')
  a.href = resultImageUrl.value
  a.download = `ai_image_${Date.now()}.jpg`
  a.click()
}

const showSavedSuccess = () => {
  ElMessage.info('图片已在素材库中，可前往「素材库」页面查看')
}

const retryGeneration = () => {
  currentRequest.value = null
  activeRequestId.value = null
  isGenerating.value = false
  currentProgress.value = 0
}

const selectHistoryItem = (item) => {
  activeRequestId.value = item.id
  currentRequest.value = item
  if (item.status === 'completed' && item.result_image_url) {
    resultImageUrl.value = item.result_image_url
    resultSavedToLibrary.value = !!item.media_item_id
    isGenerating.value = false
  } else if (item.status === 'processing' || item.status === 'pending') {
    isGenerating.value = true
    startPolling()
  }
}

const statusTagType = (s) => ({
  pending: 'info', processing: 'warning', completed: 'success', failed: 'danger'
})[s] || ''

const statusLabel = (s) => ({
  pending: '等待', processing: '生成中', completed: '完成', failed: '失败'
})[s] || s

const formatTime = (iso) => iso ? new Date(iso).toLocaleString('zh-CN') : ''
</script>

<style scoped>
.image-generator-view {
  padding: 0;
}

.page-header {
  margin-bottom: 24px;
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

.generator-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 900px) {
  .generator-layout {
    grid-template-columns: 1fr;
  }
}

.input-card,
.result-card,
.history-card {
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--el-border-color-lighter);
}

.input-card {
  margin-bottom: 16px;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
}

.form-section {
  margin-bottom: 20px;
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

/* Upload Zone */
.upload-zone {
  border: 2px dashed var(--el-border-color);
  border-radius: var(--radius-lg, 14px);
  height: 140px;
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
  font-size: 28px;
  color: var(--el-text-color-placeholder);
  margin-bottom: 8px;
}

.upload-hint {
  font-size: 13px;
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
  top: 8px;
  right: 8px;
}

.generate-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  background: var(--brand-primary, #6366f1);
  border-color: var(--brand-primary, #6366f1);
}

.generate-btn:hover:not(:disabled) {
  background: #5254c8;
  border-color: #5254c8;
}

/* History */
.history-list {
  max-height: 260px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.history-item:hover,
.history-item--active {
  background: rgba(99, 102, 241, 0.06);
}

.history-prompt {
  flex: 1;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-time {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

/* Result Panel */
.result-card {
  min-height: 460px;
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

.result-image-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 8px 0;
}

.result-image {
  max-width: 100%;
  max-height: 480px;
  border-radius: var(--radius-lg, 14px);
  box-shadow: var(--shadow-sm, 0 2px 12px rgba(0,0,0,0.08));
  object-fit: contain;
}

.result-actions {
  display: flex;
  gap: 12px;
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
