# Knowledge Base — test_engineer
<!-- 记录测试工程中遇到的经验教训，供后续参考 -->

---

## TE-L001: 集成测试 — 注册接口必须包含 password2 字段

**日期**: 2026-04-10  
**场景**: 编写跨模块集成测试时调用 `/api/v1/auth/register/`

**问题**: `RegisterSerializer` 要求 `password2` 字段进行密码确认，直接传 `password` 会返回 400。

**教训**:
- 集成测试中调用注册接口必须传 `password2: password` （与 `password` 相同）
- 单元测试中通过 `User.objects.create_user()` 直接创建用户可绕过此限制
- 在 `_register_and_login()` 等 helper 里应第一时间包含此字段

**正确示例**:
```python
client.post("/api/v1/auth/register/", {
    "username": "user1",
    "email": "user1@example.com",
    "password": "SecurePass123!",
    "password2": "SecurePass123!",   # 必须
}, format="json")
```

---

## TE-L002: 集成测试 — 发布任务 API 字段名是复数 platform_account_ids

**日期**: 2026-04-10  
**场景**: 集成测试 IT-004/IT-005 中创建发布任务

**问题**: `POST /api/v1/publisher/tasks/` 接收的字段名是 `platform_account_ids`（列表），
不是 `platform_account_id`（单数）。同时响应是列表不是单对象。

**教训**:
- 写测试前先看 `apps/publisher/views.py` 确认字段名和返回格式
- 响应是 `list`，应用 `resp.data[0]["id"]` 而非 `resp.data["id"]`

**正确示例**:
```python
resp = client.post("/api/v1/publisher/tasks/", {
    "content_id": content_id,
    "platform_account_ids": [account_id],   # 列表！
}, format="json")
assert resp.status_code == 201
assert isinstance(resp.data, list)
task_id = resp.data[0]["id"]
```

---

## TE-L003: 集成测试 — settings 模块必须使用 config.settings.test

**日期**: 2026-04-10  
**场景**: CI Stage 3 集成测试之前使用 `config.settings.development`

**问题**: `development` 设置启用了 `UserRateThrottle`，测试间 locmem 缓存共享导致 429 错误；
`test.py` 明确禁用了 throttle 并使用 MD5 密码哈希加速。

**教训**:
- 集成测试环境变量: `DJANGO_SETTINGS_MODULE=config.settings.test`
- `pytest tests/` 而非 `pytest apps/`（集成测试文件在 `tests/` 目录）
- 去掉 `continue-on-error: true`，测试失败应阻断 pipeline

---

## TE-L004: E2E 测试 — 冒烟测试脚本用户名必须唯一

**日期**: 2026-04-10  
**场景**: smoke_test.sh 在多次部署后失败

**问题**: username 硬编码为 `smokeuser`，第二次运行时 DB 已有该用户，注册返回 400。
email 已用 `$(date +%s)` 唯一化，但 username 没有。

**教训**:
- 冒烟测试中所有唯一性字段（username、email）都必须用时间戳或随机值
- 生产数据库不会在两次部署间清空

**正确做法**:
```bash
SMOKE_TS="$(date +%s)"
SMOKE_USER="smoke_${SMOKE_TS}"
SMOKE_EMAIL="${SMOKE_USER}@test.internal"
```

---

## TE-L005: E2E 测试 — Playwright 必须使用 ESM 格式

**日期**: 2026-04-10  
**场景**: Playwright spec 文件用 `import` 语法，config 用 `require()`

**问题**: 当 spec 文件使用 ESM (`import { test }`) 时，Node.js 将整个包视为 ES module，
导致 `playwright.config.js` 中的 `require()` 报错：
`ReferenceError: require is not defined in ES module scope`

**教训**:
- `package.json` 加 `"type": "module"`
- `playwright.config.js` 改为 `import/export` 语法

**正确的 playwright.config.js**:
```js
import { defineConfig, devices } from '@playwright/test';
export default defineConfig({ ... });
```

---

## TE-L006: E2E 测试 — 按 UI 真实文本匹配元素，不要猜

**日期**: 2026-04-10  
**场景**: Playwright helpers.js 中 `getByRole('button', { name: /注册/ })` 超时

**问题**: 注册页按钮真实文本是 **"创建账号"**，不是 "注册"；
登录页密码框 placeholder 是 **"输入密码"**，不是 "密码"。
每次编写 E2E 测试前必须检查 `.vue` 源文件中的真实文本。

