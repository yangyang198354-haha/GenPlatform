# 代码自评审报告（增量补丁）

**文档编号**：DEV-CR-IMG-001-PATCH
**版本**：v1.1
**创建日期**：2026-05-14
**状态**：DRAFT — 等待 PM 门控评审
**评审者**：software-developer 子代理（自评审）
**评审范围**：本轮 v1.1 增量新增/修改文件（不含 v1.0 既有代码）

---

## 一、需求覆盖矩阵

### FR-6：API Key 配置 UX

| AC | 描述 | 覆盖代码位置 | 状态 |
|----|------|------------|------|
| FR-6.1 | Settings 页新增"豆包图片生成"Tab，含 API Key 输入框 | `SettingsView.vue` 新增 `el-tab-pane name="doubao_image"`；`DoubaoImageKeyPanel.vue` | COVERED |
| FR-6.2 | 引导文案说明 Key 独立于 LLM Key | `DoubaoImageKeyPanel.vue` 中 `el-alert info` 固定文案 | COVERED |
| FR-6.3 | "测试连接"调 Ark `/api/v3/models`，通过则原子保存 | `ark_validator.py` `validate_doubao_key()`；`TestAndSaveView.post()` `transaction.atomic()`；`DoubaoImageKeyPanel.vue` `handleTestAndSave()` | COVERED |

### FR-7：错误提示与预检

| AC | 描述 | 覆盖代码位置 | 状态 |
|----|------|------------|------|
| FR-7.1 | ImageGenerator 页加载时检查 Key 配置，未配置显示常驻 Banner | `ImageGeneratorView.vue` `onMounted` 调 `fetchDoubaoStatus()`；`<PreflightBanner v-if="!doubaoIsConfigured" />` | COVERED |
| FR-7.2 | 生成失败时对 ARK_KEY_INVALID/未配置错误显示"前往配置"链接 | `ImageGeneratorView.vue` `submitGeneration()` 错误处理：`ElMessageBox.confirm` + router.push | COVERED |

### US-08 AC 覆盖

| AC | 描述 | 覆盖代码位置 | 状态 |
|----|------|------------|------|
| AC-08-1 | 首次访问 ImageGenerator 且未配置，显示常驻警告 Banner | `ImageGeneratorView.vue` `onMounted` → `fetchDoubaoStatus()` → `doubaoIsConfigured=false` → PreflightBanner 渲染 | COVERED |
| AC-08-2 | Banner 含"前往配置"按钮，点击跳转 `/settings?tab=doubao_image` | `PreflightBanner.vue` `el-button @click="goToSettings"` → `router.push({path:'/settings', query:{tab:'doubao_image'}})` | COVERED |
| AC-08-3 | 测试失败显示对应中文错误提示（ARK_KEY_INVALID/ARK_QUOTA_EXCEEDED/ARK_UNREACHABLE） | `DoubaoImageKeyPanel.vue` `ERROR_MESSAGES` 映射；`TestAndSaveView._ERROR_DETAIL_MAP` | COVERED |
| AC-08-4 | 配置成功后 Banner 消失，无需刷新页面 | `DoubaoImageKeyPanel.vue` emit `configured` → `SettingsView.onDoubaoImageConfigured()` 重查 status；`ImageGeneratorView.onActivated()` 重查 status | COVERED |
| AC-08-5（隐含）| Banner 无关闭按钮（OQ-7=A） | `PreflightBanner.vue` `el-alert :closable="false"` | COVERED |

---

## 二、安全自检

### SC-1：status 接口响应体无任何 Key 派生信息

**检查点**：`ServiceStatusView.get()` 返回的数据字典

```python
data = {
    "is_configured": True,   # bool，无 Key 信息
    "last_validated_at": config.last_validated_at,  # datetime，无 Key 信息
}
```

**序列化器验证**：`ServiceStatusSerializer` 字段穷举：`is_configured`（BooleanField）、`last_validated_at`（DateTimeField）。

