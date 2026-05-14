# 测试计划 v1.1 — 豆包图片迁移 UX 修复迭代

**文档版本**：v1.1
**迭代范围**：content_gen_platform — 豆包图片迁移 UX 修复（FR-6 / FR-7 / US-08）
**负责人**：test-engineer 子代理
**日期**：2026-05-14
**关联需求**：requirements_spec_v0.3.md（FR-6, FR-7）、user_stories.md（US-08）
**关联架构**：architecture_design_v1.1.md（ADR-08, ADR-09, ADR-10）

---

## 1. 测试范围

### 1.1 本次迭代新增 / 修改的代码（测试覆盖目标）

| 文件 | 变更类型 | 测试必要性 |
|------|---------|----------|
| `apps/settings_vault/ark_validator.py` | 新增 | 必须全面覆盖（核心验权逻辑） |
| `apps/settings_vault/views.py`（ServiceStatusView） | 新增 | 必须全面覆盖（ADR-09 响应安全） |
| `apps/settings_vault/views.py`（TestAndSaveView） | 新增 | 必须全面覆盖（ADR-10 原子性） |
| `apps/settings_vault/serializers.py`（新增两个 Serializer） | 新增 | 单元测试（序列化/反序列化行为） |
| `apps/settings_vault/models.py`（last_validated_at 字段） | 修改 | 集成测试（迁移验证） |
| `apps/settings_vault/urls.py`（新路由 status / test-and-save） | 修改 | 路由可达性（通过视图测试覆盖） |
| `apps/settings_vault/migrations/0003_*` | 新增 | 集成测试（迁移正向/回滚） |

### 1.2 不在本次测试范围内

- 前端 Vue 组件（`DoubaoImageKeyPanel.vue`, `PreflightBanner.vue`）——E2E 测试
- 未修改的 `apps/image_generator/` 代码（已有测试，无本次变更）
- 旧有 `ServiceConfigListView` / `ServiceConfigDetailView`（已有测试覆盖）

---

## 2. 测试矩阵：需求 → 测试用例 ID 映射

### FR-6 覆盖矩阵（Key 配置入口）

| 需求 ID | 需求描述 | 测试类 | 测试用例 ID | 文件 |
|--------|---------|-------|-----------|------|
| FR-6.3 | 调用 Ark /api/v3/models 验证 Key 有效性 | TestValidateDoubaoKeySuccess | test_200_returns_true_empty_error | test_ark_validator.py |
| FR-6.3 | 401 → ARK_KEY_INVALID，不重试 | TestValidateDoubaoKeyAuthErrors | test_401_returns_ark_key_invalid | test_ark_validator.py |
| FR-6.3 | 429 → ARK_QUOTA_EXCEEDED，不重试 | TestValidateDoubaoKeyAuthErrors | test_429_returns_ark_quota_exceeded | test_ark_validator.py |
| FR-6.3 | 网络错误 → ARK_UNREACHABLE | TestValidateDoubaoKeyNetworkErrors | test_timeout_after_retries_returns_unreachable | test_ark_validator.py |
| FR-6.3 | ConnectError → ARK_UNREACHABLE | TestValidateDoubaoKeyNetworkErrors | test_connect_error_after_retries_returns_unreachable | test_ark_validator.py |
| FR-6.3 | 测试通过原子保存 | TestTestAndSaveViewSuccess | test_valid_key_saves_and_returns_200 | test_test_and_save_view.py |
| FR-6.3 | 验证失败不入库 | TestTestAndSaveViewArkErrors | test_ark_key_invalid_returns_400_no_db_write | test_test_and_save_view.py |
| FR-6.1 | api_key 不回显（write_only） | TestTestAndSaveViewSecurityGuard | test_response_does_not_echo_api_key_on_success | test_test_and_save_view.py |

### FR-7 覆盖矩阵（Banner 状态查询）

| 需求 ID | 需求描述 | 测试类 | 测试用例 ID | 文件 |
|--------|---------|-------|-----------|------|
| FR-7.1 | 未配置 → is_configured=False | TestServiceStatusView | test_returns_not_configured_when_no_record | test_service_status_view.py |
| FR-7.1 | 已配置且激活 → is_configured=True | TestServiceStatusView | test_returns_configured_when_active_record_exists | test_service_status_view.py |
| FR-7.1 | is_active=False → is_configured=False | TestServiceStatusView | test_returns_not_configured_when_inactive_record | test_service_status_view.py |
| FR-7.1 | 响应不含 api_key（安全守卫） | TestServiceStatusView | test_response_does_not_contain_api_key | test_service_status_view.py |
| FR-7.1 | 用户数据隔离 | TestServiceStatusView | test_status_is_user_scoped | test_service_status_view.py |

### US-08 全 AC 覆盖矩阵

