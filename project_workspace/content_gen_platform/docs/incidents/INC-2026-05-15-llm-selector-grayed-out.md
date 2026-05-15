# INC-2026-05-15: LLM 模型选择器持续置灰

## 状态

调查完成，修复方案待用户 CONFIRM

---

## 现象

用户在系统设置 > 大语言模型 Tab 填写 DeepSeek API Key 并点击"保存"后，进入内容生成工作台，"请选择 AI 模型"下拉框持续置灰，无法选择任何模型，"开始生成"按钮同时被禁用。

---

## 时间线

- 2026-05-15：6 个 commit 推送 main，CI run `25904034448` 全绿（含 Smoke Test 17s），物理部署成功
- 2026-05-15 同日：用户配置 DeepSeek key 后立即发现选择器置灰，报告 bug

---

## 根因分析

### 根因 A（主因，已确认）：`ServiceConfigDetailView.put` 不写 `last_validated_at`，但 LlmSelector 的可用判定强依赖该字段

**数据流追踪：**

1. 用户在 SettingsView.vue 点击"保存"按钮
   - 触发 `saveLlmConfig()`（`SettingsView.vue:251`）
   - 调用 `settingsAPI.save(llmServiceType, payload)`，即 `PUT /api/v1/settings/services/llm_deepseek/`
   - 后端 `ServiceConfigDetailView.put`（`settings_vault/views.py:72-96`）执行：
     ```python
     UserServiceConfig.objects.update_or_create(
         user=request.user,
         service_type=service_type,
         defaults={"encrypted_config": encrypted, "is_active": True},
     )
     ```
   - **`last_validated_at` 字段不在 `defaults` 中，保持 NULL**

2. 后端 `list_available_providers`（`selectors.py:179`）计算每个 provider 的状态：
   ```python
   last_test_ok = bool(cfg and cfg.last_validated_at is not None)
   ```
   - `last_validated_at` 为 NULL → `last_test_ok = False`
   - `configured = True`（`is_active=True` 的记录存在）

3. API 响应返回：
   ```json
   { "configured": true, "last_test_ok": false, "models": [...] }
   ```

4. 前端 `llm.js` store getter（`stores/llm.js:33`）：
   ```js
   noAvailableProviders: (state) =>
     state.providers.filter((p) => p.configured && p.last_test_ok).length === 0
   ```
   - `last_test_ok=false` → DeepSeek 被过滤掉 → `noAvailableProviders = true`

5. `LlmSelector.vue:21` 绑定：
   ```html
   :disabled="disabled || noAvailableProviders"
   ```
   - 整个 el-select 被 disable → 选择器置灰

6. `LlmSelector.vue:39` 每个 option 也同时 disabled：
   ```html
   :disabled="!provider.configured || !provider.last_test_ok"
   ```

7. `WorkspaceView.vue:200-202`：
   ```js
   const generateDisabled = computed(() =>
     !form.prompt || llmStore.noAvailableProviders || !form.selectedLlm
   )
   ```
   - "开始生成"按钮同时被禁用

**结论：**  
用户走了"仅保存"路径（`PUT /settings/services/llm_deepseek/` → `ServiceConfigDetailView`），`last_validated_at` 永远为 NULL，导致前端判定 `last_test_ok=false`，选择器完全置灰。这是一个设计上的 UX 陷阱：UI 有两个按钮（"保存"和"测试连接"），用户直觉是先保存 key 就能用，但系统要求必须额外点"测试连接"且测试通过才算可用。

### 根因 B（次要因素，加重症状）：`ServiceConfigTestView.post` 也不写 `last_validated_at`

用户即便点了"测试连接"按钮：

- 调用 `settingsAPI.test()`，即 `POST /api/v1/settings/services/llm_deepseek/test/`
- 后端 `ServiceConfigTestView.post`（`settings_vault/views.py:105-118`）调用 `_test_connection()`
- **`_test_connection()` 仅返回 `{"success": True/False, "message": "..."}`，不写 `last_validated_at`**

