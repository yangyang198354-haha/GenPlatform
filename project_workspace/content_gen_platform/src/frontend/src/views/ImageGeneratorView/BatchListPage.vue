<template>
  <!-- 批次列表页面（US-05，AC-05-1）
       按时间倒序展示用户的所有豆包图片批次
       支持：重命名、删除、查看详情
  -->
  <div class="batch-list-page">
    <!-- 加载状态 -->
    <div v-if="loading" class="batch-loading">
      <el-icon class="spinning-icon"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="batches.length === 0" class="batch-empty">
      <el-icon class="empty-icon"><Picture /></el-icon>
      <p>暂无批次记录</p>
      <p class="empty-hint">提交图片生成请求后，批次将在此处展示</p>
    </div>

    <!-- 批次列表 -->
    <div v-else>
      <div
        v-for="batch in batches"
        :key="batch.id"
        class="batch-card"
        @click="openBatchDetail(batch)"
      >
        <div class="batch-info">
          <div class="batch-name-row">
            <!-- 重命名输入框（AC-05-3）-->
            <el-input
              v-if="renamingId === batch.id"
              v-model="renameValue"
              size="small"
              class="rename-input"
              @keyup.enter="confirmRename(batch)"
              @keyup.escape="cancelRename"
              @click.stop
              autofocus
            />
            <span v-else class="batch-name">{{ batch.name }}</span>

            <div class="batch-status-tag">
              <el-tag :type="statusTagType(batch.status)" size="small">
                {{ statusLabel(batch.status) }}
              </el-tag>
            </div>
          </div>

          <div class="batch-meta">
            <span class="meta-item">
              <el-icon><Camera /></el-icon>
              {{ batch.model }}
            </span>
            <span class="meta-item">
              <el-icon><Files /></el-icon>
              {{ batch.completed_count }}/{{ batch.total_count }} 张
            </span>
            <span class="meta-item">
              <el-icon><Clock /></el-icon>
              {{ formatTime(batch.created_at) }}
            </span>
            <el-tag v-if="batch.is_img2img" type="warning" size="small">图生图</el-tag>
          </div>

          <div class="batch-prompt">{{ batch.prompt }}</div>
        </div>

        <!-- 操作按钮 -->
        <div class="batch-actions" @click.stop>
          <el-button
            v-if="renamingId === batch.id"
            type="primary"
            size="small"
            @click.stop="confirmRename(batch)"
          >确认</el-button>
          <el-button
            v-if="renamingId === batch.id"
            size="small"
            @click.stop="cancelRename"
          >取消</el-button>
          <template v-else>
            <el-button
              size="small"
              :icon="Edit"
              @click.stop="startRename(batch)"
            >重命名</el-button>
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              :loading="deletingId === batch.id"
              @click.stop="confirmDelete(batch)"
            >删除</el-button>
          </template>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrap" v-if="totalCount > pageSize">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalCount"
          layout="prev, pager, next"
          @current-change="loadBatches"
        />
      </div>
    </div>

    <!-- 批次详情弹窗（AC-05-2）-->
    <el-dialog
      v-model="detailVisible"
      :title="selectedBatch?.name || '批次详情'"
      width="700px"
      destroy-on-close
    >
      <BatchDetailPage v-if="selectedBatch" :batch-id="selectedBatch.id" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Loading, Picture, Edit, Delete, Camera, Files, Clock,
} from '@element-plus/icons-vue'
import { imageAPI } from '@/api'
import BatchDetailPage from './BatchDetailPage.vue'

const batches = ref([])
const loading = ref(false)
const totalCount = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

// 重命名状态
const renamingId = ref(null)
const renameValue = ref('')

// 删除状态
const deletingId = ref(null)

// 批次详情弹窗
const detailVisible = ref(false)
const selectedBatch = ref(null)

onMounted(async () => {
  await loadBatches()
})

const loadBatches = async () => {
  loading.value = true
  try {
    const { data } = await imageAPI.getBatches({
      page: currentPage.value,
      page_size: pageSize.value,
    })
    batches.value = data.results
    totalCount.value = data.count
  } catch {
    ElMessage.error('加载批次列表失败')
  } finally {
    loading.value = false
  }
}

const openBatchDetail = (batch) => {
  selectedBatch.value = batch
  detailVisible.value = true
}

const startRename = (batch) => {
  renamingId.value = batch.id
  renameValue.value = batch.name
}

const cancelRename = () => {
  renamingId.value = null
  renameValue.value = ''
}

const confirmRename = async (batch) => {
  if (!renameValue.value.trim()) {
    ElMessage.error('批次名称不能为空')
    return
  }
  try {
    await imageAPI.renameBatch(batch.id, renameValue.value.trim())
    batch.name = renameValue.value.trim()
    cancelRename()
    ElMessage.success('重命名成功（AC-05-3）')
  } catch {
    ElMessage.error('重命名失败，请重试')
  }
}

const confirmDelete = async (batch) => {
  try {
    await ElMessageBox.confirm(
      `确定删除批次「${batch.name}」及其所有图片吗？此操作不可撤销。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await deleteBatch(batch)
  } catch {
    // 用户取消，忽略
  }
}

const deleteBatch = async (batch) => {
  deletingId.value = batch.id
  try {
    await imageAPI.deleteBatch(batch.id)
    batches.value = batches.value.filter((b) => b.id !== batch.id)
    totalCount.value -= 1
    ElMessage.success('批次已删除（AC-05-4）')
  } catch (err) {
    const status = err.response?.status
    if (status === 409) {
      ElMessage.error('批次生成中，无法删除（AC-05-5）')
    } else {
      ElMessage.error('删除失败，请重试')
    }
  } finally {
    deletingId.value = null
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
.batch-list-page {
  padding: 8px 0;
}

.batch-loading,
.batch-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: var(--el-text-color-placeholder);
}

.spinning-icon,
.empty-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.spinning-icon {
  animation: spin 1.5s linear infinite;
  color: var(--el-color-primary);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.empty-hint {
  font-size: 12px;
  margin-top: 4px;
}

.batch-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s;
  background: var(--el-bg-color);
}

.batch-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  border-color: var(--el-color-primary-light-7);
}

.batch-info {
  flex: 1;
  min-width: 0;
}

.batch-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.batch-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.rename-input {
  max-width: 280px;
}

.batch-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 6px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.batch-prompt {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
}

.batch-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-left: 16px;
  flex-shrink: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>