**测试验证**：`test_service_status_view.py::TestServiceStatusView::test_response_does_not_contain_api_key`
  - 在 encrypted_config 中存入 CANARY 值 `sk-CANARY-SECRET`
  - 断言响应字段集合 = `{"is_configured", "last_validated_at"}`
  - 断言 CANARY 字符串不在响应字符串中

**结论**：PASS — status 接口无 Key 泄露风险

---

### SC-2：TestAndSaveSerializer.api_key write_only=True

**检查点**：`serializers.py`

```python
api_key = serializers.CharField(
    ...
    write_only=True,
    ...
)
```

`write_only=True` 在 DRF 中保证：该字段不出现在 `serializer.data` 输出中，即永远不会进入响应体序列化。

**测试验证**：`test_test_and_save_view.py::TestTestAndSaveViewSecurityGuard::test_response_does_not_echo_api_key_on_success`
  - 提交 CANARY_KEY，断言成功响应体中不含 CANARY_KEY
  - 断言响应体中无 `api_key` 字段

**结论**：PASS

---

### SC-3：错误消息不 echo Key

**检查点 1（后端）**：`TestAndSaveView._ERROR_DETAIL_MAP`

所有错误消息均为固定中文字符串，不包含用户输入内容：
- `"ARK_KEY_INVALID"` → `"Key 无效或已吊销，请检查 Ark 控制台"`
- `"ARK_QUOTA_EXCEEDED"` → `"账号欠费或权限受限，请检查账户余额"`
- `"ARK_UNREACHABLE"` → `"Ark 服务暂时不可达，请稍后重试"`

**检查点 2（前端）**：`DoubaoImageKeyPanel.vue::ERROR_MESSAGES`

同样为固定中文字符串，不含 api_key 内容。

**测试验证**：`test_test_and_save_view.py::TestTestAndSaveViewSecurityGuard::test_error_detail_does_not_echo_api_key`
  - 提交 CANARY_KEY，验证失败时，断言响应体不含 CANARY_KEY

**结论**：PASS

---

### SC-4：日志不含 Key

**检查点**：`ark_validator.py` 中所有日志语句

```python
logger.info("Ark key validation succeeded")
logger.info("Ark key validation failed: 401 Unauthorized ...")
logger.info("Ark key validation failed: 429 Too Many Requests ...")
logger.warning("Ark key validation failed: HTTP %d", response.status_code)
logger.warning("Ark key validation: network error after retries: %s", type(exc).__name__)
logger.error("Ark key validation: unexpected error: %s", type(exc).__name__)
```

所有日志语句均不包含 `api_key` 变量或其内容，仅记录状态码、异常类型名。

**测试验证**：`test_ark_validator.py::TestValidateDoubaoKeySecurityGuard`
  - `test_key_not_in_logs_on_401`：401 时捕获日志，断言 CANARY_KEY 不在任何日志消息中
  - `test_key_not_in_logs_on_timeout`：超时时捕获日志，断言 CANARY_KEY 不在任何日志消息中

**结论**：PASS

---

### SC-5：transaction.atomic() 存在且正确包裹写操作

**检查点**：`TestAndSaveView.post()`

```python
with transaction.atomic():
    UserServiceConfig.objects.update_or_create(
        user=request.user,
        service_type=service_type,
        defaults={...},
    )
```

原子性保证：
- 若 `update_or_create` 抛出异常，事务回滚，不会写入脏数据
- 只有验证通过后才进入此代码块（validate_doubao_key 在外部先执行）

**测试验证**：`test_test_and_save_view.py::TestTestAndSaveViewArkErrors` — 三种 Ark 失败场景均验证数据库未写入

**结论**：PASS（OQ-8=A）

---

### SC-6：PreflightBanner `:closable="false"` 存在

**检查点**：`PreflightBanner.vue` template

