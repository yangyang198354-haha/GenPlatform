# LLM 模型选择功能 — 用户故事

**版本**：v0.1.0-DRAFT
**日期**：2026-05-15
**关联需求文档**：`docs/features/llm_selection/requirements.md`
**特性分支**：llm_selection

---

## US-01：内容创作者首次使用（仅配了 DeepSeek）

**角色**：内容创作者（仅配置了 `llm_deepseek`，last_test_ok=True）

**故事**：作为内容创作者，我已经在设置页面配置并验证了 DeepSeek 的 API Key，现在我想生成一篇小红书文案，希望系统自动使用 DeepSeek V3，不需要我再做任何选择。

**验收条件（Given/When/Then）**：

- **AC-US01-1（默认选中）**
  - Given 用户只配置了 `llm_deepseek`（last_test_ok=True），无偏好记录
  - When 用户打开文案生成页面
  - Then 模型下拉控件默认选中"DeepSeek / deepseek-chat"，无需手动操作

- **AC-US01-2（首屏加载时间）**
  - Given 同上
  - When 页面加载
  - Then 下拉控件从空白到可交互（含 model 列表显示）耗时 ≤ 1s

- **AC-US01-3（成功生成）**
  - Given 下拉选中 deepseek-chat，用户填写 prompt 并点击"生成"
  - When 后端处理请求
  - Then 后端以 `DeepSeekProvider(model="deepseek-chat")` 调用 API，SSE 流正常返回文案内容

**关联 FR**：FR-LLM-SEL-01, FR-LLM-SEL-02
**关联 AC**：AC-01, AC-02

---

## US-02：内容创作者切换模型（配了 DeepSeek + 火山引擎）

**角色**：内容创作者（同时配置了 `llm_deepseek` 和 `llm_volcano`，均 last_test_ok=True）

**故事**：作为内容创作者，我配置了多个 LLM 服务，想在生成文案时手动选择使用哪个模型，例如今天想试试豆包长文案效果。

**验收条件（Given/When/Then）**：

- **AC-US02-1（下拉列出多 provider）**
  - Given 用户配置了 llm_deepseek 和 llm_volcano，均有效
  - When 用户打开文案生成页面
  - Then 下拉控件按 provider 分组展示，DeepSeek 分组含 deepseek-chat / deepseek-reasoner，火山引擎分组含从 /models 接口动态拉取（或白名单 fallback）的 model 列表

- **AC-US02-2（手动切换并生成）**
  - Given 用户在下拉中选择"火山引擎 / doubao-pro-32k"
  - When 用户点击"生成文案"
  - Then 后端以 `VolcanoProvider(model="doubao-pro-32k")` 调用 API，生成结果正常返回
  - And 后端日志记录 `provider=llm_volcano, model=doubao-pro-32k, success=True, latency_ms=<实测值>`

- **AC-US02-3（后端 service_type 校验）**
  - Given 用户请求参数中 service_type 为不在其已配置列表中的值（如伪造了 `llm_fake`）
  - When 后端处理
  - Then 返回 HTTP 400，错误信息明确说明"无效的 service_type 或该服务未配置"

**关联 FR**：FR-LLM-SEL-01, FR-LLM-SEL-03, FR-LLM-SEL-08
**关联 AC**：AC-01, AC-04

---

## US-03：用户偏好记忆（上次选了 doubao-pro-32k，下次自动选中）

**角色**：内容创作者（上次成功生成时使用了 `llm_volcano / doubao-pro-32k`）

**故事**：作为内容创作者，我不想每次进入文案生成页面都重新手动选模型，希望系统记住我上次的选择，下次自动恢复。

**验收条件（Given/When/Then）**：

- **AC-US03-1（偏好写入）**
  - Given 用户选择 `llm_volcano / doubao-pro-32k` 并成功完成文案生成（SSE 正常结束）
  - When 生成流结束
  - Then 后端将 `preferred_service_type=llm_volcano, preferred_model=doubao-pro-32k` 写入用户偏好记录

- **AC-US03-2（下次自动选中）**
  - Given 用户的偏好记录为 `llm_volcano / doubao-pro-32k`，且该 provider 仍有效（last_test_ok=True）
  - When 用户再次打开文案生成页面
  - Then 下拉默认选中"火山引擎 / doubao-pro-32k"，而不是 deepseek-chat

- **AC-US03-3（偏好失效降级）**
  - Given 用户偏好记录为 `llm_volcano / doubao-pro-32k`，但用户事后在设置页删除了火山引擎配置
  - When 用户打开文案生成页面
  - Then 系统检测到偏好 provider 已失效，自动降级为 DeepSeek / deepseek-chat（FR-LLM-SEL-02 规则 2）

**关联 FR**：FR-LLM-SEL-02, FR-LLM-SEL-04
**关联 AC**：AC-03, AC-05

---

## US-04：未配置 DeepSeek 用户（看到提示，不能直接生成）

**角色**：新用户（未配置任何 LLM provider，或已配置但所有 provider 均 last_test_ok=False）

**故事**：作为新注册用户，我还没有配置任何 LLM API Key，进入文案生成页面时希望看到清晰的引导提示，而不是让我直接点击生成却发现失败。

**验收条件（Given/When/Then）**：

