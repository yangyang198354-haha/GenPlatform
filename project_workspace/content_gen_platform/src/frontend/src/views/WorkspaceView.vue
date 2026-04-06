<template>
  <div class="workspace">
    <el-row :gutter="24">
      <el-col :span="24">
        <h2>文案创作工作台</h2>
      </el-col>
    </el-row>

    <!-- Generation Form -->
    <el-card class="generation-card">
      <el-form :model="form" label-position="top">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="目标平台">
              <el-select v-model="form.platform" style="width: 100%">
                <el-option label="通用" value="general" />
                <el-option label="微博" value="weibo" />
                <el-option label="小红书" value="xiaohongshu" />
                <el-option label="微信公众号" value="wechat_mp" />
                <el-option label="微信视频号" value="wechat_video" />
                <el-option label="今日头条" value="toutiao" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="文案风格">
              <el-select v-model="form.style" style="width: 100%">
                <el-option label="专业" value="professional" />
                <el-option label="口语化" value="casual" />
                <el-option label="幽默" value="humorous" />
                <el-option label="种草" value="promotion" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="字数限制">
              <el-input-number v-model="form.wordLimit" :min="0" :max="5000"
                placeholder="不限制" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="生成指令">
          <el-input
            v-model="form.prompt"
            type="textarea"
            :rows="4"
            placeholder="请描述你想要生成的文案内容，例如：写一篇关于夏季防晒护肤品的种草文案，突出产品的清爽质地和防晒效果..."
          />
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="form.useKb">使用知识库作为上下文</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="generating" @click="startGeneration"
            :disabled="!form.prompt">
            {{ generating ? '生成中...' : '开始生成' }}
          </el-button>
          <el-button v-if="generating" @click="stopGeneration">停止</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Generated Content -->
    <el-card v-if="generatedText || generating" class="content-card" style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>生成结果</span>
          <span class="word-count">{{ generatedText.length }} 字</span>
        </div>
      </template>

      <el-input
        v-model="generatedText"
        type="textarea"
        :rows="12"
        @input="isDirty = true"
      />

      <div class="action-bar" style="margin-top: 12px">
        <el-input v-model="contentTitle" placeholder="文案标题（可选）" style="width: 300px; margin-right: 12px" />
        <el-button @click="saveDraft" :disabled="!generatedText">保存草稿</el-button>
        <el-button type="success" @click="confirmContent" :disabled="!savedContentId">确认文案</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { contentAPI } from '@/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const form = reactive({
  prompt: '',
  platform: 'general',
  style: 'professional',
  wordLimit: null,
  useKb: true,
})

const generatedText = ref('')
const generating = ref(false)
const contentTitle = ref('')
const savedContentId = ref(null)
const isDirty = ref(false)

let eventSource = null

const startGeneration = () => {
  if (!form.prompt) return

  generatedText.value = ''
  savedContentId.value = null
  generating.value = true

  const params = new URLSearchParams({
    prompt: form.prompt,
    platform: form.platform,
    style: form.style,
    use_kb: form.useKb,
    ...(form.wordLimit ? { word_limit: form.wordLimit } : {}),
  })

  const token = auth.accessToken
  eventSource = new EventSource(
    `/api/v1/llm/generate/?${params.toString()}`,
    { headers: { Authorization: `Bearer ${token}` } }
  )

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.done) {
      generating.value = false
      eventSource.close()
      autoSaveDraft()
    } else {
      generatedText.value += data.token
    }
  }

  eventSource.onerror = () => {
    generating.value = false
    eventSource.close()
    ElMessage.error('生成中断，已保存部分内容')
    if (generatedText.value) autoSaveDraft()
  }
}

const stopGeneration = () => {
  if (eventSource) {
    eventSource.close()
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
      platform_type: form.platform,
      style: form.style,
      word_limit: form.wordLimit,
      generation_prompt: form.prompt,
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
      title: contentTitle.value,
      body: generatedText.value,
    })
  } else {
    await autoSaveDraft()
  }
  ElMessage.success('草稿已保存')
}

const confirmContent = async () => {
  if (!savedContentId.value) return
  await contentAPI.confirm(savedContentId.value)
  ElMessage.success('文案已确认，可以进行发布或视频生成')
}
</script>

<style scoped>
.workspace { padding: 0 }
.generation-card { margin-bottom: 0 }
.card-header { display: flex; justify-content: space-between; align-items: center }
.word-count { color: #909399; font-size: 12px }
.action-bar { display: flex; align-items: center }
</style>
