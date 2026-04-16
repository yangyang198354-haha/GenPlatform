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

            <!-- DeepSeek specific fields -->
            <template v-if="llmForm.provider === 'deepseek'">
              <el-form-item label="模型">
                <el-select v-model="llmForm.deepseek_model" placeholder="选择模型" style="width: 100%">
                  <el-option
                    v-for="m in deepseekModels"
                    :key="m.value"
                    :label="m.label"
                    :value="m.value"
                  />
                </el-select>
                <div class="field-hint">{{ deepseekModelHint }}</div>
              </el-form-item>
              <el-form-item label="Temperature">
                <el-input-number
                  v-model="llmForm.deepseek_temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  :precision="1"
                  style="width: 180px"
                />
                <span class="field-hint" style="margin-left: 8px">范围 0–2，默认 1.0；越高越随机</span>
              </el-form-item>
              <el-form-item label="Max Tokens">
                <el-input-number
                  v-model="llmForm.deepseek_max_tokens"
                  :min="1"
                  :max="8192"
                  :step="256"
                  style="width: 180px"
                />
                <span class="field-hint" style="margin-left: 8px">范围 1–8192，默认 4096</span>
              </el-form-item>
            </template>

            <!-- Volcano specific fields -->
            <template v-if="llmForm.provider === 'volcano'">
              <el-form-item label="豆包模型">
                <el-select v-model="llmForm.doubao_model" placeholder="选择豆包模型系列" style="width: 100%">
                  <el-option
                    v-for="m in volcanoModels"
                    :key="m.value"
                    :label="m.label"
                    :value="m.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="Endpoint ID">
                <el-input
                  v-model="llmForm.model_name"
                  :placeholder="volcanoEndpointPlaceholder"
                />
                <div class="field-hint">在火山引擎控制台"推理接入点"中创建并复制 ID（格式：ep-xxxxxxxx）</div>
              </el-form-item>
              <el-form-item label="Temperature">
                <el-input-number
                  v-model="llmForm.volcano_temperature"
                  :min="0"
                  :max="1"
                  :step="0.1"
                  :precision="1"
                  style="width: 180px"
                />
                <span class="field-hint" style="margin-left: 8px">范围 0–1，默认 0.7</span>
              </el-form-item>
              <el-form-item label="Max Tokens">
                <el-input-number
                  v-model="llmForm.volcano_max_tokens"
                  :min="1"
                  :max="4096"
                  :step="256"
                  style="width: 180px"
                />
                <span class="field-hint" style="margin-left: 8px">范围 1–4096，默认 2048</span>
              </el-form-item>
            </template>

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
import { ref, computed, onMounted, watch } from "vue";
import { ElMessage } from "element-plus";
import { settingsAPI } from "@/api";

const activeTab = ref("llm");

// ── DeepSeek 可选模型列表 ────────────────────────────────────────────────────
const deepseekModels = [
  { value: "deepseek-chat",     label: "deepseek-chat（DeepSeek-V3，通用对话，推荐）" },
  { value: "deepseek-reasoner", label: "deepseek-reasoner（DeepSeek-R1，推理模型）" },
];

// ── 火山引擎（豆包）可选模型列表 ────────────────────────────────────────────
const volcanoModels = [
  { value: "Doubao-pro-4k",       label: "Doubao-pro-4k（专业版，4K 上下文）" },
  { value: "Doubao-pro-32k",      label: "Doubao-pro-32k（专业版，32K 上下文）" },
  { value: "Doubao-pro-128k",     label: "Doubao-pro-128k（专业版，128K 上下文）" },
  { value: "Doubao-lite-4k",      label: "Doubao-lite-4k（轻量版，4K 上下文）" },
  { value: "Doubao-lite-32k",     label: "Doubao-lite-32k（轻量版，32K 上下文）" },
  { value: "Doubao-1.5-pro-32k",  label: "Doubao-1.5-pro-32k（新一代专业版）" },
  { value: "Doubao-1.5-lite-32k", label: "Doubao-1.5-lite-32k（新一代轻量版）" },
];

// ── LLM ─────────────────────────────────────────────────────────────────────
const llmForm = ref({
  provider: "deepseek",
  api_key: "",
  model_name: "",           // volcano endpoint ID
  deepseek_model: "deepseek-chat",
  deepseek_temperature: 1.0,
  deepseek_max_tokens: 4096,
  doubao_model: "Doubao-pro-32k",
  volcano_temperature: 0.7,
  volcano_max_tokens: 2048,
});

// 分别缓存两个 provider 的已保存配置（来自后端 config_preview），
// 避免切换 provider 时互相覆盖同一个 api_key 字段。
const llmSavedConfig = ref({
  deepseek: {
    api_key: "",
    model_name: "deepseek-chat",
    temperature: 1.0,
    max_tokens: 4096,
  },
  volcano: {
    api_key: "",
    model_name: "",
    doubao_model: "Doubao-pro-32k",
    temperature: 0.7,
    max_tokens: 2048,
  },
});

// DeepSeek 模型提示文字
const deepseekModelHint = computed(() => {
  const m = deepseekModels.find(x => x.value === llmForm.value.deepseek_model);
  return m ? "" : "";
});