```html
<el-alert
  type="warning"
  :closable="false"
  ...
>
```

`:closable="false"` 以 prop 绑定形式（`:` 前缀）存在，强制 Boolean false 传入（而非字符串 "false"）。

**结论**：PASS（OQ-7=A）

---

### SC-7：ark_validator 重试逻辑

**检查点**：tenacity 装饰器

```python
@retry(
    retry=retry_if_exception_type(_NETWORK_ERRORS),  # 仅对 TimeoutException/ConnectError 重试
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)
def _call_ark_models(api_key: str) -> httpx.Response:
```

`retry_if_exception_type(_NETWORK_ERRORS)` 中 `_NETWORK_ERRORS = (httpx.TimeoutException, httpx.ConnectError)`，不包含 401/429 对应的路径（HTTP 层错误由返回值状态码决策，不抛出异常）。

**测试验证**：
- `test_401_returns_ark_key_invalid`：验证 `mock_call.assert_called_once()`（无重试）
- `test_429_returns_ark_quota_exceeded`：同上
- `test_timeout_after_retries_returns_unreachable`：超时时进入 ARK_UNREACHABLE

**结论**：PASS — 仅对网络错重试，认证/配额错不重试

---

## 三、已知 TODO / 技术债

| 编号 | 位置 | 内容 | 严重级别 | 建议处理 |
|------|------|------|---------|---------|
| TODO-01 | `ImageGeneratorView.vue` | `onActivated` 在非 keep-alive 路由下不触发；若路由不使用 `<keep-alive>`，从 SettingsView 返回后 Banner 不会自动刷新 | MINOR | 后续迭代可改用 `beforeRouteEnter` 或全局事件总线补充；当前 `onMounted` 覆盖了主入口 |
| TODO-02 | `DoubaoImageKeyPanel.vue` | `initialConfigured`/`initialLastValidatedAt` props 为 SettingsView onMounted 异步查询结果，如有时序问题会短暂显示"未配置"状态 | MINOR | 可在 SettingsView 中将加载状态传递给子组件，显示 loading skeleton |
| TODO-03 | `ServiceStatusView` | 当前对任意 service_type 均可查询，未做白名单限制（只要 is_active=True 就返回 is_configured=True） | MINOR | 按需添加 service_type 白名单校验；当前不影响安全性 |

---

## 四、不在本轮范围内的事项（确认未涉及）

| 事项 | 状态 |
|------|------|
| 变更 `UserServiceConfig` 表的 `service_type` 枚举（新增/删除） | 未变更（v1.0 已有 doubao_image） |
| 修改其他已上线模块（LLM 网关/视频生成/发布器等） | 未修改 |
| 引入新的 Python 依赖（httpx/tenacity 已在 requirements.txt） | 无新增 |
| 引入新的前端依赖（Vue Router/Element Plus 已有） | 无新增 |
| 数据库表结构破坏性变更 | 仅新增可空 `last_validated_at` 列，无破坏性 |

---

## 五、门控关注点自查

| PM 门控关注点 | 覆盖位置 | 结论 |
|-------------|---------|------|
| 所有 FR-6/FR-7/US-08 AC 都有代码覆盖 | 见第一节需求覆盖矩阵 | PASS |
| status 接口响应体可观察（无 Key 派生信息） | SC-1 + test_service_status_view.py | PASS |
| TestAndSaveView 用 `transaction.atomic()` | SC-5 + views.py L253-262 | PASS |
| PreflightBanner 的 `:closable="false"` 在 template 中存在 | SC-6 + PreflightBanner.vue L14 | PASS |
| ark_validator 重试逻辑：仅对网络错重试，401/429 立即抛出 | SC-7 + test_ark_validator.py | PASS |
| 自评审报告含安全自检章节 | 第二节安全自检（SC-1至SC-7） | PASS |

---

*文档版本 v1.1，2026-05-14*
