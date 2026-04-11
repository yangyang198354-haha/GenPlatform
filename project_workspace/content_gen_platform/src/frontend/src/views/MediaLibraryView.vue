<template>
  <div class="media-library-view">
    <div class="page-header">
      <div class="header-left">
        <h2>素材库</h2>
        <span class="item-count" v-if="total > 0">{{ total }} 个文件</span>
      </div>
      <el-button type="primary" :icon="Upload" @click="showUploadDialog = true">
        上传素材
      </el-button>
    </div>

    <!-- Filter Tabs -->
    <div class="filter-tabs">
      <button
        v-for="tab in filterTabs"
        :key="tab.value"
        class="filter-tab"
        :class="{ 'filter-tab--active': activeFilter === tab.value }"
        @click="setFilter(tab.value)"
      >
        <el-icon><component :is="tab.icon" /></el-icon>
        {{ tab.label }}
      </button>
    </div>

    <!-- Grid -->
    <div v-if="loading && !items.length" class="loading-placeholder">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="items.length" class="media-grid" ref="gridRef">
      <div
        v-for="item in items"
        :key="item.id"
        class="media-card"
        @mouseenter="hoveredId = item.id"
        @mouseleave="hoveredId = null"
      >
        <!-- Thumbnail / Preview -->
        <div class="media-thumb">
          <img
            v-if="item.media_type === 'image'"
            :src="item.file_url"
            :alt="item.title"
            class="thumb-img"
            loading="lazy"
          />
          <div v-else-if="item.media_type === 'video'" class="thumb-video">
            <video :src="item.file_url" class="thumb-img" preload="metadata" />
            <div class="video-overlay">
              <el-icon class="play-icon"><VideoPlay /></el-icon>
            </div>
          </div>
          <div v-else class="thumb-audio">
            <el-icon class="audio-icon"><Headset /></el-icon>
          </div>

          <!-- Hover Actions Overlay -->
          <transition name="fade">
            <div v-show="hoveredId === item.id" class="hover-overlay">
              <div class="hover-actions">
                <el-tooltip content="下载" placement="top">
                  <el-button
                    circle
                    size="small"
                    :icon="Download"
                    @click="downloadItem(item)"
                  />
                </el-tooltip>
                <el-tooltip content="删除" placement="top">
                  <el-button
                    circle
                    size="small"
                    type="danger"
                    :icon="Delete"
                    @click="confirmDelete(item)"
                  />
                </el-tooltip>
              </div>
            </div>
          </transition>
        </div>

        <!-- Card Info -->
        <div class="media-info">
          <div class="media-title" :title="item.title">{{ item.title }}</div>
          <div class="media-meta">
            <el-tag size="small" :type="sourceTagType(item.source)" effect="plain">
              {{ sourceLabel(item.source) }}
            </el-tag>
            <span class="file-size">{{ formatFileSize(item.file_size) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <el-empty
      v-else-if="!loading"
      :description="emptyDescription"
      :image-size="120"
    >
      <el-button type="primary" @click="showUploadDialog = true">上传第一个素材</el-button>
    </el-empty>

    <!-- Load More -->
    <div v-if="hasMore" class="load-more">
      <el-button :loading="loading" @click="loadMore">加载更多</el-button>
    </div>

    <!-- Upload Dialog -->
    <el-dialog
      v-model="showUploadDialog"
      title="上传素材"
      width="480px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="upload-dialog-content">
        <el-form :model="uploadForm" label-position="top">
          <el-form-item label="素材类型" required>
            <el-radio-group v-model="uploadForm.mediaType">
              <el-radio-button value="image">图片</el-radio-button>
              <el-radio-button value="video">视频</el-radio-button>
              <el-radio-button value="audio">音频</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="选择文件" required>
            <el-upload
              ref="uploadRef"
              :accept="acceptTypes[uploadForm.mediaType]"
              :before-upload="() => false"
              :on-change="handleUploadChange"
              :file-list="[]"
              drag
              :limit="1"
              class="uploader"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">
                拖拽文件到此处，或 <em>点击上传</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">
                  {{ uploadTip }}
                </div>
              </template>
            </el-upload>
          </el-form-item>

          <el-form-item label="标题（可选）">
            <el-input v-model="uploadForm.title" placeholder="留空则使用文件名" />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="isUploading"
          :disabled="!uploadForm.file"
          @click="submitUpload"
        >
          {{ isUploading ? '上传中...' : '确认上传' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, markRaw } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, UploadFilled, Delete, Download, VideoPlay, Headset,
  Picture, Film, Microphone, Files,
} from '@element-plus/icons-vue'
import { mediaAPI } from '@/api'

// Filter state — wrap icon components with markRaw() to prevent Vue from
// converting them into reactive proxies.  Putting a component definition
// object inside a plain const causes Vite to minify it; Vue's reactivity
// system then tries to proxy the minified reference and hits a Temporal
// Dead Zone (TDZ) error: "Cannot access 'x' before initialization".
// markRaw() opts the object out of Vue's reactivity, eliminating the TDZ.
const filterTabs = [
  { value: 'all',   label: '全部', icon: markRaw(Files)      },
  { value: 'image', label: '图片', icon: markRaw(Picture)    },
  { value: 'video', label: '视频', icon: markRaw(Film)       },
  { value: 'audio', label: '音频', icon: markRaw(Microphone) },
]
const activeFilter = ref('all')

// Grid state
const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 24
const hasMore = computed(() => items.value.length < total.value)
const hoveredId = ref(null)

// Upload dialog state
const showUploadDialog = ref(false)
const isUploading = ref(false)
const uploadForm = ref({ mediaType: 'image', file: null, title: '' })
const uploadRef = ref(null)

const acceptTypes = {
  image: 'image/jpeg,image/png,image/gif,image/webp',
  video: 'video/mp4,video/quicktime,video/x-msvideo',
  audio: 'audio/mpeg,audio/wav,audio/ogg,audio/mp4',
}

const uploadTip = computed(() => {
  const limits = { image: '图片（JPG/PNG/GIF/WebP）最大 20 MB', video: '视频（MP4/MOV/AVI）最大 500 MB', audio: '音频（MP3/WAV/OGG/M4A）最大 100 MB' }
  return limits[uploadForm.value.mediaType] || ''
})

const emptyDescription = computed(() => {
  const labels = { all: '素材库为空', image: '暂无图片', video: '暂无视频', audio: '暂无音频' }
  return labels[activeFilter.value] || '暂无素材'
})

onMounted(fetchItems)

watch(activeFilter, () => {
  page.value = 1
  items.value = []
  fetchItems()
})

const setFilter = (value) => {
  activeFilter.value = value
}

const fetchItems = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (activeFilter.value !== 'all') params.media_type = activeFilter.value
    const { data } = await mediaAPI.list(params)
    const newItems = data.results ?? data
    if (page.value === 1) {
      items.value = newItems
    } else {
      items.value = [...items.value, ...newItems]
    }
    total.value = data.count ?? newItems.length
  } catch (err) {
    const msg = err.response?.data?.error || '加载素材库失败，请刷新重试'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

const loadMore = () => {
  page.value++
  fetchItems()
}

const handleUploadChange = (file) => {
  uploadForm.value.file = file.raw
}

const submitUpload = async () => {
  if (!uploadForm.value.file) return
  isUploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadForm.value.file)
    formData.append('media_type', uploadForm.value.mediaType)
    if (uploadForm.value.title) formData.append('title', uploadForm.value.title)

    const { data } = await mediaAPI.upload(formData)
    items.value.unshift(data)
    total.value++
    showUploadDialog.value = false
    uploadForm.value = { mediaType: 'image', file: null, title: '' }
    ElMessage.success('上传成功')
  } catch (err) {
    const msg = err.response?.data?.error || '上传失败，请重试'
    ElMessage.error(msg)
  } finally {
    isUploading.value = false
  }
}

