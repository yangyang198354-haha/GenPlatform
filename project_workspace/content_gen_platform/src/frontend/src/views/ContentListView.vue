<template>
  <div class="content-list-view">
    <div class="page-header">
      <h2>内容列表</h2>
      <el-button type="primary" :icon="Plus" @click="$router.push('/workspace')">
        新建内容
      </el-button>
    </div>

    <el-table :data="contents" v-loading="loading" stripe @row-click="openContent">
      <el-table-column prop="title" label="标题" min-width="200">
        <template #default="{ row }">
          {{ row.title || `内容 #${row.id}` }}
        </template>
      </el-table-column>
      <el-table-column label="平台" width="120">
        <template #default="{ row }">
          <el-tag>{{ platformLabel(row.platform_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="字数" width="80">
        <template #default="{ row }">{{ row.body?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click.stop="openContent(row)">查看</el-button>
          <el-popconfirm title="确认删除？" @confirm="deleteContent(row.id)">
            <template #reference>
              <el-button type="danger" size="small" @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      class="pagination"
      @current-change="fetchContents"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { contentAPI } from "@/api";

const router = useRouter();
const contents = ref([]);
const loading = ref(false);
const page = ref(1);
const pageSize = 20;
const total = ref(0);

onMounted(fetchContents);

async function fetchContents() {
  loading.value = true;
  try {
    const { data } = await contentAPI.list({ page: page.value });
    contents.value = data.results ?? data;
    total.value = data.count ?? contents.value.length;
  } finally {
    loading.value = false;
  }
}

function openContent(row) {
  router.push(`/contents/${row.id}`);
}

async function deleteContent(id) {
  await contentAPI.delete(id);
  ElMessage.success("已删除");
  fetchContents();
}

const platformLabel = (p) =>
  ({ weibo: "微博", xiaohongshu: "小红书", wechat_mp: "公众号", wechat_video: "视频号", toutiao: "头条" }[p] ?? p);

const statusType = (s) =>
  ({ draft: "", confirmed: "success", published: "primary" }[s] ?? "info");

const statusLabel = (s) =>
  ({ draft: "草稿", confirmed: "已确认", published: "已发布" }[s] ?? s);

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString("zh-CN") : "-";
}
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 { margin: 0; }
.pagination { margin-top: 16px; justify-content: center; display: flex; }
</style>
