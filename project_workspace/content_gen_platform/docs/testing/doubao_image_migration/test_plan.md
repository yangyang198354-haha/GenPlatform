# 测试计划：豆包 Seedream 图片生成接入

```
file_header:
  document_id: TEST-PLAN-DOUBAO-001
  version: 1.0
  status: DRAFT
  author_agent: sub_agent_test_engineer
  project: content_gen_platform
  feature: doubao_image_migration
  created_at: 2026-05-13
```

---

## 1. 测试范围与策略

### 1.1 测试目标

验证豆包 Seedream 图片生成接入（即梦替换）功能满足以下需求文档中的所有验收条件：

- 需求规格：`docs/requirements/doubao_image_migration/requirements_spec.md`（v0.2 APPROVED）
- 用户故事：`docs/requirements/doubao_image_migration/user_stories.md`（v0.2 APPROVED）

### 1.2 测试层次

| 层次 | 工具 | 标记 | 运行时机 | 负责方 |
|------|------|------|---------|--------|
| 单元测试（无 DB） | pytest | 无标记 / `unit` | 本地 + CI | 开发者 / CI |
| 单元测试（含 DB） | pytest + Django TestClient | `django_db` | 本地（SQLite）+ CI（PG） | 开发者 / CI |
| 集成测试 | pytest | `integration` | CI 仅 | CI（PostgreSQL + Celery） |
| E2E 测试 | Playwright | 无标记 | CI 仅（可选） | CI |

### 1.3 测试策略

**本地执行约束（CLAUDE.md 强制）：**
```bash
cd project_workspace/content_gen_platform/src/backend
pytest apps/ tests/ -m "not integration" --tb=short -q
```

- 本地使用 SQLite（`config.settings.local_test`）运行含 `django_db` 的单元测试
- 标记为 `integration` 的测试仅在 CI（GitHub Actions）中运行
- 所有测试均禁止调用真实 Ark API（使用 mock httpx）
- 所有测试均禁止硬编码任何 API Key

---

## 2. 用户故事 AC 到测试用例映射矩阵

### US-01：选择豆包模型版本

| AC 编号 | 验收条件描述 | 测试文件 | 测试用例 ID/函数名 |
|---------|------------|---------|-----------------|
| AC-01-1 | 界面展示三个豆包模型选项 | test_serializers.py | test_supported_model_50_lite_is_valid, test_supported_model_45_is_valid, test_supported_model_40_is_valid |
| AC-01-2 | 提交生成返回 202 + batch_id | test_views.py | TestImageGenerationSubmitView::test_submit_valid_prompt_returns_202 |
| AC-01-4 | API Key 缺失时批次置为 failed | test_tasks.py | TestGenerateImageTaskDoubao::test_task_fails_when_no_doubao_config |
| AC-01-5 | 不支持的模型返回 400 | test_views.py, test_serializers.py | test_submit_invalid_model_returns_400, test_unsupported_model_jimeng_is_rejected |

### US-02：文生图（文字描述生成图片）

| AC 编号 | 验收条件描述 | 测试文件 | 测试用例 ID/函数名 |
|---------|------------|---------|-----------------|
| AC-02-1 | 有效提示词提交成功 | test_views.py | test_submit_valid_prompt_returns_202 |
| AC-02-3 | 参考图 GIF 格式返回 400 | test_views.py | test_submit_invalid_ref_image_format_returns_400 |
| AC-02-5 | 任务结束清理参考图临时文件 | test_tasks.py | （通过 _cleanup_ref_image 间接覆盖） |

### US-03：图生图（参考图 + 提示词）

| AC 编号 | 验收条件描述 | 测试文件 | 测试用例 ID/函数名 |
|---------|------------|---------|-----------------|
| AC-03-1 | 生成成功，MediaItem 创建 | test_tasks.py | test_task_completes_successfully_single_image |
| AC-03-4 | 完成时推送 WebSocket 事件 | test_tasks.py | test_task_completes_successfully_single_image（验证 push_notification 调用） |
| AC-03-ref | 参考图 base64 编码传入 Ark | test_doubao_client.py | TestDoubaoImageClientAdvancedParams::test_build_request_body_includes_ref_image |

### US-04：批次生成（1-4 张）

| AC 编号 | 验收条件描述 | 测试文件 | 测试用例 ID/函数名 |
|---------|------------|---------|-----------------|
| AC-04-1 | 批次名 MMDD-HHmm 格式 | test_views.py | test_batch_name_format |
| AC-04-3 | 4 张全部成功 status=completed | test_tasks.py | test_task_batch_status_update_to_completed |
| AC-04-4 | 部分失败 status=partial_failed | test_tasks.py | test_task_handles_partial_failure |
| AC-04-5 | n>4 返回 400（Canary 守卫） | test_serializers.py + test_views.py | **test_n_equals_5_is_rejected_canary_guard** + test_submit_n_exceeds_4_returns_400 |
| AC-04-DB | DB CheckConstraint 0/5 张拒绝 | test_models.py | test_total_count_0_violates_constraint + test_total_count_5_violates_constraint |

### US-05：批次历史管理

| AC 编号 | 验收条件描述 | 测试文件 | 测试用例 ID/函数名 |
|---------|------------|---------|-----------------|
| AC-05-1 | 批次列表仅返回当前用户 | test_views.py | TestImageBatchListView::test_list_batches_own_only |
| AC-05-2 | 批次详情含图片列表 | test_views.py | TestImageBatchDetailView::test_get_batch_detail |
| AC-05-3 | PATCH 重命名批次 | test_views.py | test_rename_batch |
| AC-05-4 | DELETE 已完成批次返回 204 | test_views.py | test_delete_batch_completed |
| AC-05-5 | DELETE 生成中批次返回 409 | test_views.py | test_delete_batch_processing_returns_409 |

