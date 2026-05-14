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

              <!-- 生成中（v1.2.1 BUG-03：无取消按钮，失败后直接重试） -->
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

              <!-- 失败（v1.2.1 BUG-03：常驻 ElAlert + 重新生成按钮） -->
              <div v-else-if="generationError" class="result-error">
                <el-alert
                  :title="`生成失败：${generationError}`"
                  type="error"
                  :closable="false"
                  show-icon
                  class="error-alert"
                />
                <el-button
                  type="primary"
                  style="margin-top: 16px"
                  @click="resetGeneration"
                >
                  重新生成
                </el-button>
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

// v1.2.1 BUG-03：超时保护定时器 + HTTP 轮询定时器
let generationTimer = null   // 5 分钟超时保护
let pollingTimer = null      // HTTP 轮询（WebSocket 不可用时降级）

const GENERATION_TIMEOUT_MS = 5 * 60 * 1000  // 5 分钟（Ark API 通常 30s 内返回）
const POLLING_INTERVAL_MS = 3000              // 轮询间隔 3 秒

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
  // v1.2.1 BUG-03：组件销毁时清理定时器，防止内存泄漏
  _clearGenerationTimers()
})

// ── v1.2.1 BUG-03：定时器清理工具函数 ──────────────────────────────────────────
const _clearGenerationTimers = () => {
  if (generationTimer) {
    clearTimeout(generationTimer)
    generationTimer = null
  }
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

// ── v1.2.1 BUG-03c：HTTP 轮询降级（WebSocket 不可用时启动）──────────────────────
const startPolling = (batchId) => {
  if (pollingTimer) return  // 防止重复启动
  pollingTimer = setInterval(async () => {
    if (!isGenerating.value) {
      stopPolling()
      return
    }
    try {
      const { data } = await imageAPI.getBatchDetail(batchId)
      // 同步已完成图片列表（从 requests 提取 completed 条目）
      const completed = (data.requests || []).filter((r) => r.status === 'completed')
      completedImages.value = completed.map((r) => ({
        request_id: r.id,
        file_url: r.thumbnail_url || r.result_image_url || '',
        media_item_id: r.media_item_id,
      }))
      // 批次进入最终态：停止轮询，重置状态
      if (['completed', 'partial_failed', 'failed'].includes(data.status)) {
        _clearGenerationTimers()
        isGenerating.value = false
        if (data.status === 'failed') {
          generationError.value = '图片生成失败，请重试'
          ElMessage({
            type: 'error',
            message: '图片生成失败，请重试',
            duration: 0,
            showClose: true,
          })
        } else if (data.status === 'partial_failed') {
          ElMessage.warning(`批次部分完成：${completedImages.value.length} 张成功，请检查失败原因`)
        } else {
          ElMessage.success(`${completedImages.value.length} 张图片已全部生成完成，已自动保存到素材库！`)
        }
      }
    } catch {
      // 轮询单次失败不终止（网络抖动），等下次继续
    }
  }, POLLING_INTERVAL_MS)
}

const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

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
  // v1.2.1 BUG-03c：WebSocket 不可用时降级到 HTTP 轮询
  ws.onerror = () => {
    if (currentBatch.value && isGenerating.value) {
      startPolling(currentBatch.value.batch_id)
    }
  }
}

const handleWebSocketMessage = (msg) => {
  const { event_type, payload } = msg

  if (!currentBatch.value) return
  if (payload.batch_id !== currentBatch.value.batch_id) return

  if (event_type === 'batch_progress') {
    // 批次开始处理（无需额外操作）
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

  // v1.2.1 BUG-03b 修复：image_failed 必须重置 isGenerating + 持久错误（duration:0）
  if (event_type === 'image_failed') {
    const errMsg = payload.error || '图片生成失败'
    generationError.value = errMsg
    isGenerating.value = false          // 修复：原来漏掉了 isGenerating 重置
    completedImages.value = []          // 进度条归零
    _clearGenerationTimers()
    ElMessage({
      type: 'error',
      message: `图片生成失败：${errMsg}`,
      duration: 0,         // v1.2.1 BUG-03a 修复：持久展示（原默认 3000ms）
      showClose: true,
    })
  }

  if (event_type === 'batch_completed') {
    _clearGenerationTimers()    // v1.2.1：清理超时保护定时器
    isGenerating.value = false
    const batchStatus = payload.status
    if (batchStatus === 'completed') {
      ElMessage.success(`${completedImages.value.length} 张图片已全部生成完成，已自动保存到素材库！`)
    } else if (batchStatus === 'partial_failed') {
      ElMessage.warning(`批次部分完成：${completedImages.value.length} 张成功，请检查失败原因`)
    } else {
      // v1.2.1 BUG-03b 修复：batch_completed[failed] 也要重置 completedImages 并持久展示错误
      generationError.value = '所有图片生成失败，请稍后重试'
      completedImages.value = []
      ElMessage({
        type: 'error',
        message: '所有图片生成失败，请稍后重试',
        duration: 0,
        showClose: true,
      })
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

  // v1.2.1：新提交时清理上一次的定时器（防止残留超时定时器干扰新请求）
  _clearGenerationTimers()
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

    // v1.2.1 BUG-03b：5 分钟超时保护（POST 成功后启动）
    // Ark API 通常 30s 内返回，5min 是安全边界，防止 isGenerating 永久为 true
    generationTimer = setTimeout(() => {
      if (isGenerating.value) {
        isGenerating.value = false
        completedImages.value = []
        generationError.value = '生成超时，请检查网络连接后重试'
        ElMessage({
          type: 'warning',
          message: '生成超时，已自动重置状态，请重试',
          duration: 0,
          showClose: true,
        })
      }
    }, GENERATION_TIMEOUT_MS)
  } catch (err) {
    // v1.2.1 BUG-03b：POST 失败路径统一重置状态（场景 B）
    isGenerating.value = false
    completedImages.value = []    // 进度条归零
    _clearGenerationTimers()
    const errorCode = err.response?.data?.error || ''
    const errMsg = err.response?.data?.detail || err.response?.data?.error || '提交失败，请检查豆包 API Key 是否已配置'

    generationError.value = errMsg

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
      // v1.2.1 BUG-03a 修复：POST 失败错误信息持久展示（duration:0，showClose:true）
      ElMessage({
        type: 'error',
        message: errMsg,
        duration: 0,
        showClose: true,
      })
    }
  }
}

const resetGeneration = () => {
  _clearGenerationTimers()   // v1.2.1：清理超时保护和轮询定时器
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

/* v1.2.1 BUG-03a：result-error 使用 ElAlert 常驻展示，布局调整 */
.result-error {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 40px;
}

.error-alert {
  text-align: left;
}
</style>
