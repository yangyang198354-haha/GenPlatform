# LLM 选择功能集成测试报告（PR-5）

**日期**：2026-05-15
**版本**：v1.0

---

## 测试用例清单

### A.1 集成测试（test_integration.py，全部 @pytest.mark.integration）

| 编号 | 测试类 / 方法 | 对应 US/AC | 预期状态 |
|------|-------------|----------|---------|
| INT-01 | `TestPostHappyPath::test_post_with_explicit_provider_model_returns_sse_and_audits` | US-01/AC-01, US-07/AC-08 | CI 通过 |
| INT-02 | `TestGetBackwardCompatIntegration::test_get_without_provider_model_uses_resolve_default` | NFR-03 | CI 通过 |
| INT-03 | `TestResolveDefaultIntegration::test_branch1_valid_preference_is_used` | US-03/AC-US03-2, AC-03 | CI 通过 |
| INT-04 | `TestResolveDefaultIntegration::test_branch2_no_preference_deepseek_valid_returns_deepseek` | US-01/AC-02 | CI 通过 |
| INT-05 | `TestResolveDefaultIntegration::test_branch3_preference_invalid_deepseek_valid_falls_back_to_deepseek` | US-03/AC-US03-3 | CI 通过 |
| INT-06 | `TestResolveDefaultIntegration::test_branch4_no_preference_no_deepseek_returns_400` | US-04/AC-US04-2 | CI 通过 |
| INT-07 | `TestResolveDefaultIntegration::test_branch4b_only_valid_volcano_and_no_preference_uses_volcano` | FR-LLM-SEL-02 step 3 | CI 通过 |
| INT-08 | `TestContentAuditFields::test_content_provider_model_fields_are_writable` | US-07/AC-US07-1, AC-08 | CI 通过 |
| INT-09 | `TestContentAuditFields::test_historical_content_provider_model_are_null` | US-07/AC-US07-2 | CI 通过 |
| INT-10 | `TestContentAuditFields::test_generate_persists_preference_which_implies_provider_model_known` | US-07/AC-US07-1 | CI 通过 |
| INT-11 | `TestUserLLMPreferencePersistence::test_first_generate_creates_preference` | US-03/AC-US03-1, AC-05 | CI 通过 |
| INT-12 | `TestUserLLMPreferencePersistence::test_second_generate_updates_preference` | US-03/AC-US03-1, AC-05 | CI 通过 |
| INT-13 | `TestFailureDoesNotPersistPreference::test_stream_error_does_not_create_preference` | US-05 | CI 通过 |
| INT-14 | `TestFailureDoesNotPersistPreference::test_stream_error_does_not_overwrite_existing_preference` | US-05 | CI 通过 |
| INT-15 | `TestListModelsTimeoutFallback::test_volcano_list_models_timeout_returns_fallback` | US-06/AC-US06-1, AC-06 | CI 通过 |
| INT-16 | `TestListModelsTimeoutFallback::test_deepseek_list_models_timeout_returns_fallback` | US-06/AC-US06-1, AC-06 | CI 通过 |
| INT-17 | `TestProvidersEndToEndStructure::test_dual_provider_response_structure` | FR-LLM-SEL-01/AC-01 | CI 通过 |
| INT-18 | `TestProvidersEndToEndStructure::test_no_config_user_gets_empty_providers` | US-04 | CI 通过 |
| INT-19 | `TestProvidersEndToEndStructure::test_both_providers_valid_default_is_deepseek` | AC-02 | CI 通过 |
| INT-20 | `TestProvidersEndToEndStructure::test_user_preference_returned_when_valid` | US-03/AC-03 | CI 通过 |
| INT-21 | `TestProvidersEndToEndStructure::test_invalid_preference_not_returned` | US-03/AC-US03-3 | CI 通过 |

### A.2 Canary 守卫扩展（test_selectors.py，TestWhitelistCanary 类下）

| 编号 | 测试方法 | 说明 | 状态 |
|------|---------|------|------|
| CAN-01 | `test_canary_default_model_is_deepseek_v3` | 断言 MODEL_WHITELIST["llm_deepseek"][0]["id"] == "deepseek-chat" | 本地通过 |
| CAN-02 | `test_canary_supported_service_types_exact_list` | 断言 SUPPORTED_LLM_SERVICE_TYPES == ["llm_deepseek", "llm_volcano"] | 本地通过 |
| CAN-03 | `test_canary_volcano_whitelist_includes_doubao_pro_32k` | 断言 doubao-pro-32k 在白名单中 | 本地通过 |

---

## 测试数量汇总

| 类型 | 文件 | 数量 |
|------|------|------|
| 集成测试（新增） | `test_integration.py` | 21 |
| Canary 守卫（新增） | `test_selectors.py` 扩展 | 3 |
| **PR-5 新增小计** | | **24** |

---

## 已知风险

1. **本地无 PG**：`test_integration.py` 全部标注 `@pytest.mark.integration`，本地无 PostgreSQL 环境时自动跳过，由 GitHub Actions CI 的 `test-integration` job 负责执行。

2. **Content.provider/model 写入路径**：当前实现中 `_sync_sse_generator` 直接写 `UserLLMPreference`，`Content` 记录由前端另行调用 `/api/v1/contents/` 创建。INT-08/09/10 通过验证 ORM 字段可写入和 SSE done 事件含 used_provider/used_model 来间接覆盖，而非验证单次 HTTP 生成后 Content 表已写入（这需要 E2E 或前端协作）。

3. **E2E 依赖 auth.setup.ts**：`llm_selection.spec.ts` 依赖 auth.setup.ts 的登录前置步骤（`storageState: 'e2e/.auth/user.json'`）。CI 环境需预先创建测试账号 `e2e_user / e2e_pass_123`。

4. **tooltip headless 环境**：US-05 的 tooltip hover 断言在某些 headless CI 环境可能无法触发 tooltip 展示，测试做了降级处理（检查 disabled-wrap 元素的可见性）。
