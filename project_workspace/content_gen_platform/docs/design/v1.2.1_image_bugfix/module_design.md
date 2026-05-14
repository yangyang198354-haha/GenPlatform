# 模块设计文档 v1.2.1 — AI 图片 Bug 修复

**file_header**
- document_id: MOD-v1.2.1
- author_agent: sub_agent_system_architect
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2.1 AI 图片 3 个 Bug 修复
- status: DRAFT
- created_at: 2026-05-14
- input_refs: requirements_spec.md v1.2.1, user_stories.md v1.2.1, v1.2 module_design.md

---

## 1. BUG-01 修复方案：批次缩略图

### 1.1 根因确认

代码证据（`BatchDetailPage.vue` 第 41-56 行）：
```html
<!-- 此处需要通过 media API 获取图片 URL，或从 file_url 展示 -->
<div class="image-placeholder">...</div>
```

代码证据（`serializers.py` ImageGenerationRequestSerializer fields 第 150-162 行）：
```python
fields = ("id", "status", "prompt", "progress", "provider", "model",
          "batch_id", "media_item_id", "error_message", "created_at")
# 缺少：result_image_url / media_item.file.url
```

**根因**：`ImageGenerationRequestSerializer` 未暴露图片 URL，前端无法渲染缩略图。

### 1.2 后端修复方案

**文件**：`apps/image_generator/serializers.py`

在 `ImageGenerationRequestSerializer` 中新增 `result_image_url` 字段，并通过 `SerializerMethodField` 补充 `media_item_url`（优先使用已入库的 MediaItem URL，降级到 Ark CDN URL）：

```python
class ImageGenerationRequestSerializer(serializers.ModelSerializer):
    media_item_id = serializers.PrimaryKeyRelatedField(
        source="media_item", read_only=True
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source="batch", read_only=True
    )
    # 新增：优先 media_item.file.url（持久 URL），降级到 result_image_url（Ark CDN，24h）
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = ImageGenerationRequest
        fields = (
            "id", "status", "prompt", "progress", "provider", "model",
            "batch_id", "media_item_id", "result_image_url",
            "thumbnail_url",           # 新增
            "error_message", "created_at",
        )
        read_only_fields = fields

    def get_thumbnail_url(self, obj):
        """
        优先返回已入库的 MediaItem.file.url（持久存储，不过期）。
        若 MediaItem 不存在或 URL 构建失败，降级到 result_image_url（Ark CDN，约 24h 有效）。
        """
        try:
            if obj.media_item and obj.media_item.file:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(obj.media_item.file.url)
                return obj.media_item.file.url
        except Exception:
            pass
        return obj.result_image_url or ""
```

**注意**：`ImageBatchSerializer` 内嵌 `ImageGenerationRequestSerializer`，需在 View 层传入 `request` context：

```python
# views.py → ImageBatchDetailView.get()
serializer = ImageBatchSerializer(batch, context={"request": request})
```

**向后兼容**：新增字段为只读，不影响现有的 PATCH 接口（仅允许修改 name）。历史即梦数据 `result_image_url=""` + `media_item=null` → `thumbnail_url=""` 不报错。

### 1.3 前端修复方案

**文件**：`src/frontend/src/views/ImageGeneratorView/BatchDetailPage.vue`

将图片网格中的占位符替换为实际图片渲染：

```html
<!-- 已完成的图片 -->
<div
  v-for="req in completedRequests"
  :key="req.id"
  class="image-grid-item"
>
  <!-- 使用 el-image 渲染缩略图（thumbnail_url 优先，支持 Lightbox） -->
  <el-image
    v-if="req.thumbnail_url"
    :src="req.thumbnail_url"
    :preview-src-list="completedImageUrls"
    :initial-index="completedRequests.indexOf(req)"
    class="grid-thumb"
    fit="cover"
    preview-teleported
    loading="lazy"
  />
  <div v-else class="image-placeholder">
    <el-icon class="placeholder-icon"><Picture /></el-icon>
    <span class="media-id">素材 #{{ req.media_item_id }}</span>
  </div>
  <div class="item-status">
    <el-tag type="success" size="small">已完成</el-tag>
  </div>
</div>
```

新增 computed：
```javascript
const completedImageUrls = computed(() =>
  completedRequests.value
    .filter(r => r.thumbnail_url)
    .map(r => r.thumbnail_url)
)
```