能写 `last_validated_at` 的唯一路径是 `TestAndSaveView`（`/test-and-save/`），但该接口在 `settings_vault/views.py:239` 显式限制：
```python
if service_type != "doubao_image":
    return Response({"error": "UNSUPPORTED_SERVICE_TYPE", ...}, status=400)
```

即 `TestAndSaveView` 仅为 `doubao_image` 实现，`llm_deepseek` 和 `llm_volcano` 完全没有写 `last_validated_at` 的途径。

**实际结论：用户无论保存还是测试，`last_validated_at` 始终为 NULL，选择器永远置灰。**

### 根因 C（排除）：前端 60s 缓存

`fetchProviders(force=false)` 缓存 TTL 60 秒，但本场景中从未拿到过 `last_test_ok=true` 的响应，所以缓存问题不影响本次 bug，属于独立的 UX 问题。

### 根因 D / E（排除）

API 鉴权（401）和 nginx 路由（404）不是本次根因，`configured=true` 说明 GET `/api/v1/llm/providers/` 已正常返回数据。

---

## 修复方案（候选）

### 方案 1（推荐）：`ServiceConfigDetailView.put` 保存时同步调 LLM API 探活，成功则写 `last_validated_at`

**改动点：**

- `apps/settings_vault/views.py`：`ServiceConfigDetailView.put` 在 `update_or_create` 之后，调用 `_test_connection(service_type, config_data)` 进行探活
  - 成功：再次 `update_or_create` 或直接 `.update(last_validated_at=timezone.now())`
  - 失败：仍保存配置，但返回响应体中附加 `{"message": "配置已保存，但连接测试失败，请检查 Key"}`

**影响面分析：**
- 仅修改 `ServiceConfigDetailView.put` 的保存逻辑，不改前端
- `_test_connection` 对 `llm_deepseek` 和 `llm_volcano` 已有实现（分别调 DeepSeek `/v1/models` 和 Volcano `/v3/models`）
- 缺点：让"保存"接口多一次外部 HTTP 请求，超时 10s，可能让按钮响应变慢
- 风险：若 LLM API 不可达，用户 key 已写入但 `last_validated_at` 仍为 NULL，仍会置灰（需在响应体提示）

**测试策略：**
- 单测 mock `_test_connection` 返回 `(True, "...")` 验证 `last_validated_at` 被写入
- 单测 mock `_test_connection` 返回 `(False, "...")` 验证配置被保存但 `last_validated_at` 仍 NULL
- 集成测试：`PUT /settings/services/llm_deepseek/` → 验 `GET /api/v1/llm/providers/` 返回 `last_test_ok=true`

**回滚：** revert `ServiceConfigDetailView.put` 的额外探活逻辑，对数据库无副作用

**工作量：** 约 1-2 小时（后端 20 行，单测补充）

---

### 方案 2（推荐补充，与方案 1 配合）：`ServiceConfigTestView.post` 测试成功后写 `last_validated_at`

不管方案 1 是否实施，"测试连接"按钮测试成功后应该写 `last_validated_at`，这是最直接的语义修复。

**改动点：**

- `apps/settings_vault/views.py`：`ServiceConfigTestView.post` 中，`_test_connection()` 返回 `success=True` 时执行：
  ```python
  UserServiceConfig.objects.filter(
      user=request.user, service_type=service_type
  ).update(last_validated_at=timezone.now())
  ```

**影响面：** 极小，仅在测试成功时追加一次 DB update，无新外部依赖

**测试策略：**
- 单测：mock `_test_connection` 返回 `(True, "")` → 验 `last_validated_at` 被更新
- 单测：mock 返回 `(False, "")` → 验 `last_validated_at` 不变

**回滚：** revert 三行 DB update 代码

**工作量：** 约 30 分钟

---

### 方案 3（备选）：前端放宽 `noAvailableProviders` 判定，不强制 `last_test_ok`

**改动点：**

