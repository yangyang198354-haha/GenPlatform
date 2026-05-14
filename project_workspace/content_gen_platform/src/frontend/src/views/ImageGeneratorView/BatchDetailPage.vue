<template>
  <!-- 批次详情页面（US-05，AC-05-2）
       展示批次内所有图片的缩略图网格
       在 BatchListPage 的 el-dialog 中嵌入使用
  -->
  <div class="batch-detail-page">
    <!-- 加载状态 -->
    <div v-if="loading" class="detail-loading">
      <el-icon class="spinning-icon"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <!-- 批次信息概览 -->
    <div v-else-if="batch">
      <div class="batch-meta-bar">
        <span class="meta-item">
          <strong>模型：</strong>{{ batch.model }}
        </span>
        <span class="meta-item">
          <strong>状态：</strong>
          <el-tag :type="statusTagType(batch.status)" size="small">
            {{ statusLabel(batch.status) }}
          </el-tag>
        </span>
        <span class="meta-item">
          <strong>完成：</strong>{{ batch.completed_count }}/{{ batch.total_count }} 张
        </span>
        <span class="meta-item">
          <strong>类型：</strong>{{ batch.is_img2img ? '图生图' : '文生图' }}
        </span>
        <span class="meta-item">
          <strong>时间：</strong>{{ formatTime(batch.created_at) }}
        </span>
      </div>

      <div class="batch-prompt-display">
        <strong>提示词：</strong>{{ batch.prompt }}
      </div>

      <!-- 图片缩略图网格（AC-05-2，v1.2.1 BUG-01 修复）-->
      <div class="image-grid" v-if="completedRequests.length > 0 || failedRequests.length > 0">
        <!-- 已完成图片：使用 el-image 渲染缩略图（thumbnail_url 优先，支持 Lightbox） -->
        <div
          v-for="req in completedRequests"
          :key="req.id"
          class="image-grid-item"
        >
          <!-- v1.2.1 BUG-01：thumbnail_url 存在时用 el-image，否则降级占位符 -->
          <el-image
            v-if="req.thumbnail_url"
            :src="req.thumbnail_url"
            :preview-src-list="completedImageUrls"
            :initial-index="completedRequests.indexOf(req)"
            class="grid-thumb"
            fit="cover"
            loading="lazy"
            preview-teleported
          />
          <div v-else class="image-placeholder">
            <el-icon class="placeholder-icon"><Picture /></el-icon>
            <span class="media-id">素材 #{{ req.media_item_id }}</span>
          </div>
          <div class="item-status">
            <el-tag type="success" size="small">已完成</el-tag>
          </div>
        </div>

        <!-- 失败的请求 -->
        <div
          v-for="req in failedRequests"
          :key="req.id"
          class="image-grid-item image-grid-item--failed"
        >
          <div class="image-placeholder">
            <el-icon class="placeholder-icon error"><CircleClose /></el-icon>
            <span class="error-msg">{{ req.error_message || '生成失败' }}</span>
          </div>
          <div class="item-status">
            <el-tag type="danger" size="small">失败</el-tag>
          </div>
        </div>
      </div>

      <!-- 无图片 -->
      <div v-else class="no-images">
        <p>批次内暂无已完成的图片</p>
      </div>
    </div>

    <!-- 加载失败 -->
    <div v-else class="load-error">
      <p>加载批次详情失败，请刷新重试</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Picture, CircleClose } from '@element-plus/icons-vue'
import { imageAPI } from '@/api'
// v1.2.1 BUG-01：导入 ElImage（BatchDetailPage 内的 el-image 需要全局注册或本地引用）
// Element Plus 已全局注册，此处无需单独导入，el-image 直接在 template 使用即可

const props = defineProps({
  batchId: {
    type: Number,
    required: true,
  },
})

const batch = ref(null)
const loading = ref(false)

const completedRequests = computed(() => {
  if (!batch.value) return []
  return (batch.value.requests || []).filter((r) => r.status === 'completed')
})

const failedRequests = computed(() => {
  if (!batch.value) return []
  return (batch.value.requests || []).filter((r) => r.status === 'failed')
})

// v1.2.1 BUG-01：已完成图片的 URL 列表，供 el-image preview-src-list 多图切换
const completedImageUrls = computed(() =>
  completedRequests.value
    .filter((r) => r.thumbnail_url)
    .map((r) => r.thumbnail_url)
)

onMounted(async () => {
  await loadBatchDetail()
})

const loadBatchDetail = async () => {
  loading.value = true
  try {
    const { data } = await imageAPI.getBatchDetail(props.batchId)
    batch.value = data
  } catch {
    ElMessage.error('加载批次详情失败')
  } finally {
    loading.value = false
  }
}

const statusTagType = (s) => ({
  pending: 'info',
  processing: 'warning',
  completed: 'success',
  partial_failed: 'warning',
  failed: 'danger',
})[s] || ''

const statusLabel = (s) => ({
  pending: '等待中',
  processing: '生成中',
  completed: '已完成',
  partial_failed: '部分失败',
  failed: '失败',
})[s] || s

const formatTime = (iso) => iso ? new Date(iso).toLocaleString('zh-CN') : ''
</script>

<style scoped>
.batch-detail-page {
  padding: 0 4px;
}

.detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
  color: var(--el-text-color-placeholder);
}

.spinning-icon {
  font-size: 36px;
  margin-bottom: 10px;
  animation: spin 1.5s linear infinite;
  color: var(--el-color-primary);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.batch-meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.meta-item {
  font-size: 13px;
  color: var(--el-text-color-regular);
  display: flex;
  align-items: center;
  gap: 4px;
}

.batch-prompt-display {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--el-fill-color-extra-light);
  border-radius: 6px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.image-grid-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
  position: relative;
}

.image-grid-item--failed {
  border-color: var(--el-color-danger-light-7);
  background: var(--el-color-danger-light-9);
}

/* v1.2.1 BUG-01：el-image 缩略图样式 */
.grid-thumb {
  width: 100%;
  height: 140px;
  display: block;
}

.grid-thumb :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* el-image 预览模式下内部 img 添加 cursor:pointer */
.grid-thumb :deep(.el-image__preview) {
  cursor: pointer;
}

.image-placeholder {
  height: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  gap: 6px;
}

.placeholder-icon {
  font-size: 32px;
  color: var(--el-text-color-placeholder);
}

.placeholder-icon.error {
  color: var(--el-color-danger);
}

.media-id {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.error-msg {
  font-size: 11px;
  color: var(--el-color-danger);
  text-align: center;
  padding: 0 8px;
}

.item-status {
  padding: 6px 8px;
  text-align: center;
}

.no-images,
.load-error {
  text-align: center;
  padding: 40px 0;
  color: var(--el-text-color-placeholder);
}
</style>
