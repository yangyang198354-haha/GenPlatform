# 需求规格说明书 v1.2.1 — AI 图片 Bug 修复

**file_header**
- document_id: REQ-SPEC-v1.2.1
- author_agent: sub_agent_requirement_analyst
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2.1 AI 图片 3 个 Bug 修复
- status: DRAFT
- created_at: 2026-05-14
- input_refs: v1.2 requirements_spec.md, v1.2 module_design.md, 用户原始反馈

---

## 1. 背景与范围

v1.2 已上线，合并到 main 并完成物理部署。本次 v1.2.1 为 bug 修复小版本，修复以下 3 个生产问题：

| Bug ID | 简述 | 影响模块 |
|--------|------|---------|
| BUG-01 | 批次管理列表看不到缩略图 | 前端 BatchDetailPage / 后端 ImageBatchDetailView |
| BUG-02 | 素材库点击图片无法放大（Lightbox 回归） | 前端 MediaLibraryView |
| BUG-03 | 错误处理与状态恢复 3 个子问题（3a/3b/3c） | 前端 ImageGeneratorView |

---

## 2. BUG-01：批次管理看不到缩略图

### 2.1 现象描述

**用户原话**：AI 图片"批次管理"列表里每个批次应该显示该批次生成的图片缩略图（可能是首图或网格预览），目前看不到。

**期望行为**：批次管理页（"批次管理" Tab → 点击某批次 → BatchDetailPage 弹窗）中，已完成的图片应以缩略图形式展示，而非仅显示"素材 #ID"占位符。

### 2.2 根因假设（待开发期 verify）

通过阅读 `BatchDetailPage.vue`（第 41-56 行），发现明确的 TODO 注释：

```html
<!-- 此处需要通过 media API 获取图片 URL，或从 file_url 展示 -->
<div class="image-placeholder">
  <el-icon class="placeholder-icon"><Picture /></el-icon>
  <span class="media-id">素材 #{{ req.media_item_id }}</span>
</div>
```

**Hypothesis A（高置信度）**：`BatchDetailPage.vue` 的图片网格使用占位符 `image-placeholder` 而非真实 `<img>` 或 `<el-image>` 渲染，属于 v1.2 开发期留下的未完成 TODO。
- 证据：`ImageGenerationRequestSerializer` 的 `fields` 包含 `media_item_id`，但不含 `file_url`（`result_image_url` 字段未暴露给列表接口）。

**Hypothesis B（需 verify）**：`ImageBatchSerializer` 的 `requests` 嵌套序列化器（`ImageGenerationRequestSerializer`）只暴露 `media_item_id`，没有暴露图片 URL，导致前端拿不到可渲染的 URL。

**影响评估**：
- 前端：`BatchDetailPage.vue` 模板层需改写
- 后端：`ImageGenerationRequestSerializer` 可能需新增 `result_image_url` 字段，或通过 `media_item.file.url` 字段补全

### 2.3 修复目标（可验证标准）

1. 批次详情弹窗中，已完成（status=completed）的图片以缩略图形式展示（`<el-image>` 或 `<img>`）
2. 缩略图来源优先级：`media_item.file_url`（已入库的最终 URL）> `result_image_url`（Ark CDN URL，可能 24h 失效）
3. 失败（status=failed）的图片仍显示错误占位符
4. 批次列表页（BatchListPage）也应显示首图预览缩略图（可选，nice-to-have）

### 2.4 影响范围

| 层 | 影响 |
|----|------|
| 后端 serializer | `ImageGenerationRequestSerializer` 新增图片 URL 字段 |
| 后端 model | `ImageGenerationRequest.result_image_url` 已有；`media_item` FK 已有 |
| 前端 BatchDetailPage | 图片网格渲染逻辑改写（占位符 → 真实图片） |
| 前端 BatchListPage（可选） | 批次卡片新增首图预览 |
| E2E 测试 | 新增批次详情缩略图显示测试 |

---

## 3. BUG-02：素材库点击图片无法放大（v1.2 回归）

### 3.1 现象描述

**用户反馈**：媒体库 `/media-library` 选择"图片"分类后，点击单张图片不能放大查看，仍然只显示删除和下载按钮。

**期望行为**：点击图片缩略图应弹出 Lightbox（el-image 预览弹层），支持全屏查看、Esc 关闭、蒙层点击关闭。

### 3.2 根因假设（待开发期 verify）

通过阅读 `MediaLibraryView.vue`（第 44-55 行）和 E2E 测试（`test_media_library_lightbox.spec.ts`），发现：

**代码实现层面**：`el-image` 已配置 `:preview-src-list="allImageUrls"` 和 `preview-teleported`，理论上应正常工作。