**BatchListPage 缩略图（可选，nice-to-have）**：批次列表卡片暂不实现缩略图（需额外 API 调用，影响分页性能）。标记为 v1.3 backlog。

### 1.4 影响边界

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `serializers.py` | 修改 | 新增 `thumbnail_url` SerializerMethodField + `result_image_url` 暴露 |
| `views.py` | 修改 | ImageBatchDetailView 传 `context={"request": request}` |
| `BatchDetailPage.vue` | 修改 | 占位符替换为 el-image |
| `tests/test_serializers.py` | 新增 | thumbnail_url 字段逻辑单测 |
| E2E | 新增 | 批次详情缩略图展示测试 |

---

## 2. BUG-02 修复方案：MediaLibraryView Lightbox 失效

### 2.1 根因确认

**主根因：Hover Overlay 拦截点击（Hypothesis A，确认为主根因）**

代码证据（`MediaLibraryView.vue`）：
- CSS（第 528-533 行）：`.hover-overlay { position: absolute; inset: 0; ... }` —— 完全覆盖 el-image 的点击区域
- el-image 内部预览触发依赖 `.el-image__inner` 的 click 事件
- hover-overlay 使用 `v-show`（不是 `v-if`），始终在 DOM 中，z-index 高于 el-image 内部元素

**当用户 hover 时**：overlay 可见（`inset:0` 覆盖全格），用户点击落在 overlay 上，el-image 的 click 事件未触发 → Lightbox 不弹出。

**次根因：allImageUrls 响应式初始化（Hypothesis B，低危）**：`allImageUrls` computed 在 items 填充后自动更新，el-image 已正确绑定，不是根因。

**E2E 漏测根因**：
- 现有 E2E（`test_media_library_lightbox.spec.ts`，AC-07-1）调用 `elImage.click()`，Playwright 点击 el-image 元素中心坐标。
- 在 Playwright 的 headless 环境中，`v-show` 控制的 overlay 若 CSS 初始 opacity 与 hover state 不同，Playwright 可能未触发 hover → overlay 不可见 → 点击落在 el-image → 测试通过。
- 实际浏览器中用户鼠标移动触发 hover → overlay 出现 → 点击被拦截 → 测试通过但线上失效。

### 2.2 修复方案（三选一，推荐方案 A）

**方案 A（推荐）：拆分点击区域，overlay 对 el-image 部分透传点击**

核心思路：hover-overlay 保留视觉蒙层，但不拦截 el-image 的点击。将删除/下载按钮从 overlay 中提取，仅让按钮区域响应点击，图片区域透传给 el-image。

```html
<div class="media-thumb">
  <el-image
    v-if="item.media_type === 'image'"
    :src="item.file_url"
    :preview-src-list="allImageUrls"
    :initial-index="getImageIndex(item)"
    class="thumb-img"
    fit="cover"
    loading="lazy"
    preview-teleported
  />
  <!-- ... video/audio 分支不变 ... -->

  <!-- Hover Actions Overlay：仅按钮区，不覆盖图片点击区 -->
  <transition name="fade">
    <div v-show="hoveredId === item.id" class="hover-overlay">
      <!-- overlay 本身 pointer-events: none，只有按钮区有事件 -->
      <div class="hover-actions" @click.stop>
        <el-tooltip content="放大查看" placement="top">
          <el-button
            circle size="small" :icon="IconZoomIn"
            @click.stop="openLightbox(item)"
          />
        </el-tooltip>
        <el-tooltip content="下载" placement="top">
          <el-button circle size="small" :icon="IconDownload"
            @click="downloadItem(item)" />
        </el-tooltip>
        <el-tooltip content="删除" placement="top">
          <el-button circle size="small" type="danger" :icon="IconDelete"
            @click="confirmDelete(item)" />
        </el-tooltip>
      </div>
    </div>
  </transition>
</div>
```

CSS 关键修改：
```css
/* overlay 本身不拦截点击，只有 .hover-actions 内按钮响应 */
.hover-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;   /* 关键：overlay 蒙层不拦截点击 */
}

.hover-actions {
  display: flex;
  gap: 10px;
  pointer-events: auto;   /* 按钮区恢复点击 */
}
```

