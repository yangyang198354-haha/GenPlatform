<template>
  <div class="kb-view">
    <div class="page-header">
      <h2>知识库</h2>
      <el-button type="primary" :icon="Plus" @click="showUploadDialog = true">
        上传文档
      </el-button>
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
      <el-table-column prop="title" label="文档名称" min-width="200" />
      <el-table-column prop="file_type" label="类型" width="80" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
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
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="deleteDoc(row.id)">
            <template #reference>
              <el-button type="danger" size="small" :icon="Delete" circle />
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Upload dialog -->
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
      <el-input v-model="uploadTitle" placeholder="文档标题（可选）" class="upload-title" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Plus, Search, Delete, UploadFilled } from "@element-plus/icons-vue";
import { kbAPI } from "@/api";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const documents = ref([]);
const loading = ref(false);
const showUploadDialog = ref(false);
const searchQuery = ref("");
const uploadTitle = ref("");

onMounted(fetchDocuments);

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

const statusType = (s) =>
  ({ available: "success", processing: "warning", failed: "danger" }[s] ?? "info");
const statusLabel = (s) =>
  ({ available: "可用", processing: "处理中", failed: "失败" }[s] ?? s);

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
.search-bar { margin-bottom: 16px; max-width: 400px; }
.upload-title { margin-top: 12px; }
</style>