**Hypothesis A（高置信度）**：Hover Overlay 覆盖拦截了点击事件。
- 证据：`hover-overlay` div 使用 `position: absolute; inset: 0`（第 528-533 行），完全覆盖 `el-image` 的点击区域。
- 当鼠标悬停时（`v-show="hoveredId === item.id"`），overlay 完全覆盖 el-image，用户点击实际上击中的是 `hover-overlay`，而非 el-image 的可点击区域。
- el-image 的预览模式靠内部的 `.el-image__inner.el-image__preview` 响应 click，但 overlay 的 z-index 将其截断。

**Hypothesis B（中置信度）**：`allImageUrls` computed 在首次渲染时为空数组。
- 证据：`allImageUrls` 依赖 `items.value`，而 `items` 在 `fetchItems()` 异步完成后才填充。若 el-image 初始化时 `preview-src-list=[]`，部分版本的 Element Plus 会禁用预览功能。

**Hypothesis C（低置信度）**：el-image 组件的 `preview-src-list` 为空（条件渲染或数据问题）。

**E2E 漏测分析**：
- 现有 E2E（`test_media_library_lightbox.spec.ts`）使用 `.el-image.click()` 直接点击 el-image，但浏览器实际接收点击的是最顶层元素（hover-overlay）。
- Playwright 的 `.click()` 会点击元素的中心点，若 overlay 覆盖其上且被 Playwright 认为可见，则点击落在 overlay 上，而非 el-image 内部的预览触发区。
- E2E 通过 Mock 数据能看到 el-image 渲染，但无法感知 overlay 拦截点击的 UX 问题 → **漏测根因：测试点击的目标层与用户真实点击层不一致**。

### 3.3 修复目标（可验证标准）

1. 点击图片缩略图（无论 hover 状态与否）能触发 Lightbox
2. Lightbox 弹出后显示原图
3. Esc 键 / 蒙层点击可关闭
4. Hover overlay（删除/下载）不受影响，关闭 Lightbox 后仍可操作

### 3.4 影响范围

| 层 | 影响 |
|----|------|
| 前端 MediaLibraryView | 修复点击拦截：overlay 的 pointer-events / z-index 调整，或在 overlay 内单独添加放大触发区 |
| 前端 E2E 测试 | 修正点击策略，补充 overlay 覆盖场景的测试用例 |
| 后端 | 不涉及 |

---

## 4. BUG-03：错误处理与状态恢复（3 个子问题）

### 4.0 触发场景（已澄清，OPEN-01 关闭）

**两个场景均需覆盖（用户确认）**：

- **场景 A（WebSocket 失败）**：用户点击"开始生成"提交后，后端 Celery task 调用 Ark API 失败，前端收到 WebSocket 的 `image_failed` / `batch_completed[status=failed]` 事件。前端必须在此路径上重置 `isGenerating=false` 并持久展示错误。
- **场景 B（POST 失败）**：POST /api/v1/image/generate/ 接口本身返回网络错误、4xx 业务错误或 5xx 服务错误，前端 catch 块触发。前端必须正确恢复 `isGenerating=false` 并持久展示错误信息。

两条路径的共同要求：
1. `isGenerating` 重置为 `false`（按钮恢复可用）
2. 错误信息持久展示（`duration:0 showClose:true`）
3. 结果面板显示常驻 ElAlert
4. 进度条归零或隐藏（不停留在错误进度）

### 4.1 Bug-3a：错误信息一闪而过

**现象**：生成失败时，顶部 `ElMessage.error(errMsg)` 提示几秒自动消失。
**期望**：错误信息持续显示直到用户主动关闭。

**根因分析（高置信度）**：
- `ElMessage` 组件默认 `duration: 3000`（3秒自动关闭）。
- 在 `submitGeneration()` catch 块中使用 `ElMessage.error(errMsg)` 和 `handleWebSocketMessage` 中的 `ElMessage.error(...)` 均采用默认时长。
- 同时，`generationError` ref 已赋值，右侧结果面板的 `v-else-if="generationError"` 区块也会显示静态错误文本，但这个静态区块没有明显的视觉突出。

**修复目标**：
1. 错误提示持续显示至用户主动关闭（duration: 0 或切换为 ElAlert 常驻展示）
2. 右侧结果面板的错误区块视觉设计明确（不能只依赖 ElMessage）

### 4.2 Bug-3b："开始生成"按钮失败后永久禁用

**现象**：一次生成失败后，按钮 disabled 状态不恢复。
**期望**：失败后按钮可重新点击重试。

**根因分析（高置信度）**：
阅读 `submitGeneration()` 函数：

```javascript
isGenerating.value = true   // 提交前置为 true（禁用按钮）
...
try {
  const { data } = await imageAPI.generate(formData)
  currentBatch.value = { ... }
  // 成功后 isGenerating 不重置！等 WebSocket batch_completed 事件才重置
} catch (err) {
  isGenerating.value = false  // catch 块：isGenerating 正确重置为 false
  ...
  generationError.value = errMsg
}
```

**按钮 disabled 条件**：`:disabled="!prompt.trim() || isGenerating"`