---

## 3. Canary 守卫测试清单（三层防护）

根据 `feedback_ci_coverage_guards.md` 要求，以下 Canary 守卫测试必须存在且通过：

| 守卫层次 | 文件 | 测试函数 | 守卫的不变量 |
|---------|------|---------|------------|
| Serializer 层 | test_serializers.py | `test_n_equals_5_is_rejected_canary_guard` | max_value=4 不得被修改为更大值 |
| DB 层（下界） | test_models.py | `test_total_count_0_violates_constraint` | DB CheckConstraint 下界 ≥1 |
| DB 层（上界） | test_models.py | `test_total_count_5_violates_constraint` | DB CheckConstraint 上界 ≤4 |
| View 层 | test_views.py | `test_submit_n_exceeds_4_returns_400` | API 层 n>4 返回 400 |
| Provider 传递 | test_tasks.py | `test_task_passes_provider_doubao_to_media_library` | provider="doubao" 参数不得丢失 |

---

## 4. 测试数据准备方案

### 4.1 单元测试数据（自包含）

所有单元测试通过 pytest fixtures 和工厂方法构造测试数据：

- `user` / `user2`：由 `conftest.py` 全局 fixture 提供（SQLite in-memory DB）
- `auth_client` / `auth_client2`：带 JWT token 的 DRF APIClient
- `_make_batch(user, n)` / `_make_doubao_config(user)`：本地工厂函数，无需外部依赖

### 4.2 Mock 策略

| 外部依赖 | Mock 方式 | 适用测试 |
|---------|---------|---------|
| httpx.Client（Ark API） | `@patch("apps.image_generator.doubao_image_client.httpx.Client")` | test_doubao_client.py 所有 HTTP 测试 |
| DoubaoImageClient.generate_images | `@patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")` | test_tasks.py |
| create_media_item_from_url | `@patch("apps.image_generator.tasks.create_media_item_from_url")` | test_tasks.py |
| push_notification_sync | `@patch("apps.image_generator.tasks.push_notification_sync")` | test_tasks.py |
| tenacity.wait_fixed | `@patch("tenacity.wait_fixed.__call__", return_value=0)` | 重试相关测试 |

### 4.3 禁止事项

- 禁止在任何 mock 中使用真实 Ark API Key
- 禁止调用真实 Ark API（所有 httpx.Client 均被 patch）
- 禁止硬编码生产环境 URL 或密钥

---

## 5. 缺陷分级与门控标准

### 5.1 缺陷分级

| 级别 | 定义 | 示例 |
|-----|------|------|
| CRITICAL | 功能完全不可用、数据损坏、安全漏洞 | API Key 明文出现在日志；n>4 约束失效 |
| HIGH | 核心功能异常、会影响用户使用 | 批次生成后 status 不更新；媒体库入库失败 |
| MEDIUM | 非核心功能异常或边界用例 | 错误提示文本不准确；批次重命名空串提示 |
| LOW | 文案、UI 细节等 | 批次名中 prompt 摘要截断位置不准确 |

### 5.2 测试阶段门控标准

| 测试类型 | 通过标准 | 失败处理 |
|---------|---------|---------|
| 单元测试（本地） | **100% 通过**（0 fail） | 立即停止，退回开发阶段修复 |
| 集成测试（CI） | 100% 通过 | CI 失败阻止 PR 合并 |
| E2E 测试（CI） | Critical Path 100% | CI 失败阻止 PR 合并 |
| 覆盖率（后端） | 核心模块 ≥ 80% | 警告但不阻塞（本次迁代特殊豁免） |

---

## 6. 即梦清理验证

作为豆包替换验证的一部分，测试阶段需确认：

- `grep -r "import jimeng" apps/` → 无结果（已验证：无 `import jimeng` 残留）
- 测试文件中的 `jimeng` 引用仅出现在：
  - `test_models.py`：验证 `jimeng_task_id` 字段默认值（历史数据兼容测试）
  - `test_views.py`：注释中说明"兼容即梦历史数据"
  - `test_serializers.py`：`test_unsupported_model_jimeng_is_rejected`（验证即梦模型被正确拒绝）
- 以上引用均为**验证清理完成**的测试，而非残留依赖

---

## 7. 集成测试说明（标记 integration，CI 跑）

以下测试在本地**跳过**（无 PostgreSQL + Celery 环境），由 GitHub Actions CI 负责执行：

- 端到端流程：POST → Celery task 实际执行 → mock Ark → media_library 入库 → WebSocket 事件
- 数据库迁移：`0002_imagebatch_and_fields` 正向迁移 + 回滚验证

集成测试文件：`apps/image_generator/tests/test_integration.py`（见独立文件）

---

## 8. E2E 测试说明（Playwright）

E2E 测试覆盖用户故事 US-01 / US-02 / US-04 / US-05 的关键路径。

**已知 Playwright 陷阱（来自 feedback_e2e_playwright_patterns.md）：**

1. **h1 重复**：页面可能存在多个 h1，需使用 `.first()` 或更精确的选择器
2. **getByText 多匹配**：避免使用短文本，优先使用 `data-testid`
3. **el-input-number 延迟**：el-input-number 的 change 事件需等待 debounce，使用 `page.waitForTimeout(300)` 或监听 network idle
4. **el-upload 定位器**：使用 `locator('.el-upload__input')` 而非 `getByRole('button')`
5. **E2E 扫描盲区**：批次删除后需显式等待列表刷新
6. **KB 页面断言**：本功能无 KB 页面，不适用

E2E 测试为**可选**，本次交付中不作为门控条件（测试策略以单元测试 100% 通过为主门控）。
