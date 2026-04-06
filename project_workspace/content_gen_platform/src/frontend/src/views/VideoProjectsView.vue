<template>
  <div class="video-projects-view">
    <div class="page-header">
      <h2>视频项目</h2>
    </div>

    <el-table :data="projects" v-loading="loading" stripe @row-click="openProject">
      <el-table-column prop="title" label="项目名称" min-width="200" />
      <el-table-column label="分镜数" width="100">
        <template #default="{ row }">{{ row.scene_count ?? "-" }}</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button size="small" @click.stop="openProject(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !projects.length" description="暂无视频项目，请先生成文案并点击「生成视频」" />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { videoAPI } from "@/api";

const router = useRouter();
const projects = ref([]);
const loading = ref(false);

onMounted(async () => {
  loading.value = true;
  try {
    const { data } = await videoAPI.listProjects();
    projects.value = data.results ?? data;
  } finally {
    loading.value = false;
  }
});

function openProject(row) {
  router.push(`/videos/${row.id}`);
}

const statusType = (s) =>
  ({ pending: "info", generating: "warning", completed: "success", failed: "danger" }[s] ?? "");
const statusLabel = (s) =>
  ({ pending: "待处理", generating: "生成中", completed: "已完成", failed: "失败" }[s] ?? s);

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
</style>