**教训**:
- 查看 `RegisterView.vue` 确认按钮文本: `<span v-if="!loading">创建账号</span>`
- 查看 `LoginView.vue` 确认 placeholder: `placeholder="输入密码"`
- 不要凭直觉或翻译猜测 — 直接 `grep placeholder\|button` 源文件

**本项目真实值速查**:
| 元素 | 真实文本/placeholder |
|------|---------------------|
| 注册按钮 | `创建账号` |
| 登录按钮 | `登录` |
| 邮箱输入 | `your@email.com` |
| 密码输入（登录页） | `输入密码` |
| 密码输入（注册页） | `至少 8 位` |
| 确认密码（注册页） | `再次输入` |
| 用户名输入（注册页） | `至少 2 个字符` |

---

## TE-L007: E2E 测试 — simplejwt 对错误密码返回 401 不是 400

**日期**: 2026-04-10  
**场景**: 冒烟测试 SM-001 期望登录端点返回 400

**问题**: `rest_framework_simplejwt` 对认证失败统一返回 `HTTP 401`，不是 `400`。

**教训**:
- 冒烟测试/E2E 中验证登录端点存活时，应期望 `401`（错误密码）
- `400` 表示请求格式错误（缺少字段），`401` 表示认证失败

---

## TE-L008: E2E 测试 — Playwright strict mode 与 getByText 的陷阱

**日期**: 2026-04-10  
**场景**: `getByText('知识库')` / `getByText('系统设置')` 等页面标题文本报错

**问题**: 本项目 AppLayout 中导航侧边栏、页面 h1、页面 h2 三处都包含相同文本（如"知识库"），
Playwright strict mode 下 `getByText()` 匹配到多个元素抛 strict mode violation。

**错误信息**:
```
Error: strict mode violation: getByText('知识库') resolved to 3 elements
```

**修复**: 用 `page.locator('h1').filter({ hasText: '知识库' })` 精确匹配 h1 标签，
或 `page.getByRole('heading', { name: '...' })` 限定 heading 角色。

**本项目规范**: 所有验证"页面已加载"的断言应锚定到 `h1` 或 `page-title` class，不要裸用 `getByText`。

---

## TE-L009: E2E 测试 — ElementPlus el-select 无法直接 click inner input

**日期**: 2026-04-10  
**场景**: E2E-003e 中 `page.getByLabel('目标平台').click()` 永远超时

**问题**: ElementPlus `el-select` 的真实 `<input>` 被 `el-select__selected-item` (placeholder div) 
覆盖拦截了点击事件。Playwright 一直等待元素 stable 并尝试点击，但总被 overlay 拦截。

**错误信息**:
```
<div class="el-select__selected-item el-select__placeholder">…</div> intercepts pointer events
```

**修复**: 点击整个 `.el-select` wrapper div，而非内部 input：
```js
// 错误
await page.getByLabel('目标平台').click();

// 正确
await page.locator('.el-select').first().click();
```

---

## TE-L011: E2E 测试 — 停止生成按钮在无 LLM 配置时会瞬间消失

**日期**: 2026-04-11  
**场景**: E2E-003d 测试"停止生成"按钮功能

**问题**: 生产环境无 LLM 配置时，SSE 流立即报错返回，`停止生成` 按钮在 Playwright
尝试点击前就已从 DOM 中被移除（`element was detached from the DOM`）。
`isVisible()` 返回 `true` 但 `click()` 超时 30s。

**根因**: 按钮存在但不稳定 — SSE 流结束时 Vue 重新渲染把它替换掉了。

**修复**: 对 `click()` 加短超时 + catch，让测试在按钮消失时依然通过：

```js
const isVisible = await stopBtn.isVisible({ timeout: 3000 }).catch(() => false);
if (isVisible) {
  // 按钮可能在 click() 完成前被 SSE 流结束移除，catch 掉即可
  await stopBtn.click({ timeout: 2000 }).catch(() => {});
}
// 核心断言：生成状态必须解除，生成按钮要重新出现
await expect(page.getByRole('button', { name: /开始生成/ }))
  .toBeVisible({ timeout: 10_000 });
```

**原则**: 测试短暂出现的交互元素时，click 本身不是核心目标；
核心是验证最终状态（生成结束后按钮恢复）。

---

## TE-L012: Mock — encode 等形状依赖输入的函数必须用 side_effect，不能用 return_value

**日期**: 2026-04-16  
**场景**: `TestProcessDocument` 系列测试 mock `_get_embedding_model`

