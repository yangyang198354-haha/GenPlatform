<template>
  <div class="publish-view">
    <div class="page-header">
      <h2>发布任务</h2>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="发布记录" name="tasks">
        <el-table :data="tasks" v-loading="loading" stripe>
          <el-table-column label="内容" min-width="180">
            <template #default="{ row }">
              <router-link :to="`/contents/${row.content}`">内容 #{{ row.content }}</router-link>
            </template>
          </el-table-column>
          <el-table-column label="平台账号" width="150">
            <template #default="{ row }">{{ row.platform_account_display }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="taskStatusType(row.status)">{{ taskStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="定时发布" width="160">
            <template #default="{ row }">{{ row.scheduled_at ? formatDate(row.scheduled_at) : "立即" }}</template>
          </el-table-column>
          <el-table-column label="发布时间" width="160">
            <template #default="{ row }">{{ formatDate(row.published_at) }}</template>
          </el-table-column>
          <el-table-column label="帖子链接" width="120">
            <template #default="{ row }">
              <a v-if="row.platform_post_url" :href="row.platform_post_url" target="_blank">查看</a>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="平台账号管理" name="accounts">
        <div class="account-actions">
          <el-button type="primary" :icon="Plus" @click="showAddAccount = true">添加账号</el-button>
        </div>
        <el-table :data="accounts" v-loading="loadingAccounts" stripe>
          <el-table-column label="平台" width="120">
            <template #default="{ row }">
              <el-tag>{{ platformLabel(row.platform_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="account_name" label="账号名称" min-width="160" />
          <el-table-column label="绑定时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-popconfirm title="确认解绑？" @confirm="deleteAccount(row.id)">
                <template #reference>
                  <el-button type="danger" size="small">解绑</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- Add account dialog -->
    <el-dialog v-model="showAddAccount" title="添加平台账号" width="500px">
      <el-form :model="accountForm" label-position="top">
        <el-form-item label="平台">
          <el-select v-model="accountForm.platform_type" placeholder="选择平台">
            <el-option label="微博" value="weibo" />
            <el-option label="小红书" value="xiaohongshu" />
            <el-option label="微信公众号" value="wechat_mp" />
            <el-option label="微信视频号" value="wechat_video" />
            <el-option label="头条" value="toutiao" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号名称">
          <el-input v-model="accountForm.account_name" />
        </el-form-item>
        <el-form-item label="凭证（JSON 格式）">
          <el-input
            v-model="accountForm.credentials_json"
            type="textarea"
            :rows="6"
            placeholder='{"access_token": "...", "app_key": "..."}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddAccount = false">取消</el-button>
        <el-button type="primary" :loading="addingAccount" @click="submitAccount">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { publisherAPI } from "@/api";

const activeTab = ref("tasks");
const tasks = ref([]);
const loading = ref(false);
const accounts = ref([]);
const loadingAccounts = ref(false);
const showAddAccount = ref(false);
const addingAccount = ref(false);
const accountForm = ref({ platform_type: "", account_name: "", credentials_json: "" });

onMounted(async () => {
  loading.value = true;
  loadingAccounts.value = true;
  try {
    const [{ data: t }, { data: a }] = await Promise.all([
      publisherAPI.listTasks(),
      publisherAPI.listAccounts(),
    ]);
    tasks.value = t.results ?? t;
    accounts.value = a.results ?? a;
  } finally {
    loading.value = false;
    loadingAccounts.value = false;
  }
});

async function submitAccount() {
  try {
    JSON.parse(accountForm.value.credentials_json);
  } catch {
    ElMessage.error("凭证格式不是有效 JSON");
    return;
  }
  addingAccount.value = true;
  try {
    await publisherAPI.createAccount({
      platform_type: accountForm.value.platform_type,
      account_name: accountForm.value.account_name,
      credentials: JSON.parse(accountForm.value.credentials_json),
    });
    ElMessage.success("账号添加成功");
    showAddAccount.value = false;
    const { data } = await publisherAPI.listAccounts();
    accounts.value = data.results ?? data;
  } finally {
    addingAccount.value = false;
  }
}

async function deleteAccount(id) {
  await publisherAPI.deleteAccount(id);
  accounts.value = accounts.value.filter((a) => a.id !== id);
  ElMessage.success("已解绑");
}

const platformLabel = (p) =>
  ({ weibo: "微博", xiaohongshu: "小红书", wechat_mp: "公众号", wechat_video: "视频号", toutiao: "头条" }[p] ?? p);

const taskStatusType = (s) =>
  ({ pending: "info", running: "warning", success: "success", failed: "danger" }[s] ?? "");
const taskStatusLabel = (s) =>
  ({ pending: "待执行", running: "执行中", success: "成功", failed: "失败" }[s] ?? s);

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
.account-actions { margin-bottom: 12px; }
</style>
