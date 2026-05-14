# 用户故事文档 v1.2.1 — AI 图片 Bug 修复

**file_header**
- document_id: US-v1.2.1
- author_agent: sub_agent_requirement_analyst
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2.1 AI 图片 3 个 Bug 修复
- status: DRAFT
- created_at: 2026-05-14
- input_refs: requirements_spec.md v1.2.1

---

## US-B01：查看批次缩略图

**作为** 已提交过图片生成任务的用户，
**我希望** 在批次管理详情弹窗中看到该批次已完成图片的缩略图，
**以便** 快速确认生成结果，不必切换到素材库查找。

**来源**：BUG-01 需求（requirements_spec.md §2）

### AC-B01-1：已完成图片显示缩略图

**Given** 某批次内有至少 1 张 status=completed 的图片（media_item 已入库）
**When** 用户进入"批次管理" Tab，点击该批次，弹出批次详情弹窗
**Then** 弹窗内的图片网格中，每张已完成图片以实际缩略图（`<el-image>` 或 `<img>`）展示，而非"素材 #ID"占位符

*E2E 覆盖点*：Mock `GET /api/v1/image/batches/{id}/` 返回含 `result_image_url` 的 requests，断言 `.image-grid img` 或 `.el-image` 可见且 src 非空。

### AC-B01-2：失败图片显示错误占位符

**Given** 批次内有 status=failed 的图片记录
**When** 用户查看批次详情弹窗
**Then** 失败图片格子显示错误图标 + error_message 文字，而非空白

*E2E 覆盖点*：Mock 含 status=failed + error_message 的 request，断言 `.image-grid-item--failed .error-msg` 可见。

### AC-B01-3：后端 serializer 返回图片 URL

**Given** 批次详情 API `GET /api/v1/image/batches/{id}/`
**When** 批次内有 completed 的 request
**Then** 响应体的 `requests[]` 数组中每条记录包含可用的图片 URL 字段（`result_image_url` 或 `media_item_url`）

*Unit 测试覆盖点*：pytest 断言序列化器输出包含 URL 字段，且非空。

---

## US-B02：素材库图片放大预览（回归修复）

**作为** 使用素材库的用户，
**我希望** 点击图片缩略图能弹出 Lightbox 放大查看，
**以便** 检查 AI 生成图片的细节质量。

**来源**：BUG-02 需求（requirements_spec.md §3）

### AC-B02-1：点击图片触发 Lightbox（核心回归验证）

**Given** `/media-library` 页面中有至少 1 张图片（media_type=image）
**When** 用户将鼠标移到图片上（hover），然后点击图片区域（非 hover overlay 按钮区域）
**Then** 页面出现 Lightbox 弹层（`.el-image-viewer__wrapper` 可见），展示原图

*E2E 覆盖点*：与现有 AC-07-1 相同场景，但点击策略从 `elImage.click()` 改为显式点击 `el-image__inner`（`.el-image__inner` 或 `el-image__preview` 区域），绕过 overlay 拦截问题。
**漏测加固**：新增测试步骤验证 hover 状态下 overlay 可见时，点击图片区域（而非按钮）仍能触发 Lightbox。

### AC-B02-2：Esc 键关闭 Lightbox

**Given** Lightbox 已弹出
**When** 用户按 Esc 键
**Then** Lightbox 关闭（`.el-image-viewer__wrapper` 消失）

*E2E 覆盖点*：继承 AC-07-2。

### AC-B02-3：点击蒙层关闭 Lightbox

**Given** Lightbox 已弹出
**When** 用户点击 `.el-image-viewer__mask`
**Then** Lightbox 关闭

*E2E 覆盖点*：继承 AC-07-3。

### AC-B02-4：修复后 hover overlay 不受影响

**Given** Lightbox 修复已应用
**When** 用户 hover 某张图片后，不点击图片而是点击"下载"或"删除"按钮
**Then** 对应操作正常执行，Lightbox 不弹出

*E2E 覆盖点*：新增测试，hover 后点击 `.hover-actions` 内按钮，断言 `.el-image-viewer__wrapper` 不出现。**此为 v1.2 漏测点。**

### AC-B02-5（漏测加固）：overlay 覆盖时点击图片区仍触发 Lightbox

**Given** 用户正在 hover 该图片（hover-overlay 可见、覆盖 el-image）
**When** 用户点击图片（el-image 内部图片区域，非按钮）
**Then** Lightbox 弹出

