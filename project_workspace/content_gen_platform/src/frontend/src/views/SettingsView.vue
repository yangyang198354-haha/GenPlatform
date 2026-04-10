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
                <el-radio value="deepseek">DeepSeek</el-radio>
                <el-radio value="volcano">火山引擎（豆包）</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llmForm.api_key" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item v-if="llmForm.provider === 'volcano'" label="模型 ID">
              <el-input v-model="llmForm.model_name" placeholder="ep-xxxxxxxx（火山引擎推理接入点 ID）" />
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
              <el-input v-model="jimengForm.access_key" />
            </el-form-item>
            <el-form-item label="Secret Access Key">
              <el-input v-model="jimengForm.secret_key" show-password />
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
                <el-radio value="local">本地存储</el-radio>
                <el-radio value="minio">MinIO</el-radio>
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
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { settingsAPI } from "@/api";

const activeTab = ref("llm");

// ── LLM ─────────────────────────────────────────────────────────────────────
const llmForm    = ref({ provider: "deepseek", api_key: "", model_name: "" });
const savingLlm  = ref(false);
const testingLlm = ref(false);

// 根据选择的服务商映射到后端 service_type
const llmServiceType = computed(() =>
  llmForm.value.provider === "deepseek" ? "llm_deepseek" : "llm_volcano"
);

async function saveLlmConfig() {
  if (!llmForm.value.api_key) {
    ElMessage.warning("请填写 API Key");
    return;
  }
  if (llmForm.value.provider === "volcano" && !llmForm.value.model_name) {
    ElMessage.warning("火山引擎需要填写模型 ID（推理接入点）");
    return;
  }
  savingLlm.value = true;
  try {
    // 只发后端需要的字段，字段名与后端 _required_keys 一致
    const payload = { api_key: llmForm.value.api_key };
    if (llmForm.value.provider === "volcano") {
      payload.model_name = llmForm.value.model_name;
    }
    await settingsAPI.save(llmServiceType.value, payload);
    ElMessage.success("LLM 配置已保存");
  } catch (e) {
    ElMessage.error(e.response?.data?.error || "保存失败");
  } finally {
    savingLlm.value = false;
  }
}

async function testLlmConfig() {
  testingLlm.value = true;
  try {
    const { data } = await settingsAPI.test(llmServiceType.value);
    if (data.success) {
      ElMessage.success(data.message || "连接测试通过");
    } else {
      ElMessage.error(data.message || "连接测试失败");
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || "连接测试失败，请检查 API Key");
  } finally {
    testingLlm.value = false;
  }
}

// ── Jimeng ──────────────────────────────────────────────────────────────────
const jimengForm    = ref({ access_key: "", secret_key: "" });
const savingJimeng  = ref(false);
const testingJimeng = ref(false);

async function saveJimengConfig() {
  savingJimeng.value = true;
  try {
    await settingsAPI.save("jimeng", {
      access_key: jimengForm.value.access_key,
      secret_key: jimengForm.value.secret_key,
    });
    ElMessage.success("即梦配置已保存");
  } catch (e) {
    ElMessage.error(e.response?.data?.error || "保存失败");
  } finally {
    savingJimeng.value = false;
  }
}

async function testJimengConfig() {
  testingJimeng.value = true;
  try {
    const { data } = await settingsAPI.test("jimeng");
    if (data.success) {
      ElMessage.success(data.message || "连接测试通过");
    } else {
      ElMessage.error(data.message || "连接测试失败");
    }
  } catch (e) {
    ElMessage.error("连接测试失败");
  } finally {
    testingJimeng.value = false;
  }
}

// ── Storage ──────────────────────────────────────────────────────────────────
const storageForm   = ref({ backend: "local", endpoint: "", access_key: "", secret_key: "", bucket: "content-gen" });
const savingStorage = ref(false);

async function saveStorageConfig() {
  savingStorage.value = true;
  try {
    await settingsAPI.save("storage", storageForm.value);
    ElMessage.success("存储配置已保存");
  } catch (e) {
    ElMessage.error(e.response?.data?.error || "保存失败");
  } finally {
    savingStorage.value = false;
  }
}

// ── 初始加载：用 list() 拿所有已配置项，逐一填充表单 ───────────────────────
onMounted(async () => {
  try {
    const { data } = await settingsAPI.list();
    for (const cfg of data) {
      const preview = cfg.config_preview || {};
      if (cfg.service_type === "llm_deepseek" && cfg.is_configured) {
        llmForm.value.provider = "deepseek";
        // preview 里 api_key 已脱敏（sk-xxxx****），仅用于显示状态
        if (preview.api_key) llmForm.value.api_key = preview.api_key;
      } else if (cfg.service_type === "llm_volcano" && cfg.is_configured) {
        llmForm.value.provider = "volcano";
        if (preview.api_key)    llmForm.value.api_key    = preview.api_key;
        if (preview.model_name) llmForm.value.model_name = preview.model_name;
      } else if (cfg.service_type === "jimeng" && cfg.is_configured) {
        if (preview.access_key) jimengForm.value.access_key = preview.access_key;
        if (preview.secret_key) jimengForm.value.secret_key = preview.secret_key;
      }
    }
  } catch (_) {
    // 首次使用，尚无配置，静默处理
  }
});
</script>

<style scoped>
h2 { margin-bottom: 20px; }
h3 { margin-top: 0; margin-bottom: 20px; }
</style>
