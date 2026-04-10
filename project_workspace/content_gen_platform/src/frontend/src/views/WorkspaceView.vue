<template>
  <div class="workspace">

    <!-- Page header -->
    <div class="ws-header">
      <div>
        <h2 class="ws-title">文案创作工作台</h2>
        <p class="ws-desc">输入创作指令，AI 将为你生成专业文案内容</p>
      </div>
      <div class="ws-header-tags">
        <span class="platform-badge" v-if="form.platform !== 'general'">
          {{ platformLabel }}
        </span>
        <span class="style-badge">{{ styleLabel }}</span>
      </div>
    </div>

    <!-- Generation Form -->
    <div class="ws-card form-card">
      <div class="card-title-row">
        <span class="card-title">
          <el-icon style="color:var(--brand-primary)"><Edit /></el-icon>
          创作参数
        </span>
      </div>

      <el-form :model="form" label-position="top">
        <div class="param-row">
          <el-form-item label="目标平台" class="param-item">
            <el-select v-model="form.platform" style="width:100%">
              <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value">
                <span>{{ p.emoji }} {{ p.label }}</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="文案风格" class="param-item">
            <el-select v-model="form.style" style="width:100%">
              <el-option v-for="s in styles" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="字数限制" class="param-item">
            <el-input-number
              v-model="form.wordLimit"
              :min="0" :max="5000"
              placeholder="不限制"
              controls-position="right"
              style="width:100%"
            />
          </el-form-item>
        </div>

        <el-form-item label="创作指令">
          <el-input
            v-model="form.prompt"
            type="textarea"
            :rows="4"
            placeholder="描述你想生成的文案，例如：写一篇关于夏季防晒护肤品的种草文案，突出清爽质地和防晒效果，结尾加购买引导..."
            class="prompt-input"
          />
        </el-form-item>

        <div class="form-bottom">
          <label class="kb-checkbox">
            <el-checkbox v-model="form.useKb" />
            <span>
              <el-icon style="font-size:13px;vertical-align:middle;color:var(--brand-primary)"><Document /></el-icon>
              引用知识库上下文
            </span>
          </label>
          <div class="form-actions">
            <el-button v-if="generating" @click="stopGeneration" plain>
              <el-icon><VideoPause /></el-icon> 停止生成
            </el-button>
            <el-button
              type="primary"
              :loading="generating"
              :disabled="!form.prompt"
              @click="startGeneration"
              class="generate-btn"
            >
              <el-icon v-if="!generating"><MagicStick /></el-icon>
              {{ generating ? '生成中...' : '开始生成' }}
            </el-button>
          </div>
        </div>
      </el-form>
    </div>

    <!-- Result Card -->
    <transition name="result-reveal">
      <div v-if="generatedText || generating" class="ws-card result-card">
        <div class="card-title-row">
          <span class="card-title">
            <el-icon style="color:#10b981"><SuccessFilled /></el-icon>
            生成结果
          </span>
          <div class="result-meta">
            <span class="word-count-badge">{{ generatedText.length }} 字</span>
            <span v-if="generating" class="generating-indicator">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </span>
          </div>
        </div>

        <el-input
          v-model="generatedText"
          type="textarea"
          :rows="12"
          class="result-textarea"
          @input="isDirty = true"
        />

        <div class="save-row">
          <el-input
            v-model="contentTitle"
            placeholder="为文案起个标题（可选）"
            class="title-input"
            :prefix-icon="Edit"
          />
          <div class="save-actions">
            <el-button @click="saveDraft" :disabled="!generatedText" plain>
              <el-icon><FolderAdd /></el-icon> 保存草稿
            </el-button>
            <el-button
              type="success"
              @click="confirmContent"
              :disabled="!savedContentId"
            >
              <el-icon><CircleCheckFilled /></el-icon> 确认文案
            </el-button>
          </div>
        </div>

        <div v-if="savedContentId" class="saved-hint">
          <el-icon><CircleCheck /></el-icon>
          草稿已保存 · 确认后可发布或生成视频
        </div>
      </div>
    </transition>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Edit, Document, MagicStick, VideoPause,
  SuccessFilled, FolderAdd, CircleCheckFilled, CircleCheck,
} from '@element-plus/icons-vue'
import { contentAPI } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const platforms = [
  { value: 'general',      label: '通用',       emoji: '🌐' },
  { value: 'weibo',        label: '微博',        emoji: '🔴' },
  { value: 'xiaohongshu',  label: '小红书',      emoji: '📕' },
  { value: 'wechat_mp',    label: '微信公众号',  emoji: '💚' },
  { value: 'wechat_video', label: '微信视频号',  emoji: '🎬' },
  { value: 'toutiao',      label: '今日头条',    emoji: '🔔' },
]
const styles = [
  { value: 'professional', label: '专业严谨' },
  { value: 'casual',       label: '口语化'   },
  { value: 'humorous',     label: '幽默风趣' },
  { value: 'promotion',    label: '种草推广' },
]

const form = reactive({
  prompt: '', platform: 'general', style: 'professional',
  wordLimit: null, useKb: true,
})

const generatedText  = ref('')
const generating     = ref(false)
const contentTitle   = ref('')
const savedContentId = ref(null)
const isDirty        = ref(false)

