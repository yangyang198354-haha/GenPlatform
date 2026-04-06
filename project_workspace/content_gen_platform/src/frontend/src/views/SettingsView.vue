<template>
  <div class="settings-view">
    <h2>系统设置</h2>

    <el-tabs v-model="activeTab" tab-position="left">
      <!-- LLM Config -->
      <el-tab-pane label="大语言模型" name="llm">
        <el-card>
          <h3>LLM 服务配置</h3>
          <el-form :model="llmForm" label-width="140px">
            <el-form-item label="服务商">
              <el-radio-group v-model="llmForm.provider">
                <el-radio label="deepseek">DeepSeek</el-radio>
                <el-radio label="volcano">火山引擎</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llmForm.api_key" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item v-if="llmForm.provider === 'volcano'" label="模型 ID">
              <el-input v-model="llmForm.model_id" placeholder="ep-xxxxxxxx" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingLlm" @click="saveLlmConfig">保存</el-button>
              <el-button :loading="testingLlm" @click="testLlmConfig">测试连接</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- Jimeng Config -->
      <el-tab-pane label="即梦 API" name="jimeng">
        <el-card>
          <h3>即梦（即创）视频 API</h3>
          <el-form :model="jimengForm" label-width="140px">
            <el-form-item label="Access Key ID">
              <el-input v-model="jimengForm.access_key_id" />
            </el-form-item>
            <el-form-item label="Secret Access Key">
              <el-input v-model="jimengForm.secret_access_key" show-password />
            </el-form-item>
            <el-form-item label="Region">
              <el-input v-model="jimengForm.region" placeholder="cn-north-1" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingJimeng" @click="saveJimengConfig">保存</el-button>
              <el-button :loading="testingJimeng" @click="testJimengConfig">测试连接</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- Storage Config -->
      <el-tab-pane label="存储设置" name="storage">
        <el-card>
          <h3>文件存储</h3>
          <el-form :model="storageForm" label-width="140px">
            <el-form-item label="存储后端">
              <el-radio-group v-model="storageForm.backend">
                <el-radio label="local">本地存储</el-radio>
                <el-radio label="minio">MinIO</el-radio>
              </el-radio-group>
            </el-form-item>
            <template v-if="storageForm.backend === 'minio'">
              <el-form-item label="Endpoint">
                <el-input v-model="storageForm.endpoint" placeholder="http://minio:9000" />
              </el-form-item>
              <el-form-item label="Access Key">
                <el-input v-model="storageForm.access_key" />
              </el-form-item>
              <el-form-item label="Secret Key">
                <el-input v-model="storageForm.secret_key" show-password />
              </el-form-item>
              <el-form-item label="Bucket">
                <el-input v-model="storageForm.bucket" />
              </el-form-item>
            </template>
            <el-form-item>
              <el-button type="primary" :loading="savingStorage" @click="saveStorageConfig">保存</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { settingsAPI } from "@/api";

const activeTab = ref("llm");

const llmForm = ref({ provider: "deepseek", api_key: "", model_id: "" });
const savingLlm = ref(false);
const testingLlm = ref(false);

const jimengForm = ref({ access_key_id: "", secret_access_key: "", region: "cn-north-1" });
const savingJimeng = ref(false);
const testingJimeng = ref(false);

const storageForm = ref({ backend: "local", endpoint: "", access_key: "", secret_key: "", bucket: "content-gen" });
const savingStorage = ref(false);

onMounted(async () => {
  try {
    const [llm, jimeng, storage] = await Promise.allSettled([
      settingsAPI.get("llm"),
      settingsAPI.get("jimeng"),
      settingsAPI.get("storage"),
    ]);
    if (llm.status === "fulfilled") Object.assign(llmForm.value, llm.value.data?.config ?? {});
    if (jimeng.status === "fulfilled") Object.assign(jimengForm.value, jimeng.value.data?.config ?? {});
    if (storage.status === "fulfilled") Object.assign(storageForm.value, storage.value.data?.config ?? {});
  } catch (_) { /* first run, configs may not exist yet */ }
});

async function saveLlmConfig() {
  savingLlm.value = true;
  try {
    await settingsAPI.save("llm", llmForm.value);
    ElMessage.success("LLM 配置已保存");
  } finally { savingLlm.value = false; }
}

async function testLlmConfig() {
  testingLlm.value = true;
  try {
    await settingsAPI.test("llm");
    ElMessage.success("连接测试通过");
  } catch { ElMessage.error("连接测试失败，请检查 API Key"); }
  finally { testingLlm.value = false; }
}

async function saveJimengConfig() {
  savingJimeng.value = true;
  try {
    await settingsAPI.save("jimeng", jimengForm.value);
    ElMessage.success("即梦配置已保存");
  } finally { savingJimeng.value = false; }
}

async function testJimengConfig() {
  testingJimeng.value = true;
  try {
    await settingsAPI.test("jimeng");
    ElMessage.success("连接测试通过");
  } catch { ElMessage.error("连接测试失败"); }
  finally { testingJimeng.value = false; }
}

async function saveStorageConfig() {
  savingStorage.value = true;
  try {
    await settingsAPI.save("storage", storageForm.value);
    ElMessage.success("存储配置已保存");
  } finally { savingStorage.value = false; }
}
</script>

<style scoped>
h2 { margin-bottom: 20px; }
h3 { margin-top: 0; }
</style>
