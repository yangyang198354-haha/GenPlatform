<template>
  <div class="content-detail-view" v-loading="loading">
    <el-page-header @back="$router.back()" :content="`内容 #${contentId}`" />

    <el-card class="detail-card" v-if="content">
      <div class="meta-row">
        <el-tag>{{ platformLabel(content.platform_type) }}</el-tag>
        <el-tag :type="statusType(content.status)">{{ statusLabel(content.status) }}</el-tag>
        <span class="word-count">{{ content.body?.length ?? 0 }} 字</span>
      </div>

      <el-input
        v-model="content.body"
        type="textarea"
        :autosize="{ minRows: 10 }"
        :disabled="content.status === 'confirmed'"
        @input="markDirty"
        class="body-editor"
      />

      <div class="actions">
        <el-button
          v-if="isDirty"
          type="primary"
          :loading="saving"
          @click="saveDraft"
        >
          保存草稿
        </el-button>
        <el-button
          v-if="content.status === 'draft'"
          type="success"
          @click="confirmContent"
        >
          确认文案
        </el-button>
        <el-button
          v-if="content.status === 'confirmed'"
          type="warning"
          @click="showPublishDialog = true"
        >
          发布到平台
        </el-button>
        <el-button
          v-if="content.status === 'confirmed'"
          @click="generateVideo"
        >
          生成视频
        </el-button>
      </div>
    </el-card>

    <!-- Publish dialog -->
    <el-dialog v-model="showPublishDialog" title="发布配置" width="480px">
      <el-form label-position="top">
        <el-form-item label="选择平台账号">
          <el-checkbox-group v-model="selectedAccounts">
            <el-checkbox
              v-for="acc in platformAccounts"
              :key="acc.id"
              :label="acc.id"
            >
              {{ acc.platform_type_display }} — {{ acc.account_name }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="定时发布（留空则立即发布）">
          <el-date-picker
            v-model="scheduledAt"
            type="datetime"
            placeholder="选择时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPublishDialog = false">取消</el-button>
        <el-button type="primary" :loading="publishing" @click="submitPublish">
          确认发布
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { contentAPI, publisherAPI, videoAPI } from "@/api";

const route = useRoute();
const router = useRouter();
const contentId = route.params.id;

const content = ref(null);
const loading = ref(false);
const saving = ref(false);
const isDirty = ref(false);
const showPublishDialog = ref(false);
const publishing = ref(false);
const platformAccounts = ref([]);
const selectedAccounts = ref([]);
const scheduledAt = ref(null);

onMounted(async () => {
  loading.value = true;
  try {
    const [{ data: c }, { data: accounts }] = await Promise.all([
      contentAPI.get(contentId),
      publisherAPI.listAccounts(),
    ]);
    content.value = c;
    platformAccounts.value = accounts.results ?? accounts;
  } finally {
    loading.value = false;
  }
});

function markDirty() {
  isDirty.value = true;
  // auto-reverts to draft on server side if was confirmed
}

async function saveDraft() {
  saving.value = true;
  try {
    const { data } = await contentAPI.update(contentId, { body: content.value.body });
    content.value = data;
    isDirty.value = false;
    ElMessage.success("已保存");
  } finally {
    saving.value = false;
  }
}

async function confirmContent() {
  const { data } = await contentAPI.confirm(contentId);
  content.value = data;
  ElMessage.success("文案已确认");
}

async function submitPublish() {
  if (!selectedAccounts.value.length) {
    ElMessage.warning("请至少选择一个平台账号");
    return;
  }
  publishing.value = true;
  try {
    await publisherAPI.create({
      content: contentId,
      platform_accounts: selectedAccounts.value,
      scheduled_at: scheduledAt.value || null,
    });
    ElMessage.success("发布任务已提交");
    showPublishDialog.value = false;
  } finally {
    publishing.value = false;
  }
}

async function generateVideo() {
  const { data } = await videoAPI.createProject({
    content: contentId,
    title: `视频 — 内容#${contentId}`,
  });
  router.push(`/videos/${data.id}`);
}

const platformLabel = (p) =>
  ({ weibo: "微博", xiaohongshu: "小红书", wechat_mp: "公众号", wechat_video: "视频号", toutiao: "头条" }[p] ?? p);
const statusType = (s) =>
  ({ draft: "", confirmed: "success", published: "primary" }[s] ?? "info");
const statusLabel = (s) =>
  ({ draft: "草稿", confirmed: "已确认", published: "已发布" }[s] ?? s);
</script>

<style scoped>
.content-detail-view { }
.detail-card { margin-top: 16px; }
.meta-row { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.word-count { color: #909399; font-size: 13px; margin-left: auto; }
.body-editor { margin-bottom: 16px; }
.actions { display: flex; gap: 8px; }
</style>
