<template>
  <div class="kb-view">
    <div class="page-header">
      <h1>知识库</h1>
      <div class="header-actions">
        <el-button type="primary" :icon="IconPlus" @click="showUploadDialog = true">
          上传文档
        </el-button>
        <el-button :icon="IconFolderOpened" @click="triggerDirUpload">
          上传目录
        </el-button>
        <!-- Hidden native directory picker -->
        <input
          ref="dirInputRef"
          type="file"
          style="display: none"
          webkitdirectory
          multiple
          @change="handleDirSelected"
        />
      </div>
    </div>

    <!-- Search -->
    <el-input
      v-model="searchQuery"
      placeholder="搜索文档…"
      clearable
      class="search-bar"
      @input="handleSearch"
    >
      <template #prefix><el-icon><Search /></el-icon></template>
    </el-input>

    <!-- Document list -->
    <el-table :data="documents" v-loading="loading" stripe>
      <el-table-column prop="name" label="文档名称" min-width="200" />
      <el-table-column prop="file_type" label="类型" width="80" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size_bytes) }}</template>
      </el-table-column>
      <el-table-column label="状态" min-width="220">
        <template #default="{ row }">
          <!-- Processing: show progress bar with stage message -->
          <div v-if="row.status === 'processing'" class="status-processing">
            <el-progress
              :percentage="row.progress || 0"
              :stroke-width="6"
              status="striped"
              striped-flow
              :duration="10"
              class="doc-progress"
            />
            <span class="progress-msg">{{ row.progress_message || '处理中…' }}</span>
          </div>
          <!-- Error: show tag + expandable message -->
          <div v-else-if="row.status === 'error'" class="status-error">
            <el-tag type="danger">失败</el-tag>
            <el-tooltip
              v-if="row.error_message"
              :content="row.error_message"
              placement="top"
              :show-after="200"
            >
              <el-icon class="error-icon"><InfoFilled /></el-icon>
            </el-tooltip>
          </div>
          <!-- Available -->
          <el-tag v-else type="success">可用</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="chunk_count" label="分块数" width="90" />
      <el-table-column label="上传时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            :icon="IconEditPen"
            circle
            title="重命名"
            @click="startRename(row)"
          />
          <el-popconfirm title="确认删除？" @confirm="deleteDoc(row.id)">
            <template #reference>
              <el-button type="danger" size="small" :icon="IconDelete" circle title="删除" />
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Single-file upload dialog -->
    <el-dialog v-model="showUploadDialog" title="上传文档" width="480px">
      <el-upload
        ref="uploadRef"
        drag
        :http-request="customUpload"
        :before-upload="beforeUpload"
        :show-file-list="false"
        accept=".pdf,.docx,.txt,.md"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此，或 <em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF / DOCX / TXT / MD，单文件 ≤ 50MB</div>
        </template>
      </el-upload>
      <el-input v-model="uploadTitle" placeholder="文档标题（可选，默认使用文件名）" class="upload-title" />
    </el-dialog>

    <!-- Rename dialog -->
    <el-dialog v-model="showRenameDialog" title="重命名文档" width="400px" @closed="renameTarget = null">
      <el-input
        v-model="renameValue"
        placeholder="请输入新名称"
        maxlength="255"
        show-word-limit
        @keyup.enter="confirmRename"
      />
      <template #footer>
        <el-button @click="showRenameDialog = false">取消</el-button>
        <el-button type="primary" :loading="renaming" @click="confirmRename">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, markRaw, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import { Plus, Search, Delete, UploadFilled, FolderOpened, EditPen, InfoFilled } from "@element-plus/icons-vue";
import { kbAPI } from "@/api";

// markRaw prevents Vue reactivity proxy from wrapping icon components,
// avoiding TDZ errors in production builds.
const IconPlus = markRaw(Plus);
const IconDelete = markRaw(Delete);
const IconFolderOpened = markRaw(FolderOpened);
const IconEditPen = markRaw(EditPen);

const documents = ref([]);
const loading = ref(false);
const showUploadDialog = ref(false);
const searchQuery = ref("");
const uploadTitle = ref("");

// Directory upload
const dirInputRef = ref(null);

// Rename state
const showRenameDialog = ref(false);
const renameTarget = ref(null);
const renameValue = ref("");
const renaming = ref(false);

// ── Polling ──────────────────────────────────────────────────────────────────
// Poll individual documents that are still in "processing" state.
// Each entry: { docId, intervalId, retries }
const _pollingMap = new Map();
// Max consecutive poll failures before giving up on a single doc.
const POLL_MAX_RETRIES = 60;
// Poll interval in milliseconds.
const POLL_INTERVAL_MS = 2000;

function _startPolling(docId) {
  if (_pollingMap.has(docId)) return; // already polling
  let retries = 0;
  const intervalId = setInterval(async () => {
    retries += 1;
    if (retries > POLL_MAX_RETRIES) {
      _stopPolling(docId);
      return;
    }
    try {
      const { data } = await kbAPI.get(docId);
      // Update the document in the reactive list in-place to avoid full re-render
      const idx = documents.value.findIndex((d) => d.id === docId);
      if (idx !== -1) {
        documents.value[idx] = { ...documents.value[idx], ...data };
      }
      // Stop polling when terminal state is reached
      if (data.status === "available" || data.status === "error") {
        _stopPolling(docId);
      }
    } catch {
      // Network error — keep polling, retries counter handles timeout
    }
  }, POLL_INTERVAL_MS);
  _pollingMap.set(docId, intervalId);
}