const platformLabel = computed(() => platforms.find(p => p.value === form.platform)?.label || '')
const styleLabel    = computed(() => styles.find(s => s.value === form.style)?.label || '')

let abortController = null

const startGeneration = async () => {
  if (!form.prompt) return
  generatedText.value  = ''
  savedContentId.value = null
  generating.value     = true

  const params = new URLSearchParams({
    prompt: form.prompt, platform: form.platform,
    style: form.style, use_kb: form.useKb,
    ...(form.wordLimit ? { word_limit: form.wordLimit } : {}),
  })

  abortController = new AbortController()

  try {
    const response = await fetch(`/api/v1/llm/generate/?${params}`, {
      headers: { Authorization: `Bearer ${auth.accessToken}` },
      signal: abortController.signal,
    })

    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err.error || `请求失败 (${response.status})`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()   // keep the last (possibly incomplete) line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = JSON.parse(line.slice(6))
        if (data.done) {
          generating.value = false
          if (data.error) {
            ElMessage.error(data.error || '生成失败，请检查 LLM 配置')
          } else {
            autoSaveDraft()
          }
        } else {
          generatedText.value += data.token
        }
      }
    }
    // Stream closed — ensure generating flag is always reset even if done event was missed
    if (generating.value) {
      generating.value = false
      if (generatedText.value) autoSaveDraft()
      else ElMessage.error('生成中断，请检查 LLM 配置是否正确')
    }
  } catch (e) {
    if (e.name === 'AbortError') return   // user pressed stop — handled in stopGeneration
    generating.value = false
    ElMessage.error(e.message || '生成失败，请重试')
    if (generatedText.value) autoSaveDraft()
  } finally {
    abortController = null
  }
}

const stopGeneration = () => {
  if (abortController) {
    abortController.abort()
    abortController = null
    generating.value = false
    if (generatedText.value) autoSaveDraft()
  }
}

const autoSaveDraft = async () => {
  if (!generatedText.value) return
  try {
    const { data } = await contentAPI.create({
      title: contentTitle.value || '草稿',
      body: generatedText.value,
      platform_type: form.platform, style: form.style,
      word_limit: form.wordLimit, generation_prompt: form.prompt,
    })
    savedContentId.value = data.id
    ElMessage.success('草稿已自动保存')
  } catch {
    ElMessage.warning('草稿保存失败，请手动保存')
  }
}

const saveDraft = async () => {
  if (savedContentId.value) {
    await contentAPI.update(savedContentId.value, {
      title: contentTitle.value, body: generatedText.value,
    })
    ElMessage.success('草稿已保存')
  } else {
    await autoSaveDraft()
  }
}

const confirmContent = async () => {
  if (!savedContentId.value) return
  await contentAPI.confirm(savedContentId.value)
  ElMessage.success('文案已确认，可进行发布或生成视频')
}

onUnmounted(() => { if (abortController) { abortController.abort(); abortController = null } })
</script>

<style scoped>
.workspace { padding: 0; }

/* Header */
.ws-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}
.ws-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
  letter-spacing: -0.02em;
}
.ws-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}
.ws-header-tags {
  display: flex;
  gap: 6px;
  align-items: center;
  padding-top: 4px;
}
.platform-badge, .style-badge {
  font-size: 12px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--el-color-primary-light-9);
  color: var(--brand-primary);
  border: 1px solid var(--el-color-primary-light-7);
}
.style-badge {
  background: #f0fdf4;
  color: #16a34a;
  border-color: #bbf7d0;
}

/* Card */
.ws-card {
  background: var(--surface-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 16px;
  transition: box-shadow var(--transition);
}
.ws-card:hover { box-shadow: var(--shadow); }
.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Params row */
.param-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 4px;
}
.param-item :deep(.el-form-item__label) {
  padding-bottom: 6px;
}

/* Prompt input */
.prompt-input :deep(.el-textarea__inner) {
  font-size: 14px;
  line-height: 1.7;
  resize: none;
}

/* Bottom row */
.form-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}
.kb-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  user-select: none;
}
.form-actions { display: flex; gap: 8px; }
.generate-btn {
  padding: 0 20px !important;
  font-weight: 600 !important;
}

/* Result */
.result-card { }
.result-meta { display: flex; align-items: center; gap: 10px; }
.word-count-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-primary);
  background: var(--el-color-primary-light-9);
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--el-color-primary-light-7);
}

/* Generating dots */
.generating-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--brand-primary);
  animation: dot-bounce 1.2s ease-in-out infinite;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.5; }
  40%            { transform: scale(1);   opacity: 1;   }
}

.result-textarea :deep(.el-textarea__inner) {
  font-family: 'Inter', monospace;
  font-size: 14px;
  line-height: 1.8;
  background: #fafbff;
  resize: vertical;
}

/* Save row */
.save-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}
.title-input { flex: 1; }
.save-actions { display: flex; gap: 8px; flex-shrink: 0; }

.saved-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  color: #16a34a;
  font-weight: 500;
}

/* Transition */
.result-reveal-enter-active { animation: fadeInUp 300ms cubic-bezier(0.4,0,0.2,1) forwards; }
.result-reveal-leave-active { animation: fadeIn 150ms reverse forwards; }
</style>