| AC ID | AC 描述 | 测试类型 | 测试用例 ID | 文件 | 通过标准 |
|-------|---------|---------|-----------|------|---------|
| AC-08-1 | 未配置 → 预检 Banner 状态查询返回 is_configured=False | 单元 | test_returns_not_configured_when_no_record | test_service_status_view.py | 断言 is_configured=False |
| AC-08-2 | Banner "前往配置"跳转 /settings?tab=doubao_image | E2E（Playwright，CI） | — | — | URL 断言 |
| AC-08-3 | 测试连接调 Ark /api/v3/models 验权 | 单元 | test_401_returns_ark_key_invalid + test_200_returns_true_empty_error | test_ark_validator.py | mock Ark 响应，断言返回值 |
| AC-08-4 | 测试成功自动保存 + Banner 消失（status 变 configured） | 单元 | test_valid_key_saves_and_returns_200 + test_returns_configured_when_active_record_exists | test_test_and_save_view.py + test_service_status_view.py | saved=True + is_configured=True |
| AC-08-5 | 未配置时直接提交 → 错误消息含可点击"前往配置"链接 | E2E（Playwright，CI） | — | — | DOM 断言 |

> 说明：AC-08-2 和 AC-08-5 为纯前端行为，由 Playwright E2E 测试覆盖（CI 运行）。

---

## 3. Canary 守卫清单

| 守卫名称 | 保护目标 | 测试用例 ID | 文件 |
|---------|---------|-----------|------|
| status 响应字段穷举守卫 | 响应体仅含 is_configured + last_validated_at，不含 Key 派生 | test_response_does_not_contain_api_key | test_service_status_view.py |
| TODO-03 service_type 白名单守卫 | 未知 service_type → 400 + INVALID_SERVICE_TYPE | test_invalid_service_type_returns_400_canary_guard | test_service_status_view.py |
| TestAndSave api_key 不回显守卫 | 成功 / 失败响应均不含 api_key 内容 | test_response_does_not_echo_api_key_on_success + test_error_detail_does_not_echo_api_key | test_test_and_save_view.py |
| ark_validator 日志不含 Key 守卫 | 日志记录中不出现 api_key 值 | test_key_not_in_logs_on_401 + test_key_not_in_logs_on_timeout | test_ark_validator.py |
| TestAndSave 原子性守卫 | 中途异常时 DB 无脏记录 | test_db_write_rolled_back_if_encrypt_raises | test_test_and_save_view.py |
| 用户数据隔离守卫 | 用户 A 的配置对用户 B 不可见 | test_status_is_user_scoped + test_user_isolation | test_service_status_view.py + test_test_and_save_view.py |

---

## 4. Mock 策略

### 4.1 Ark API Mock（核心约束：严禁真实调用）

**工具**：`unittest.mock.patch`（直接 patch `_call_ark_models`）

```
patch("apps.settings_vault.ark_validator._call_ark_models", return_value=<MagicMock>)
```

- Mock 层级：在 `_call_ark_models` 函数级别 patch，不在 httpx 层级（避免 tenacity 重试逻辑干扰测试时序）
- 网络错误测试：`side_effect=httpx.TimeoutException(...)` 或 `side_effect=httpx.ConnectError(...)`
- 重试验证：通过 `mock_call.assert_called_once()` 验证 401/429 不触发重试

**TestAndSaveView 层面 Mock**（在视图测试中）：

```
patch("apps.settings_vault.views.validate_doubao_key", return_value=(ok, code))
```

- 理由：视图测试关注的是视图逻辑（路由 + 序列化 + 数据库写入），不重复测试验证逻辑

### 4.2 DB 隔离

- 使用 `@pytest.mark.django_db` + Django test 内置事务回滚
- 每个测试方法自动隔离，不依赖测试顺序

### 4.3 加密模块

- `core.encryption.encrypt / decrypt` 不 Mock，使用测试专用 settings（`config.settings.local_test`）中配置的测试密钥

---

## 5. 集成测试范围（@pytest.mark.integration，CI 负责）

| 测试 ID | 测试场景 | 依赖 | 文件 |
|--------|---------|------|------|
| INT-01 | 登录 → GET status（未配置）→ POST test-and-save（mock Ark 200）→ GET status（已配置）→ POST 生成（Celery 同步）→ 入素材库 | PostgreSQL, Redis, Celery | test_integration.py（image_generator） |
| INT-02 | Migration 0003 正向 apply | PostgreSQL | CI schema check |
| INT-03 | Migration 0003 回滚 revert | PostgreSQL | CI schema check |

---

## 6. 测试执行命令

### 本地单元测试（-m "not integration"）

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.local_test"
Set-Location C:\Users\yanggyan\MyProject\GenPlatform\project_workspace\content_gen_platform\src\backend
python -m pytest apps/settings_vault/tests/ apps/image_generator/tests/ -m "not integration" --tb=short -q
```

### 仅本迭代新增测试

```powershell
python -m pytest apps/settings_vault/tests/test_ark_validator.py apps/settings_vault/tests/test_service_status_view.py apps/settings_vault/tests/test_test_and_save_view.py -m "not integration" --tb=short -v
```

---

## 7. 通过门控标准

- 单元测试通过率：100%（0 failed, 0 error）
- 所有 US-08 AC 有对应单元测试（AC-08-2 / AC-08-5 除外，由 E2E 覆盖）
- ark_validator 错误分支：401 / 429 / ConnectError / TimeoutException / 其他异常 — 各至少 1 例
- TestAndSaveView 原子性测试：存在并通过
- ServiceStatusView Canary 守卫：白名单拒绝测试通过
- 集成测试：不在本地强制，由 CI 负责