function _stopPolling(docId) {
  const id = _pollingMap.get(docId);
  if (id !== undefined) {
    clearInterval(id);
    _pollingMap.delete(docId);
  }
}

function _stopAllPolling() {
  for (const [docId] of _pollingMap) {
    _stopPolling(docId);
  }
}

// Start polling for all documents currently in "processing" state.
function _schedulePollingForProcessing() {
  for (const doc of documents.value) {
    if (doc.status === "processing") {
      _startPolling(doc.id);
    }
  }
}

onUnmounted(_stopAllPolling);

onMounted(() => fetchDocuments());

async function fetchDocuments() {
  loading.value = true;
  try {
    const { data } = await kbAPI.list();
    documents.value = data.results ?? data;
    _schedulePollingForProcessing();
  } finally {
    loading.value = false;
  }
}

async function handleSearch() {
  if (!searchQuery.value) return fetchDocuments();
  loading.value = true;
  try {
    const { data } = await kbAPI.search(searchQuery.value);
    documents.value = data.results ?? data;
    _schedulePollingForProcessing();
  } finally {
    loading.value = false;
  }
}

function beforeUpload(file) {
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error("文件大小不得超过 50MB");
    return false;
  }
  return true;
}

async function customUpload({ file }) {
  const formData = new FormData();
  formData.append("file", file);
  if (uploadTitle.value) formData.append("name", uploadTitle.value);
  try {
    const { data: newDoc } = await kbAPI.upload(formData);
    ElMessage.success("上传成功，正在处理…");
    showUploadDialog.value = false;
    uploadTitle.value = "";
    // Prepend new doc to list and start polling immediately
    documents.value = [newDoc, ...documents.value];
    if (newDoc.status === "processing") {
      _startPolling(newDoc.id);
    }
  } catch (err) {
    const msg = err.response?.data?.error || "上传失败，请重试";
    ElMessage.error(msg);
  }
}

async function deleteDoc(id) {
  _stopPolling(id);
  await kbAPI.delete(id);
  ElMessage.success("已删除");
  documents.value = documents.value.filter((d) => d.id !== id);
}

// ── Directory upload ──────────────────────────────────────────────────────

function triggerDirUpload() {
  dirInputRef.value?.click();
}

async function handleDirSelected(event) {
  const allFiles = Array.from(event.target.files);
  const supported = allFiles.filter((f) => /\.(pdf|docx|txt|md)$/i.test(f.name));

  if (supported.length === 0) {
    ElMessage.error("所选目录中无可导入的文档");
    event.target.value = "";
    return;
  }

  ElMessage.info(`正在上传 ${supported.length} 个文件…`);

  const formData = new FormData();
  const relativePaths = [];
  supported.forEach((f) => {
    formData.append("files", f);
    relativePaths.push(f.webkitRelativePath || f.name);
  });
  formData.append("relative_paths", JSON.stringify(relativePaths));

  try {
    const { data } = await kbAPI.batchUpload(formData);
    if (data.accepted.length > 0) {
      ElMessage.success(data.summary);
    } else {
      ElMessage.warning(data.summary || "没有文件成功入库");
    }
    // Re-fetch to get the newly created documents and start polling for them
    await fetchDocuments();
  } catch (err) {
    const msg = err.response?.data?.error || "目录上传失败，请重试";
    ElMessage.error(msg);
  } finally {
    event.target.value = "";
  }
}

// ── Rename ────────────────────────────────────────────────────────────────

function startRename(row) {
  renameTarget.value = row;
  renameValue.value = row.name;
  showRenameDialog.value = true;
}

async function confirmRename() {
  const newName = renameValue.value.trim();
  if (!newName) {
    ElMessage.warning("文档名称不能为空");
    return;
  }
  if (!renameTarget.value) return;

  renaming.value = true;
  try {
    await kbAPI.rename(renameTarget.value.id, newName);
    ElMessage.success("重命名成功");
    // Optimistic update — no need to re-fetch the whole list
    renameTarget.value.name = newName;
    showRenameDialog.value = false;
  } catch (err) {
    ElMessage.error(err.response?.data?.error || "重命名失败，请重试");
  } finally {
    renaming.value = false;
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatSize(bytes) {
  if (!bytes) return "-";
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString("zh-CN") : "-";
}
</script>

<style scoped>
.kb-view { }
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h1 { margin: 0; font-size: 1.4rem; }
.header-actions { display: flex; gap: 8px; }
.search-bar { margin-bottom: 16px; max-width: 400px; }
.upload-title { margin-top: 12px; }

/* Processing state: stacked progress bar + stage label */
.status-processing {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 160px;
}
.doc-progress {
  width: 100%;
}
.progress-msg {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Error state: tag + info icon */
.status-error {
  display: flex;
  align-items: center;
  gap: 6px;
}
.error-icon {
  color: #f56c6c;
  cursor: pointer;
  font-size: 16px;
}
</style>
