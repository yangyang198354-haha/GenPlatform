# 集成测试报告：豆包 Seedream 图片生成接入

```
file_header:
  document_id: TEST-INTEGRATION-REPORT-DOUBAO-001
  version: 1.0
  status: DRAFT
  author_agent: sub_agent_test_engineer
  project: content_gen_platform
  feature: doubao_image_migration
  created_at: 2026-05-13
```

---

## 执行说明

### 本地跳过原因

集成测试全部标记为 `@pytest.mark.integration`，在本地执行以下命令时自动跳过：

```bash
pytest apps/ tests/ -m "not integration" --tb=short -q
```

**本地环境缺失：**
- PostgreSQL 数据库（集成测试需要真实 PG 连接验证 CheckConstraint）
- Celery worker（验证真实任务队列行为）

### CI 执行环境

GitHub Actions workflow 中，集成测试由独立 job 执行：
```bash
pytest apps/ tests/ -m "integration" --tb=short -q
```

CI 环境配置：
- PostgreSQL 15（service container）
- `DJANGO_SETTINGS_MODULE=config.settings.test`
- Celery `TASK_ALWAYS_EAGER=True`（任务在进程内同步执行）

---

## 集成测试清单

### test_integration.py（5 例，`@pytest.mark.integration`）

| 测试类 | 测试函数 | 测试内容 | 本地状态 | CI 状态 |
|-------|---------|---------|---------|---------|
| TestImageGenerationEndToEnd | test_full_pipeline_single_image | POST → Celery → mock Ark → 入库 → completed | SKIP（本地） | 待 CI 执行 |
| TestImageGenerationEndToEnd | test_full_pipeline_batch_4_images | 4 张批次完整流水线 | SKIP（本地） | 待 CI 执行 |
| TestMigrationIntegrity | test_imagebatch_table_exists_with_all_fields | ImageBatch 表字段验证 | SKIP（本地） | 待 CI 执行 |
| TestMigrationIntegrity | test_imagegenerationrequest_new_fields | 新字段读写验证 | SKIP（本地） | 待 CI 执行 |
| TestMigrationIntegrity | test_check_constraint_in_postgres | CheckConstraint 在 PG 层验证 | SKIP（本地） | 待 CI 执行 |

---

## 数据库迁移说明

### 迁移文件：0002_imagebatch_and_fields.py

**正向迁移（migrate）：**
- 新建 `image_batch` 表，含 CheckConstraint `image_batch_total_count_1_to_4`
- 在 `image_generation_request` 表新增 `batch_id`（FK，ON DELETE SET NULL）、`model`、`provider` 字段

**回滚迁移（migrate 0001）：**
- 删除 `image_batch` 表
- 从 `image_generation_request` 中移除三个新字段

**验证命令（CI 中执行）：**
```bash
python manage.py migrate --settings=config.settings.test
python manage.py migrate image_generator 0001 --settings=config.settings.test  # 回滚
python manage.py migrate image_generator 0002 --settings=config.settings.test  # 重新迁移
```

---

## 提示：CI 失败处理

若 CI 中集成测试失败：
1. 查看 GitHub Actions 的 `pytest` 日志，定位失败测试
2. 根据失败类型判断：
   - DB schema 不一致 → 检查 migration 文件
   - mock 配置错误 → 更新 mock 目标路径
   - Celery eager 模式问题 → 检查 `CELERY_TASK_ALWAYS_EAGER` 配置
3. 修复后重新推送触发 CI
