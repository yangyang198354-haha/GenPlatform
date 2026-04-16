<template>
  <div class="kb-view">
    <div class="page-header">
      <h2>知识库</h2>
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
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
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
import { ref, markRaw, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Plus, Search, Delete, UploadFilled, FolderOpened, EditPen } from "@element-plus/icons-vue";
import { kbAPI } from "@/api";

// markRaw prevents Vue reactivity proxy from wrapping icon components,
// avoiding TDZ errors in production builds (see kb entry SD-L014).
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

onMounted(() => fetchDocuments());

async function fetchDocuments() {
  loading.value = true;
  try {
    const { data } = await kbAPI.list();
    documents.value = data.results ?? data;
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
    await kbAPI.upload(formData);
    ElMessage.success("上传成功，正在处理…");
    showUploadDialog.value = false;
    uploadTitle.value = "";
    fetchDocuments();
  } catch (err) {
    const msg = err.response?.data?.error || "上传失败，请重试";
    ElMessage.error(msg);
  }
}

async function deleteDoc(id) {
  await kbAPI.delete(id);
  ElMessage.success("已删除");
  fetchDocuments();
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
    fetchDocuments();
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

const statusType = (s) =>
  ({ available: "success", processing: "warning", error: "danger" }[s] ?? "info");
const statusLabel = (s) =>
  ({ available: "可用", processing: "处理中", error: "失败" }[s] ?? s);

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
.page-header h2 { margin: 0; }
.header-actions { display: flex; gap: 8px; }
.search-bar { margin-bottom: 16px; max-width: 400px; }
.upload-title { margin-top: 12px; }
</style>