**方案 B（备选）**：在 hover-overlay 内增加"放大"按钮（ZoomIn 图标），点击该按钮调用 `el-image` 的内部 preview 方法（`elImageRef.clickHandler()`）。复杂度较高，需 ref 访问 el-image 实例。

**方案 C（备选）**：将 Lightbox 实现改为自定义 modal（不依赖 el-image preview），el-image 仅用于展示缩略图。引入额外代码量，不推荐。

**选定方案 A 的理由**：
- 最小侵入性：仅改 CSS 一个属性 + 视觉不变
- el-image 的原生 preview-src-list 机制不变，支持多图切换
- 删除/下载按钮功能完整保留（`pointer-events: auto` 在 .hover-actions 上）

### 2.3 E2E 测试修复与补强

**修正现有 AC-07-1**：改为 hover 后点击 `.el-image__inner`（而非 `.el-image`），模拟真实用户操作：
```typescript
await firstCard.hover()
// 等待 hover-overlay 出现
await firstCard.locator('.hover-overlay').waitFor({ state: 'visible' })
// 点击 el-image 内部图片区（不是按钮）
await firstCard.locator('.el-image__inner').click()
```

**新增 AC-B02-4**（按钮点击不触发 Lightbox）：
```typescript
await firstCard.hover()
await firstCard.locator('.hover-actions .el-button').first().click()
// 断言 Lightbox 不弹出
await expect(page.locator('.el-image-viewer__wrapper')).not.toBeVisible()
```

**新增 AC-B02-5**（hover 覆盖状态下点击图片区触发 Lightbox）：
```typescript
await firstCard.hover()
await firstCard.locator('.hover-overlay').waitFor({ state: 'visible' })
await firstCard.locator('.el-image__inner').click()
await expect(page.locator('.el-image-viewer__wrapper')).toBeVisible()
```

### 2.4 影响边界

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `MediaLibraryView.vue` | 修改 | `.hover-overlay` 加 `pointer-events: none`；`.hover-actions` 加 `pointer-events: auto` |
| `test_media_library_lightbox.spec.ts` | 修改+新增 | 修正 AC-07-1 点击策略；新增 AC-B02-4/5 |
| 后端 | 不涉及 | |

---

## 3. BUG-03 修复方案：错误处理与状态恢复

### 3.1 状态机设计

当前 `ImageGeneratorView.vue` 的生成状态由 `isGenerating`（boolean）+ `generationError`（string）控制，是隐式的两变量状态机，存在状态不一致风险。

**修复方案**：保持现有 ref 结构不重构（降低改动范围），但明确每条失败路径的状态重置逻辑，并增加超时保护。

状态转换表：

| 事件 | isGenerating | generationError | 按钮状态 |
|------|-------------|----------------|---------|
| 初始 | false | '' | 可点击 |
| 点击"开始生成" | true | '' | 禁用 |
| POST 失败（catch） | false | errMsg | **可点击** |
| WebSocket image_failed | false（需修复，见3.2） | errMsg | 可点击 |
| WebSocket batch_completed[failed] | false | errMsg | 可点击 |
| WebSocket batch_completed[completed] | false | '' | 可点击 |
| 超时保护触发 | false | '生成超时，请重试' | 可点击 |
| 用户点击"取消" | false | '' | 可点击 |
| 用户点击"重试" (resetGeneration) | false | '' | 可点击 |

### 3.2 Bug-3a：错误信息持久化

**方案**：将 `ElMessage.error(errMsg)` 改为 `duration: 0`（不自动关闭）+ 同时在结果面板显示 ElAlert 常驻。

修改位置（`ImageGeneratorView.vue`）：
```javascript
// submitGeneration catch 块
ElMessage({ type: 'error', message: errMsg, duration: 0, showClose: true })

// handleWebSocketMessage - image_failed
ElMessage({ type: 'error', message: `图片生成失败：${payload.error}`, duration: 0, showClose: true })

// handleWebSocketMessage - batch_completed[failed]
ElMessage({ type: 'error', message: '所有图片生成失败，请稍后重试', duration: 0, showClose: true })
```