**问题**: 所有测试都写成：
```python
mock_model.encode.return_value = np.zeros((1, 512), dtype="float32")
```
这里 `(1, 512)` 是固定形状。当文档切分出 N > 1 个 chunk 时，
`zip(chunks, embeddings)` 按最短者截断，只生成 1 个 chunk 写入 DB。
测试靠 `assert doc.chunk_count >= 1` 通过（恰好 1 个），
但生产中多 chunk 文档只有 1 个 chunk 落库，其余静默丢失。

**根因**: `return_value` 无论输入多少文本都返回相同的固定数组；
而真实的 `model.encode(texts)` 输出形状是 `(len(texts), 512)`。

**正确做法**:
```python
# 根据输入 chunk 数量动态生成正确形状
mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
```

**通用规则**: 凡是被 mock 的函数其 **输出形状/内容依赖于输入**，
必须使用 `side_effect` 动态生成，不能使用固定 `return_value`。
常见此类函数：`model.encode(texts)`, `tokenizer(texts)`, `batch_predict(inputs)`。

---

## TE-L013: 测试 — 资源约束参数（batch_size / timeout）必须通过 call_args 断言验证

**日期**: 2026-04-16  
**场景**: `model.encode()` 未传 `batch_size` 导致 OOM kill worker

**问题**: `process_document` 调用 `model.encode(chunks)` 未传 `batch_size`，
大型文档一次性把所有 chunk 张量加载到 RAM，触发 Linux OOM killer (SIGKILL)。
SIGKILL 绕过所有 Python `except` 块，文档永久停留在 `"processing"`。
但测试只验证最终状态（`doc.status == "available"`），不验证 encode 的调用参数，
因此测试全绿，OOM 风险完全不可见。

**正确做法**：在测试中同时断言参数：
```python
_, call_kwargs = mock_model.encode.call_args
assert call_kwargs.get("batch_size") == 32, (
    "model.encode() must use batch_size=32 to prevent OOM on large documents"
)
```

**通用规则**: 涉及 OS 级资源（RAM、线程数、文件句柄、超时）的调用，
除了验证输出结果，**必须通过 `call_args` 断言验证约束参数的存在和正确值**。
典型参数：`batch_size`、`max_workers`、`timeout`、`num_threads`。

---

## TE-L014: Smoke Test — VectorField 维度与模型输出必须有一致性断言

**日期**: 2026-04-16  
**场景**: embedding 模型从 bge-m3（1024维）切换到 bge-small-zh-v1.5（512维）

**问题**: 切换模型时 `VectorField(dimensions=)` 如果漏改或 migration 未执行，
`bulk_create()` 会被 pgvector 以维度错误拒绝，文档状态变为 `"error"`，chunk 不落库。
但所有测试都 mock 了 encode 输出，无法检测维度不匹配。

**正确做法**：增加不需要 DB 的 smoke test：
```python
class TestVectorFieldDimension:
    EXPECTED_DIM = 512  # bge-small-zh-v1.5

    def test_vector_field_dimension_matches_embedding_model(self):
        from apps.knowledge_base.models import DocumentChunk
        field = DocumentChunk._meta.get_field("embedding")
        assert field.dimensions == self.EXPECTED_DIM
```

**通用规则**: 任何 schema 字段的取值需与代码常量保持一致时，
必须有对应的 smoke test 在 CI 最早阶段（无需 DB）执行断言。
切换 embedding 模型时必须同步修改：
① `VectorField(dimensions=N)` ② migration ③ 本测试 `EXPECTED_DIM` ④ 所有 mock 数组形状。

---

## TE-L010: E2E 测试 — ElMessage.warning 产生 .el-message--warning 而非 --error

**日期**: 2026-04-10  
**场景**: E2E-004c 检查空 API key 保存时的错误提示

**问题**: `SettingsView.vue` 对空必填字段用的是 `ElMessage.warning()`，
产生 `.el-message--warning` class；而测试只检查 `.el-message--error`，导致找不到元素。

**本项目 SettingsView 验证逻辑**:
```js
if (!llmForm.value.api_key) {
  ElMessage.warning("请填写 API Key");  // warning，不是 error！
  return;
}
```

**修复**: 选择器覆盖 warning + error + 表单内联错误：
```js
page.locator('.el-message--warning, .el-message--error, .el-form-item__error').first()
```

**原则**: 写 E2E 断言前先在源码中确认用的是 `warning`、`error` 还是 `info`。