- **AC-US04-1（前端拦截 + 提示）**
  - Given 用户无任何有效 LLM 配置（service_type 含 llm_ 的记录为空，或所有均 last_test_ok=False）
  - When 用户打开文案生成页面
  - Then 模型下拉控件显示为禁用/空状态，"生成"按钮置灰不可点击
  - And 在表单区域显示提示：「请先配置 DeepSeek 服务，或在下拉框选择其他已配置的模型」

- **AC-US04-2（不静默回退）**
  - Given 同上
  - When 用户通过技术手段（如 API 调试工具）直接发请求但不传 service_type
  - Then 后端不静默选取任何 provider，返回 HTTP 400 + 明确错误信息

- **AC-US04-3（配置后恢复正常）**
  - Given 用户在设置页面新增并验证了 llm_deepseek 配置（last_test_ok=True）
  - When 用户返回文案生成页面（或刷新）
  - Then 下拉控件恢复可用，默认选中 deepseek-chat

**关联 FR**：FR-LLM-SEL-06
**关联 AC**：AC-07

---

## US-05：已选模型的 key 失效（保存时测过 OK，使用时失败）

**角色**：内容创作者（key 在保存时验证通过，但在使用时已失效—— 如 API Key 被吊销或账户欠费）

**故事**：作为内容创作者，我上次保存 key 时测试是 OK 的，但这次生成文案时 key 已经失效，希望看到明确的错误提示，而不是系统静默换到另一个 provider 继续生成。

**验收条件（Given/When/Then）**：

- **AC-US05-1（明确错误提示）**
  - Given 用户选择 `llm_deepseek / deepseek-chat`，对应 API Key 已在服务商侧失效
  - When 用户点击"生成"，后端调用 DeepSeek API 返回 401/403
  - Then SSE 流返回错误事件，前端展示错误提示：「当前选择的模型调用失败，请检查 API Key 是否有效（错误：401 Unauthorized）」
  - And 不静默切换到其他 provider 继续生成

- **AC-US05-2（可追溯）**
  - Given 同上
  - When 错误发生
  - Then 后端日志记录 `provider=llm_deepseek, model=deepseek-chat, success=False, latency_ms=<值>, error_code=401`

**关联 FR**：FR-LLM-SEL-03, FR-LLM-SEL-06, NFR-02
**关联 AC**：AC-04（反向验证）

---

## US-06：/models 接口超时（前端 fallback 到白名单 + 明示）

**角色**：内容创作者（网络延迟或 provider /models 接口不稳定）

**故事**：作为内容创作者，有时网络不好或 provider 接口响应慢，我希望页面仍然能快速可用，即便 model 列表不是最新的，也要有基础的可选项，而且要明确告诉我现在用的是默认列表。

**验收条件（Given/When/Then）**：

- **AC-US06-1（超时 fallback）**
  - Given 用户配置了有效的 `llm_volcano`，但 Ark /v3/models 接口响应超过 800ms
  - When 用户打开文案生成页面，后端等待 /models 接口超时
  - Then 后端在 800ms 内返回白名单 model 列表（doubao-pro-4k, doubao-pro-32k），响应中 `models_source = "fallback"`
  - And 前端检测到 fallback 标志，在火山引擎分组旁显示提示："模型列表加载失败，使用默认列表"
  - And 页面整体可交互时间 ≤ 1s

- **AC-US06-2（白名单可正常使用）**
  - Given AC-US06-1 的 fallback 场景
  - When 用户选择白名单中的 doubao-pro-32k 并生成
  - Then 生成正常完成（白名单 model 是经过验证可用的 ID）

**关联 FR**：FR-LLM-SEL-01, FR-LLM-SEL-05, NFR-01
**关联 AC**：AC-01, AC-06

---

## US-07：运维/管理员通过后端审计

**角色**：运维人员 / 成本核算管理员

**故事**：作为运维人员，我需要分析各 provider 和 model 的使用量和成本，希望每条文案生成记录都带有使用的 provider 和 model 信息，可以在后台直接查询。

**验收条件（Given/When/Then）**：

- **AC-US07-1（字段写入）**
  - Given 用户以 `llm_volcano / doubao-pro-32k` 成功完成文案生成
  - When 查询数据库 Content 表该条记录
  - Then `provider = "llm_volcano"`，`model = "doubao-pro-32k"` 已正确写入，不为 null

- **AC-US07-2（历史记录向后兼容）**
  - Given 本次迁移前（字段新增前）已存在的 Content 记录
  - When 查询这些历史记录
  - Then `provider` 和 `model` 字段为 null，不报错，不影响列表查询性能

- **AC-US07-3（前端不暴露）**
  - Given 用户在前端"我的文案"列表页
  - When 页面加载
  - Then 文案列表中不展示 provider 和 model 字段（仅后端可见）

**关联 FR**：FR-LLM-SEL-07
**关联 AC**：AC-08

---

## 故事地图（角色 × 场景矩阵）

| 故事 | 主角 | 核心场景 | 优先级 |
|---|---|---|---|
| US-01 | 创作者（单 provider） | 首次使用，默认 DeepSeek | P0 |
| US-02 | 创作者（多 provider） | 手动切换 provider+model | P0 |
| US-03 | 创作者（有历史偏好） | 偏好记忆与自动恢复 | P1 |
| US-04 | 新用户（未配置） | 无配置时前端引导 | P0 |
| US-05 | 创作者（key 失效） | 运行时 key 失效的错误处理 | P0 |
| US-06 | 创作者（网络异常） | /models 超时 fallback | P1 |
| US-07 | 运维/管理员 | provider/model 使用记录审计 | P2 |