右侧结果面板错误区块增强（视觉更明显）：
```html
<div v-else-if="generationError" class="result-error">
  <el-alert
    :title="`生成失败：${generationError}`"
    type="error"
    :closable="false"
    show-icon
    class="error-alert"
  />
  <el-button type="primary" @click="resetGeneration" style="margin-top:12px">
    重新生成
  </el-button>
</div>
```

### 3.3 Bug-3b：按钮失败后永久禁用

**已知代码**：`submitGeneration()` catch 块已有 `isGenerating.value = false`，POST 失败路径 (场景 B) 理论上应正常恢复。

**问题在场景 A（WebSocket 失败）**：
- `handleWebSocketMessage` 的 `image_failed` 分支（第 316-319 行）只设置 `generationError`，未重置 `isGenerating`。
- `batch_completed` 分支的 `status !== 'completed'` 分支（第 328-330 行）有 `isGenerating.value = false`，但仅在 batch_completed 到达时触发。

**修复**：在所有错误路径强制重置 `isGenerating`：
```javascript
if (event_type === 'image_failed') {
  generationError.value = payload.error || '图片生成失败'
  isGenerating.value = false                           // 新增
  ElMessage({ type: 'error', message: `图片生成失败：${payload.error}`, duration: 0, showClose: true })
}
```

**超时保护**：在 `submitGeneration()` 成功后（202 响应）启动超时定时器：
```javascript
// 超时保护：5 分钟内未完成则重置（Ark API 通常 30s 内返回，5min 是安全边界）
const GENERATION_TIMEOUT_MS = 5 * 60 * 1000
let generationTimer = null

// submitGeneration try 块成功后：
currentBatch.value = { ... }
generationTimer = setTimeout(() => {
  if (isGenerating.value) {
    isGenerating.value = false
    generationError.value = '生成超时，请检查网络连接后重试'
    ElMessage({ type: 'warning', message: '生成超时，已自动重置', duration: 0, showClose: true })
  }
}, GENERATION_TIMEOUT_MS)

// handleWebSocketMessage batch_completed 中清理定时器：
clearTimeout(generationTimer)
generationTimer = null

// onUnmounted 中清理：
onUnmounted(() => {
  if (ws) ws.close()
  if (generationTimer) clearTimeout(generationTimer)
})
```

### 3.4 Bug-3c：进度条 + 移除取消按钮（OPEN-02/04 已关闭）

**产品决策**：取消按钮完全移除。失败后 UX 转向"简单重试"模式（见 §3.6）。

#### 3.4.1 进度条 HTTP 降级轮询

WebSocket 不可用时（`ws.onerror` 或连接超时），启动 HTTP 轮询：

```javascript
let pollingTimer = null
const POLLING_INTERVAL_MS = 3000  // 3 秒轮询一次

const startPolling = (batchId) => {
  if (pollingTimer) return
  pollingTimer = setInterval(async () => {
    if (!isGenerating.value) {
      stopPolling()
      return
    }
    try {
      const { data } = await imageAPI.getBatchDetail(batchId)
      // 更新 completedImages（通过 completed requests）
      const completed = (data.requests || []).filter(r => r.status === 'completed')
      completedImages.value = completed.map(r => ({
        request_id: r.id,
        file_url: r.thumbnail_url || r.result_image_url,
        media_item_id: r.media_item_id,
      }))
      // 批次最终态：停止轮询
      if (['completed', 'partial_failed', 'failed'].includes(data.status)) {
        isGenerating.value = false
        if (data.status === 'failed') {
          generationError.value = '图片生成失败，请重试'
        }
        stopPolling()
      }
    } catch {
      // 轮询失败不终止（网络抖动），等下次继续
    }
  }, POLLING_INTERVAL_MS)
}

const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

// WebSocket onerror 触发降级
ws.onerror = () => {
  if (currentBatch.value) {
    startPolling(currentBatch.value.batch_id)
  }
}
```

#### 3.4.2 移除取消按钮（代码定位清单）

**决策**：取消按钮不新增，且若代码中存在相关遗留代码一并清除。

需要 grep 排查并删除的代码定位（执行时以实际搜索结果为准）：

