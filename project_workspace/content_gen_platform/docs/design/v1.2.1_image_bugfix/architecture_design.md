# 架构设计文档 v1.2.1 — AI 图片 Bug 修复

**file_header**
- document_id: ARCH-v1.2.1
- author_agent: sub_agent_system_architect
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2.1 AI 图片 3 个 Bug 修复
- status: DRAFT
- created_at: 2026-05-14
- input_refs: requirements_spec.md v1.2.1, ARCH-v1.2, MOD-v1.2

---

## 1. 架构影响评估

v1.2.1 是纯 bug 修复版本，**不引入新的架构组件**，不新增 API 端点，不改变数据模型。变更集中在以下层：

| 层 | 变更性质 | 影响范围 |
|----|---------|---------|
| 后端 Serializer 层 | 字段扩展（新增 thumbnail_url）| 仅 ImageGenerationRequestSerializer |
| 后端 View 层 | context 传递修复 | 仅 ImageBatchDetailView |
| 前端 组件层 | 渲染逻辑修复 | BatchDetailPage、MediaLibraryView、ImageGeneratorView |
| 前端 状态管理 | isGenerating 状态机修复 | ImageGeneratorView |
| 前端 网络层 | HTTP 轮询降级 | ImageGeneratorView（新增 polling 逻辑） |
| E2E 测试 | 测试修正 + 新增 | 媒体库 + 批次详情 + 生成状态 |

## 2. 跨模块状态机变更

### 2.1 ImageGeneratorView 生成状态机（修复后，已合并 OPEN-01/02/04 澄清）

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

  ↓ POST 失败（catch，含网络错误/4xx/5xx）
[DONE_ERROR] isGenerating=false, completedImages=[], generationError 已设置

[DONE_ERROR]
  ↓ 用户修改参数后点击"开始生成"（无需额外步骤）
[SUBMITTING] → ...
```

**关键修复点**：
- `image_failed` 事件现在也会设置 `isGenerating=false`（原来漏掉了）
- 所有失败路径增加 `completedImages.value = []`（进度条归零）
- 超时保护：5 分钟后强制重置
- POST 失败覆盖：网络错误、4xx 业务错误、5xx 服务错误三类
- **不再有"取消"分支**（OPEN-02 已关闭，取消按钮从产品移除）

## 3. ADR（架构决策记录）

### ADR-v1.2.1-01：取消功能从产品范围移除（已更新，OPEN-02 关闭）

**原问题**：用户点击"取消"后，前端是否应调用后端接口中止 Celery 任务？

**最终决策（2026-05-15 用户澄清）**：**取消功能完全从产品移除**。

用户原话：「如果生成任务确认已经失败了，那么重新能调整提示词或者参数重新生成就可以了」

产品哲学从"中途取消"转向"失败后简单重试"：
- 不新增取消按钮
- 移除任何现有取消相关 UI/handler/state/CSS
- 不需要后端 cancel API
- 失败后用户直接修改参数 → 点"开始生成"重试

**后续版本**：若用户需要，可在 v1.3 重新评估。

### ADR-v1.2.1-02：BUG-02 修复选方案 A（pointer-events: none）

**问题**：Lightbox 点击拦截如何修复？

**决定**：`.hover-overlay { pointer-events: none }` + `.hover-actions { pointer-events: auto }`

**理由**：
1. 最小改动（2 行 CSS），视觉效果完全不变
2. 不引入 ref 访问 el-image 内部方法（减少与 Element Plus 版本绑定）
3. el-image 的原生 preview 机制不变，多图切换 `initial-index` 逻辑不需改动

## 4. 无变更确认

以下内容在 v1.2.1 中确认**不变更**：

- `tech_stack.md`：无新增依赖
- 数据库 Model：`ImageBatch`、`ImageGenerationRequest`、`MediaItem` 均不改动，不需要新 migration
- Celery Task 签名：`generate_image_task(batch_id, advanced_params, size)` 不变
- API 端点 URL：所有端点不变
- WebSocket 协议：不变

## 5. 回归风险评估

| Bug 修复 | 回归风险点 | 缓解措施 |
|---------|-----------|---------|
| BUG-01（serializer 扩展）| PATCH 重命名接口误加 thumbnail_url | ImageBatchListSerializer 不变，仅 ImageBatchSerializer 的嵌套序列化受影响 |
| BUG-02（pointer-events）| 删除/下载按钮失效 | pointer-events: auto 明确恢复按钮事件；E2E AC-B02-4 验证 |
| BUG-03（isGenerating 修复）| 正常成功路径 isGenerating 提前置 false | 超时保护 timer 在 batch_completed[success] 时 clearTimeout；成功路径不受影响 |
| BUG-03（HTTP 轮询）| 与 WebSocket 重复处理 | WebSocket 可用时不启动轮询；ws.onerror 触发时 WebSocket 已无效，互斥 |
