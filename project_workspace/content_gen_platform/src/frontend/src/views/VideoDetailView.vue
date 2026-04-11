<template>
  <div class="video-detail" v-if="project">
    <el-page-header @back="$router.back()" :content="`视频项目 #${project.id}`" />

    <el-alert v-if="continuityIssues.length" type="warning" :closable="false" style="margin: 16px 0">
      <div v-for="issue in continuityIssues" :key="issue.scene_index">
        ⚠️ {{ issue.issue_description }}
      </div>
    </el-alert>

    <!-- Scene List -->
    <el-card style="margin-top: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>分镜列表（总时长：{{ totalDuration }}秒）</span>
          <div>
            <el-button type="primary" @click="generateVideo"
              :disabled="project.status === 'generating'"
              :loading="project.status === 'generating'">
              {{ project.status === 'generating' ? '生成中...' : '开始生成视频' }}
            </el-button>
            <el-button v-if="project.status === 'completed'" type="success" @click="exportVideo">
              导出视频
            </el-button>
          </div>
        </div>
      </template>

      <el-progress v-if="project.status === 'generating'" :percentage="videoProgress"
        status="active" style="margin-bottom: 16px" />

      <draggable v-model="scenes" item-key="id" handle=".drag-handle" @end="onReorder">
        <template #item="{ element: scene, index }">
          <el-card class="scene-card" v-if="!scene.is_deleted" shadow="never">
            <div class="scene-header">
              <el-icon class="drag-handle" style="cursor: grab"><Rank /></el-icon>
              <span class="scene-num">第 {{ index + 1 }} 镜</span>
              <el-tag size="small">{{ scene.duration_sec }}秒</el-tag>
              <el-tag size="small" type="info">{{ transitionLabel(scene.transition) }}</el-tag>
              <el-button type="danger" size="small" text @click="deleteScene(scene)">删除</el-button>
            </div>

            <el-row :gutter="16" style="margin-top: 12px">
              <el-col :span="12">
                <div class="field-label">画面提示词（英文）</div>
                <el-input v-model="scene.scene_prompt" type="textarea" :rows="3"
                  @blur="updateScene(scene)" />
              </el-col>
              <el-col :span="12">
                <div class="field-label">配音文案</div>
                <el-input v-model="scene.narration" type="textarea" :rows="3"
                  @blur="updateScene(scene)" />
              </el-col>
            </el-row>

            <el-row :gutter="16" style="margin-top: 8px">
              <el-col :span="8">
                <div class="field-label">时长（秒）</div>
                <el-slider v-model="scene.duration_sec" :min="2" :max="10" :step="1"
                  show-input @change="updateScene(scene)" />
              </el-col>
              <el-col :span="8">
                <div class="field-label">转场方式</div>
                <el-select v-model="scene.transition" @change="updateScene(scene)">
                  <el-option label="硬切" value="cut" />
                  <el-option label="淡入淡出" value="fade" />
                  <el-option label="推拉" value="push_pull" />
                </el-select>
              </el-col>
              <el-col :span="8" v-if="scene.jimeng_clip_url">
                <video :src="scene.jimeng_clip_url" controls style="width: 100%; max-height: 120px" />
              </el-col>
            </el-row>
          </el-card>
        </template>
      </draggable>
    </el-card>

    <!-- Final Video Preview -->
    <el-card v-if="project.final_video_path" style="margin-top: 16px">
      <template #header>最终视频</template>
      <video :src="project.final_video_path" controls style="width: 100%" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Rank } from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import { videoAPI } from '@/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const project = ref(null)
const scenes = ref([])
const continuityIssues = ref([])
const videoProgress = ref(0)
let ws = null

const totalDuration = computed(() =>
  scenes.value.filter(s => !s.is_deleted).reduce((sum, s) => sum + s.duration_sec, 0)
)

const transitionLabel = (t) => ({ cut: '硬切', fade: '淡出', push_pull: '推拉' }[t] || t)

onMounted(async () => {
  await loadProject()
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) ws.close()
})

const loadProject = async () => {
  const { data } = await videoAPI.getProject(route.params.id)
  project.value = data
  scenes.value = data.scenes || []
}

const connectWebSocket = () => {
  const token = auth.accessToken
  ws = new WebSocket(`ws://${location.host}/ws/notifications/`)
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.event_type === 'video_progress' && msg.payload.project_id === project.value.id) {
      videoProgress.value = msg.payload.progress
    }
    if (msg.event_type === 'video_completed' && msg.payload.project_id === project.value.id) {
      loadProject()
      ElMessage.success('视频生成完成！')
    }
    if (msg.event_type === 'video_failed' && msg.payload.project_id === project.value.id) {
      project.value.status = 'failed'
      ElMessage.error(`视频生成失败：${msg.payload.error}`)
    }
  }
}

const generateVideo = async () => {
  await videoAPI.generate(project.value.id)
  project.value.status = 'generating'
  videoProgress.value = 0
}

const exportVideo = async () => {
  const { data } = await videoAPI.exportVideo(project.value.id)
  ElMessage.success('视频合成中，完成后可下载')
  window.open(data.download_url)
}

const updateScene = async (scene) => {
  await videoAPI.updateScene(project.value.id, scene.id, {
    scene_prompt: scene.scene_prompt,
    narration: scene.narration,
    duration_sec: scene.duration_sec,
    transition: scene.transition,
  })
}

const deleteScene = async (scene) => {
  await videoAPI.deleteScene(project.value.id, scene.id)
  scene.is_deleted = true
}

const onReorder = async () => {
  const ids = scenes.value.filter(s => !s.is_deleted).map(s => s.id)
  await videoAPI.reorderScenes(project.value.id, ids)
}
</script>

<style scoped>
.scene-card { margin-bottom: 12px }
.scene-header { display: flex; align-items: center; gap: 8px }
.scene-num { font-weight: 600 }
.field-label { font-size: 12px; color: #909399; margin-bottom: 4px }
</style>