const downloadItem = (item) => {
  const a = document.createElement('a')
  a.href = item.file_url
  a.download = item.title
  a.target = '_blank'
  a.click()
}

const confirmDelete = async (item) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除「${item.title}」吗？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await mediaAPI.delete(item.id)
    items.value = items.value.filter(i => i.id !== item.id)
    total.value--
    ElMessage.success('已删除')
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const sourceTagType = (s) => ({ ai_generated: 'primary', uploaded: 'success' })[s] || ''
const sourceLabel = (s) => ({ ai_generated: 'AI 生成', uploaded: '已上传' })[s] || s

const formatFileSize = (bytes) => {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}
</script>

<style scoped>
.media-library-view {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.item-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* Filter Tabs */
.filter-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  background: var(--surface-base, #f0f4fa);
  padding: 4px;
  border-radius: 10px;
  width: fit-content;
}

.filter-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  line-height: 1;
}

.filter-tab:hover {
  color: var(--el-text-color-primary);
  background: rgba(255, 255, 255, 0.6);
}

.filter-tab--active {
  background: #ffffff;
  color: var(--brand-primary, #6366f1);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

/* Media Grid */
.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
}

@media (min-width: 1440px) {
  .media-grid {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
}

.media-card {
  background: var(--surface-card, #ffffff);
  border-radius: var(--radius-lg, 14px);
  overflow: hidden;
  box-shadow: var(--shadow-sm, 0 1px 4px rgba(0, 0, 0, 0.06));
  border: 1px solid var(--el-border-color-lighter);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  cursor: default;
}

.media-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
}

/* Thumbnail */
.media-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  background: var(--surface-base, #f0f4fa);
}

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-video {
  width: 100%;
  height: 100%;
  position: relative;
}

.video-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2);
}

.play-icon {
  font-size: 32px;
  color: #ffffff;
}

.thumb-audio {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.audio-icon {
  font-size: 40px;
  color: rgba(255, 255, 255, 0.9);
}

/* Hover Overlay */
.hover-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
}

.hover-actions {
  display: flex;
  gap: 10px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Card Info */
.media-info {
  padding: 10px 12px 12px;
}

.media-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 6px;
}

.media-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.file-size {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

/* Load More */
.load-more {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

/* Upload Dialog */
.upload-dialog-content {
  padding: 0 4px;
}

.uploader {
  width: 100%;
}

/* Loading placeholder */
.loading-placeholder {
  padding: 20px 0;
}
</style>