- `src/stores/llm.js`：
  ```js
  // 修改前
  noAvailableProviders: (state) =>
    state.providers.filter((p) => p.configured && p.last_test_ok).length === 0
  // 修改后
  noAvailableProviders: (state) =>
    state.providers.filter((p) => p.configured).length === 0
  ```
- `src/components/LlmSelector.vue`：option 的 `:disabled` 同步放宽（可选：仅 `!provider.configured`，`last_test_ok=false` 时改为显示 warning tooltip 但不 disable）

**风险：**
- 用户可以选择"配置了但未验证"的 provider，生成时若 key 无效会在 SSE 流中报错
- 后端 `validate_choice()` 不检查 `last_validated_at`（`selectors.py:305-342`），可以提交请求，但实际调用时会因 key 无效而失败
- 用户体验上是"选择成功 → 生成失败"，比"无法选择"稍好但不够干净

**推荐度：** 可作为方案 1+2 的前端兜底，但不建议单独使用

---

### 方案 4（备选）：前端在路由进入 /workspace 时强制 `fetchProviders(force=true)`

**改动点：**

- `src/views/WorkspaceView.vue` 添加 `onMounted` 或路由 `beforeRouteEnter` 钩子：
  ```js
  import { onMounted } from 'vue'
  onMounted(() => {
    llmStore.fetchProviders(true) // 跳过 60s 缓存
  })
  ```
- 或在 `settingsAPI.save` 成功后调 `llmStore.fetchProviders(true)`（需跨 View 通信）

**作用：** 解决假设 B（缓存），但本次 bug 的实际根因是 `last_test_ok` 永远为 false，强制刷新后拿到的数据仍然是 `last_test_ok=false`，**不能修复本 bug**

**结论：** 单独使用无效，可作为辅助改进独立上线

---

## 推荐方案：方案 2 先行，方案 1 紧跟

**优先级：**

1. **立即：方案 2**（`ServiceConfigTestView` 测试成功后写 `last_validated_at`）  
   改动最小、风险最低、语义最正确。用户在已保存 key 的情况下，点"测试连接"测试通过即可解灰。修复当前已受影响的用户。

2. **同步：方案 1**（`ServiceConfigDetailView.put` 保存时做探活）  
   让"保存"动作本身完成"测试通过即可用"的语义，消除 UI 中需要用户额外点"测试连接"的隐患，改善长期 UX。

3. **可选辅助：方案 4**（WorkspaceView `onMounted` 强制刷新 providers）  
   解决 60s 缓存问题，防止用户保存 key 后立即切换页面还看到旧数据，独立上线无风险。

---

## 为什么没被测试拦截

- **直接原因：E2E Playwright job 本次仍被跳过**（CI run `25904034448`），12 个 LLM E2E 实际未执行
- **深层原因：即便 E2E 跑了也不一定覆盖此路径**——PR-5 中的 E2E 测试设计未覆盖"仅保存（不测试）→ 进 workspace 验证选择器状态"这条具体用户路径；集成测试覆盖了 `list_available_providers` 的返回结构，但未断言"仅走保存接口后 `last_test_ok` 为 false 导致 selector 被禁用"这一端到端行为
- **`ServiceConfigTestView` 不写 `last_validated_at` 这一点，在现有单测和集成测试中均未被断言**

---

## 后续动作

- [ ] 用户 CONFIRM 推荐方案（方案 2 先行 + 方案 1 同步）
- [ ] 实施修复（新 commit，按提交前测试规则运行 `pytest apps/ tests/ -m "not integration"`）
- [ ] 修 E2E Playwright job 跳过问题（独立任务，已知问题）
- [ ] 补集成测试：`PUT /settings/services/llm_deepseek/` → verify `last_validated_at` 被写入，`GET /api/v1/llm/providers/` 返回 `last_test_ok=true`
- [ ] 补集成测试：`POST /settings/services/llm_deepseek/test/` 成功后 verify `last_validated_at` 被写入
- [ ] 补 E2E canary：模拟"仅保存不测试"→ 进 workspace → 断言 selector 非灰色（方案 1 实施后）