*E2E 覆盖点*：`await firstCard.hover(); await elImageInner.click()`，断言 Lightbox 出现。**v1.2 E2E 未覆盖此场景 = 漏测根因。**

---

## US-B03：生成失败后的状态恢复与重试

**作为** 使用 AI 图片生成功能的用户，
**我希望** 在生成失败后能清楚看到错误原因，并能直接修改参数后立即重试，
**以便** 不必刷新页面即可重新生成。

**来源**：BUG-03 需求（requirements_spec.md §4）；OPEN-01/02/04 用户澄清

**产品决策**：不提供"取消"按钮。失败后直接修改提示词/参数 → 点"开始生成"重试。

### AC-B03-POST-1：POST 失败时错误信息持续展示

**Given** 用户提交图片生成，POST 请求返回网络错误、4xx 或 5xx
**When** 前端 catch 块处理完成
**Then** 错误信息以 ElMessage（duration:0, showClose:true）展示，且不自动消失

*E2E 覆盖点*：Mock POST 返回 500，等待 5 秒后断言 `.el-message--error` 仍可见。

### AC-B03-POST-2：POST 失败后按钮立即恢复可用

**Given** 用户点击"开始生成"触发 POST 请求，后端返回 4xx/5xx
**When** 前端 catch 块处理完成
**Then** "开始生成"按钮不再 disabled（isGenerating 重置为 false），用户可点击重试

*E2E 覆盖点*：Mock POST 返回 500，断言按钮 `toBeEnabled()`。

### AC-B03-WS-1：WebSocket image_failed 事件后按钮恢复

**Given** POST 成功（202），但后续 WebSocket 推送 image_failed 事件
**When** 前端处理 image_failed
**Then** isGenerating 重置为 false，按钮可点击，结果面板显示持久错误

*E2E 覆盖点*：Mock WebSocket 发送 image_failed 事件，断言按钮可用 + ElAlert 可见。

### AC-B03-WS-2：WebSocket 断开后超时保护恢复按钮

**Given** POST 成功（202），但 WebSocket 连接断开，5 分钟未收到 batch_completed
**When** 超时保护定时器触发
**Then** isGenerating 重置为 false，按钮可点击，结果面板显示超时提示

*E2E 覆盖点*：Mock WebSocket 不发任何事件，使用 fake timer 推进 5min，断言按钮恢复。

### AC-B03-RETRY-1：失败后可修改参数重新提交

**Given** 一次图片生成失败（POST 失败 或 WebSocket image_failed）
**When** 用户修改提示词或生成参数
**Then** "开始生成"按钮可点击，点击后成功提交新的生成请求

*E2E 覆盖点*：在 AC-B03-POST-2 或 AC-B03-WS-1 断言按钮可用后，更新 prompt input 并再次 click 按钮，断言新 POST 请求被发出。

### AC-B03-ERROR-1：结果面板常驻 ElAlert

**Given** 生成失败（任意场景）
**When** 前端处理错误
**Then** 右侧结果面板显示 ElAlert（type=error），包含具体错误文本，用户不主动关闭时不消失

*E2E 覆盖点*：Mock POST 失败，断言 `.el-alert--error` 可见且包含错误描述。

### AC-B03-PROGRESS-1：失败时进度条归零

**Given** 生成过程中出现失败（任意场景）
**When** 前端处理失败状态
**Then** 进度条 percentage 重置为 0（或隐藏），不停留在错误进度

*E2E 覆盖点*：Mock 失败场景，断言 `.el-progress` 的 percentage attribute 为 0 或不可见。

### AC-B03c-1：进度条反映真实进度（WebSocket 路径）

**Given** 用户提交图片生成（n=2 或更多），后端逐张返回完成事件
**When** 每张图片完成时（WebSocket image_completed）
**Then** 进度条 percentage 从 0 递增，每完成一张增加 `100/total_count`%

*E2E 覆盖点*：Mock WebSocket 推送 2 个 image_completed 事件，断言进度条 percentage 值变化。

### AC-B03c-2：WebSocket 不可用时降级到 HTTP 轮询

**Given** WebSocket 连接失败（ws.onerror 触发）
**When** 用户提交生成请求
**Then** 前端自动启动 HTTP 轮询（`GET /api/v1/image/batches/{id}/`），每 3 秒查询一次，更新进度条