| 类型 | 搜索关键词 | 文件范围 | 处理方式 |
|------|---------|---------|---------|
| Template | `取消` / `cancel-btn` / `cancelGeneration` | `ImageGeneratorView.vue` 及子组件 | 删除 el-button 节点 |
| Script | `cancelGeneration` / `const cancel` | `ImageGeneratorView.vue` | 删除函数定义 |
| State | `isCancelling` / `cancelToken` / `cancelSource` | `ImageGeneratorView.vue` | 删除 ref/state 声明 |
| CSS | `.cancel-btn` | `ImageGeneratorView.vue` 或独立 CSS | 删除样式块 |
| E2E | `取消` / `cancelGeneration` / `cancel-btn` | `e2e/` 目录 | 删除相关 test case |

**进度条失败归零**：失败时（POST catch / image_failed / 超时）执行：
```javascript
// 失败路径统一执行
isGenerating.value = false
// 清空 completedImages 使 batchProgress computed 归零
completedImages.value = []
```

进度条归零而非隐藏（`v-if` 控制的 `isGenerating` 块已隐藏整个进度区域）。

### 3.5 影响边界

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `ImageGeneratorView.vue` | 修改 | ElMessage duration:0；isGenerating 重置；超时保护；轮询降级；**移除取消按钮**；进度条失败归零 |
| 后端 | 不涉及 | 无取消 API（OPEN-04 关闭） |
| E2E | 新增+删除 | Bug-03 AC 覆盖；**删除**取消按钮相关 E2E；新增失败后重试验证 |

### 3.6 失败后重试 UX 状态机（澄清后更新）

更新后的状态机（对比 architecture_design.md §2.1，移除"用户点击取消"分支）：

```
[IDLE]
  ↓ 用户点击"开始生成"
[SUBMITTING] isGenerating=true, completedImages=[]
  ↓ POST 返回 202
[GENERATING] isGenerating=true, currentBatch 已设置
  ├── WebSocket 可用：handleWebSocketMessage 驱动
  │     image_completed → completedImages push
  │     image_failed → isGenerating=false, completedImages=[], generationError=msg → [DONE_ERROR]
  │     batch_completed[success] → clearTimeout → isGenerating=false → [DONE_SUCCESS]
  │     batch_completed[failed] → clearTimeout → isGenerating=false, completedImages=[] → [DONE_ERROR]
  ├── WebSocket 不可用（onerror）→ 启动 HTTP 轮询（3s 间隔）
  │     getBatchDetail → completed_count 更新 completedImages
  │     status=completed/failed → stopPolling → isGenerating=false
  └── 超时保护（5min）→ isGenerating=false, completedImages=[] → [DONE_ERROR: '生成超时']

  ↓ POST 失败（catch）
[DONE_ERROR] isGenerating=false, completedImages=[], generationError 已设置

[DONE_ERROR]
  ↓ 用户修改参数后点击"开始生成"（resetGeneration 自动在 submitGeneration 开头执行）
[IDLE] → [SUBMITTING]
```

**关键差异（vs 原设计）**：
- 删除 `"用户点击取消" → [IDLE]` 分支
- 所有失败路径增加 `completedImages.value = []`（确保进度条归零）
- `[DONE_ERROR]` 的退出路径仅为"再次点击开始生成"

---

## 4. API 契约变更汇总

| 端点 | 变更 | 类型 |
|------|------|------|
| `GET /api/v1/image/batches/{id}/` | response.requests[].thumbnail_url 新增字段 | 向后兼容（新增字段） |
| `GET /api/v1/image/batches/{id}/` | response.requests[].result_image_url 暴露 | 向后兼容（原有字段暴露） |
| `GET /api/v1/image/batches/` | 无变更 | - |
| `POST /api/v1/image/generate/` | 无变更 | - |
| 取消 API | 不新增（前端状态重置） | - |

---

## 5. 单元测试设计（后端）

| 测试文件 | 测试用例 | 覆盖点 |
|---------|---------|-------|
| `tests/test_serializers.py` | `test_request_serializer_thumbnail_url_with_media_item` | media_item 存在时返回入库 URL |
| `tests/test_serializers.py` | `test_request_serializer_thumbnail_url_fallback_to_result_url` | media_item 为 null 时降级到 result_image_url |
| `tests/test_serializers.py` | `test_request_serializer_thumbnail_url_empty_when_both_null` | 两者均空时返回空字符串 |
| `tests/test_views.py` | `test_batch_detail_includes_thumbnail_url` | View 层传 request context 后 thumbnail_url 非空 |