// 火山引擎 endpoint placeholder：根据选定的豆包模型给出提示
const volcanoEndpointPlaceholder = computed(() => {
  const model = llmForm.value.doubao_model;
  if (!model) return "ep-xxxxxxxx（火山引擎推理接入点 ID）";
  return `ep-xxxxxxxx（${model} 对应的推理接入点 ID）`;
});

// 切换 provider 单选框时，从缓存中回填当前 provider 的配置
watch(() => llmForm.value.provider, (newProvider) => {
  if (newProvider === "deepseek") {
    llmForm.value.api_key             = llmSavedConfig.value.deepseek.api_key;
    llmForm.value.deepseek_model      = llmSavedConfig.value.deepseek.model_name || "deepseek-chat";
    llmForm.value.deepseek_temperature = Number(llmSavedConfig.value.deepseek.temperature) || 1.0;
    llmForm.value.deepseek_max_tokens  = Number(llmSavedConfig.value.deepseek.max_tokens) || 4096;
    llmForm.value.model_name          = "";
  } else {
    llmForm.value.api_key             = llmSavedConfig.value.volcano.api_key;
    llmForm.value.model_name          = llmSavedConfig.value.volcano.model_name;
    llmForm.value.doubao_model        = llmSavedConfig.value.volcano.doubao_model || "Doubao-pro-32k";
    llmForm.value.volcano_temperature = Number(llmSavedConfig.value.volcano.temperature) || 0.7;
    llmForm.value.volcano_max_tokens  = Number(llmSavedConfig.value.volcano.max_tokens) || 2048;
  }
});

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
    let payload;
    if (llmForm.value.provider === "deepseek") {
      payload = {
        api_key:     llmForm.value.api_key,
        model_name:  llmForm.value.deepseek_model || "deepseek-chat",
        temperature: llmForm.value.deepseek_temperature,
        max_tokens:  llmForm.value.deepseek_max_tokens,
      };
    } else {
      payload = {
        api_key:      llmForm.value.api_key,
        model_name:   llmForm.value.model_name,
        doubao_model: llmForm.value.doubao_model,
        temperature:  llmForm.value.volcano_temperature,
        max_tokens:   llmForm.value.volcano_max_tokens,
      };
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
    // 记录哪些 provider 已配置，用于决定最终显示哪个
    let hasDeepseek = false;
    let hasVolcano  = false;
    for (const cfg of data) {
      const preview = cfg.config_preview || {};
      if (cfg.service_type === "llm_deepseek" && cfg.is_configured) {
        hasDeepseek = true;
        if (preview.api_key)     llmSavedConfig.value.deepseek.api_key     = preview.api_key;
        if (preview.model_name)  llmSavedConfig.value.deepseek.model_name  = preview.model_name;
        if (preview.temperature != null) llmSavedConfig.value.deepseek.temperature = preview.temperature;
        if (preview.max_tokens  != null) llmSavedConfig.value.deepseek.max_tokens  = preview.max_tokens;
      } else if (cfg.service_type === "llm_volcano" && cfg.is_configured) {
        hasVolcano = true;
        if (preview.api_key)      llmSavedConfig.value.volcano.api_key      = preview.api_key;
        if (preview.model_name)   llmSavedConfig.value.volcano.model_name   = preview.model_name;
        if (preview.doubao_model) llmSavedConfig.value.volcano.doubao_model = preview.doubao_model;
        if (preview.temperature != null) llmSavedConfig.value.volcano.temperature = preview.temperature;
        if (preview.max_tokens  != null) llmSavedConfig.value.volcano.max_tokens  = preview.max_tokens;
      } else if (cfg.service_type === "jimeng" && cfg.is_configured) {
        if (preview.access_key) jimengForm.value.access_key = preview.access_key;
        if (preview.secret_key) jimengForm.value.secret_key = preview.secret_key;
      }
    }
    // 优先显示已配置的 provider；两者都有则保持默认（deepseek）
    if (!hasDeepseek && hasVolcano) {
      llmForm.value.provider = "volcano";
    }
    // 根据当前 provider 回填表单（watch 此时已注册，但首次设置 provider 可能未触发，
    // 因此手动触发一次回填，确保表单显示正确的缓存值）
    const p = llmForm.value.provider;
    if (p === "deepseek") {
      llmForm.value.api_key             = llmSavedConfig.value.deepseek.api_key;
      llmForm.value.deepseek_model      = llmSavedConfig.value.deepseek.model_name || "deepseek-chat";
      llmForm.value.deepseek_temperature = Number(llmSavedConfig.value.deepseek.temperature) || 1.0;
      llmForm.value.deepseek_max_tokens  = Number(llmSavedConfig.value.deepseek.max_tokens) || 4096;
    } else {
      llmForm.value.api_key             = llmSavedConfig.value.volcano.api_key;
      llmForm.value.model_name          = llmSavedConfig.value.volcano.model_name;
      llmForm.value.doubao_model        = llmSavedConfig.value.volcano.doubao_model || "Doubao-pro-32k";
      llmForm.value.volcano_temperature = Number(llmSavedConfig.value.volcano.temperature) || 0.7;
      llmForm.value.volcano_max_tokens  = Number(llmSavedConfig.value.volcano.max_tokens) || 2048;
    }
  } catch (_) {
    // 首次使用，尚无配置，静默处理
  }
});
</script>

<style scoped>
h2 { margin-bottom: 20px; }
h3 { margin-top: 0; margin-bottom: 20px; }
.field-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}
</style>