*E2E 覆盖点*：模拟 WebSocket 失败，Mock `GET /api/v1/image/batches/{id}/` 返回递增的 completed_count，断言进度条更新。

---

## US-B03-X：失败后无需取消、直接重试

**作为** 使用 AI 图片生成功能的用户，
**我希望** 在生成失败后可以直接修改提示词或参数然后点击"开始生成"重试，
**以便** 不需要任何额外的"取消"步骤。

**来源**：OPEN-02 用户澄清（2026-05-15）

### AC-B03-X-1：失败后开始生成按钮可点击

**Given** 一次图片生成失败
**When** 用户修改提示词或参数
**Then** "开始生成"按钮可点击且新任务正常提交

*E2E 覆盖点*：失败场景后直接点击"开始生成"，断言新 POST 请求发出、进度条重新开始。

### AC-B03-X-2（反向验证）：生成区域不存在取消按钮

**Given** 图片正在生成中（isGenerating=true）
**When** 用户查看生成区域
**Then** 区域内不存在任何"取消"按钮（包含文字"取消"的 el-button）

*E2E 覆盖点*：提交生成后断言 `page.getByRole('button', { name: '取消' })` count 为 0。

---

## 测试策略总表

| User Story | AC | 测试类型 | 新增/现有 | 漏测修复 |
|-----------|-----|---------|---------|---------|
| US-B01 | AC-B01-1 | E2E (Playwright) | 新增 | - |
| US-B01 | AC-B01-2 | E2E (Playwright) | 新增 | - |
| US-B01 | AC-B01-3 | Unit (pytest) | 新增 | - |
| US-B02 | AC-B02-1 | E2E (Playwright) | 修正现有 AC-07-1 | 修复 overlay 拦截漏测 |
| US-B02 | AC-B02-2 | E2E (Playwright) | 继承 AC-07-2 | - |
| US-B02 | AC-B02-3 | E2E (Playwright) | 继承 AC-07-3 | - |
| US-B02 | AC-B02-4 | E2E (Playwright) | 新增 | 补充 hover-overlay 不误触 lightbox |
| US-B02 | AC-B02-5 | E2E (Playwright) | 新增 | **v1.2 核心漏测点修复** |
| US-B03 | AC-B03-POST-1 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03-POST-2 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03-WS-1 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03-WS-2 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03-RETRY-1 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03-ERROR-1 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03-PROGRESS-1 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03c-1 | E2E (Playwright) | 新增 | - |
| US-B03 | AC-B03c-2 | E2E (Playwright) | 新增 | - |
| US-B03-X | AC-B03-X-1 | E2E (Playwright) | 新增 | - |
| US-B03-X | AC-B03-X-2 | E2E (Playwright) | 新增（反向验证） | 确保取消按钮已移除 |
| ~~US-B03~~ | ~~AC-B03c-3 取消按钮~~ | ~~E2E~~ | **已删除** | 需求变更：取消按钮从产品中移除 |

### v1.2 漏测总结

1. **最关键漏测**：AC-B02-5（hover-overlay 覆盖 el-image 时，点击图片区仍应触发 Lightbox）
   - 原因：现有 E2E 的 `elImage.click()` 在 non-hover 状态下点击，实际生产环境中用户几乎必然在 hover 状态下点击图片
   - 修复：新增 hover → click(el-image__inner) 的测试链路

2. **次要漏测**：hover-overlay 按钮点击不应触发 Lightbox（AC-B02-4）
   - 原因：现有测试只验证"能开"，未验证"按钮区不误开"

3. **缺口**：批次详情缩略图（BUG-01）完全未被 E2E 覆盖

4. **缺口**：生成失败后状态恢复（BUG-03）完全未被 E2E 覆盖

### 需求变更说明（2026-05-15）

- **删除**：AC-B03c-3（取消按钮）—— OPEN-02 用户澄清后，取消按钮从产品范围中移除
- **新增**：US-B03-X（失败后重试）+ AC-B03-X-1/2 —— 覆盖失败后直接重试的正向和反向场景
- **扩展**：US-B03 下的 AC 细化为 POST 失败 / WS 失败 / 进度条 / 重试 四类（原 AC-B03a/b/c 体系保留语义，编号更新为更精确的路径标识）