- **场景 B（POST 失败）**：catch 块已执行 `isGenerating.value = false`，按钮应该恢复。需 verify 是否真的不恢复。
- **场景 A（WebSocket 失败）**：`isGenerating` 在 `handleWebSocketMessage` 的 `batch_completed` 中置 false，但若 WebSocket 断开或 `batch_completed` 消息未到达，`isGenerating` 永久为 true → 按钮永久禁用。

**修复目标**：
1. 任何失败路径均确保 `isGenerating` 重置为 false
2. 超时保护机制：若 N 分钟内未收到 batch_completed，自动重置状态

### 4.3 Bug-3c：进度条不更新 + 取消按钮（已澄清，OPEN-02/04 关闭）

**现象**：
- 进度条（el-progress）始终停在 0% 或固定值不更新

**现象说明**：当前 `ImageGeneratorView.vue` 生成中区域代码（第 145-159 行）：
```html
<el-progress :percentage="batchProgress" ... />
```
其中 `batchProgress` computed = `completedImages.length / total_count * 100`。

**Hypothesis A（进度条，高置信度）**：
- 进度条数据源 `batchProgress` 依赖 `completedImages.length`，而 `completedImages` 仅在 WebSocket `image_completed` 事件中 push 新项。
- 若 WebSocket 连接失败或未建立，`completedImages` 永远为空 → 进度条 0%。
- WebSocket 连接逻辑在 `connectWebSocket()` 中，`ws.onerror` 回调仅打了注释，没有降级到 HTTP 轮询。

**关键决策（OPEN-02 + OPEN-04 合并关闭）：取消按钮完全去掉**

用户确认产品哲学：「如果生成任务确认已经失败了，那么重新能调整提示词或者参数重新生成就可以了」

因此：
- **不新增**取消按钮
- **移除**任何现有的取消按钮 UI、事件 handler、状态字段、CSS（如果存在的话）
- 后端不需要 Celery task revoke 接口（v1.2.1 范围外）
- 失败后的 UX 转向"失败后简单重试"模式（见 §4.4）

**修复目标**：
1. **3c-进度**：WebSocket 不可用时降级到 HTTP 轮询（调用 `/api/v1/image/batches/{id}/`），通过 `completed_count / total_count` 更新 batchProgress
2. **3c-取消按钮**：如代码中存在取消相关 UI 或 handler，本次一并移除；后续不添加

### 4.4 失败后重试 UX（OPEN-02/04 澄清后新增）

**用户确认的交互模式**：生成失败后不需要"取消"，直接支持重试。

失败后的页面状态要求：
1. 错误信息持久显示（ElMessage `duration:0 showClose:true` + 结果面板常驻 ElAlert）
2. "开始生成"按钮恢复可用（`isGenerating=false`）
3. 进度条归零或隐藏（不停在错误进度让用户误以为还在运行）
4. 用户可直接修改提示词/参数 → 点"开始生成"重试，不需刷新页面

### 4.5 影响范围（Bug-03 整体）

| 层 | 影响 |
|----|------|
| 前端 ImageGeneratorView | isGenerating 状态机修复（3b）；ElMessage duration（3a）；进度轮询降级（3c）；**移除**取消按钮（如存在）；进度条失败归零 |
| 后端 tasks.py / views.py | 不涉及（无需取消 API） |
| 前端 E2E | 新增失败状态 + 按钮恢复 + 失败后重试测试；**删除**任何取消按钮相关测试 |

---

## 5. 非功能需求

| ID | 描述 |
|----|------|
| NFR-01 | 所有前端修复必须有配套 unit/E2E 测试（保持 pre-commit 通过） |
| NFR-02 | Bug-03 状态机修改不得影响正常成功路径 |
| NFR-03 | Bug-02 修复不得破坏 hover overlay（删除/下载功能） |
| NFR-04 | Bug-01 后端 serializer 扩展保持向后兼容（历史即梦数据不受影响） |

---

## 6. 开放问题（Open Questions）

| ID | 问题 | 优先级 | 状态 | 决策 |
|----|------|--------|------|------|
| OPEN-01 | "剪辑删除"的真实触发场景是什么？是 POST 失败还是 WebSocket 失败？ | 高 | **已关闭** | 两种场景均需覆盖（见 §4.0） |
| OPEN-02 | 用户期望的"取消按钮"是现有的还是新增的功能？ | 高 | **已关闭** | 取消按钮完全去掉，转向失败后重试模式 |
| OPEN-03 | 批次列表页（BatchListPage）卡片是否也需要显示首图缩略图？ | 中 | 保留 | 仅在 BatchDetailPage 弹窗实现，BatchListPage 为 v1.3 backlog |
| OPEN-04 | 后端是否支持 Celery task revoke（任务取消）？ | 中 | **已关闭** | 不需要，取消功能已从产品范围移除 |

---

## 7. 范围边界（Out of Scope）

- 新增模型版本
- 视频生成改造
- 其他 v1.2 已上线功能的改动
- 批次管理的搜索/筛选功能
