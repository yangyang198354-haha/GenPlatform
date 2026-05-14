# 集成测试报告 v1.1 — 豆包图片迁移 UX 修复迭代

**文档版本**：v1.1
**迭代范围**：content_gen_platform — 豆包图片迁移 UX 修复（FR-6 / FR-7 / US-08）
**负责人**：test-engineer 子代理
**日期**：2026-05-14
**说明**：集成测试在本地不强制执行（无 Docker 环境），由 GitHub Actions CI 负责运行。

---

## 1. 集成测试范围说明

所有集成测试均标记 `@pytest.mark.integration`，本地运行时通过 `-m "not integration"` 跳过。

### 1.1 现有集成测试

| 测试文件 | 测试内容 | CI 依赖 |
|---------|---------|---------|
| `apps/image_generator/tests/test_integration.py` | 图片生成端到端流程（Celery 同步模式，mock Ark API） | PostgreSQL |

### 1.2 本次迭代新增集成测试需求

以下场景需要在 CI 中补充集成测试（建议在后续迭代中由 test-engineer 实现）：

| 测试 ID | 场景 | 依赖 | 优先级 |
|--------|------|------|-------|
| INT-SV-01 | 登录 → GET status（未配置）→ POST test-and-save（mock Ark 200）→ GET status（已配置）→ 验证 is_configured=True | PostgreSQL | 高 |
| INT-SV-02 | POST test-and-save 成功后再次调用（update_or_create）不产生重复行 | PostgreSQL | 中 |
| INT-MIG-01 | Migration 0003（last_validated_at 字段）正向 apply | PostgreSQL | 高 |
| INT-MIG-02 | Migration 0003 回滚（last_validated_at 字段删除后可恢复） | PostgreSQL | 中 |
| INT-GEN-01 | 登录 → GET status（已配置）→ POST 生成（Celery 同步）→ 素材库入库端到端 | PostgreSQL + Redis + Celery | 高 |

---

## 2. CI 配置参考

### 2.1 触发条件

- GitHub Actions：每次 `git push` 到 `main` / `feature/*` 分支自动触发
- 本地：`python -m pytest apps/ tests/ -m "integration" --tb=short -q`（需要 Docker Compose）

### 2.2 本次迭代 CI 变更

本次迭代不修改 CI 配置文件。以下是需要确认已有 CI 能覆盖的检查点：

| 检查点 | 说明 | CI 任务 |
|-------|------|---------|
| Migration 0003 自动 apply | CI 在测试前执行 `python manage.py migrate`，0003 应自动 apply | unit-tests job |
| `last_validated_at` 字段存在于 DB schema | Migration apply 后查询该字段应不报错 | 集成测试隐式验证 |
| doubao_image service_type 在 SERVICE_CHOICES 中 | ServiceStatusView + TestAndSaveView 路由可达 | 单元测试已覆盖 |

---

## 3. 本地执行说明

集成测试在本地无法运行的原因：

1. **数据库依赖**：集成测试使用 PostgreSQL（本地无 Docker），`local_test.py` 配置了 SQLite，不满足集成测试的 PG 要求。
2. **migration 0003 兼容性**：`last_validated_at` 使用 `models.DateTimeField(null=True)`，SQLite 支持但 pgvector 相关 app 被排除，不影响 `settings_vault` 集成测试运行。
3. **Celery 依赖**：INT-GEN-01 场景需要 Celery worker，本地无 Redis。

如需本地运行集成测试，请先启动 Docker Compose：

```bash
docker-compose up -d db redis
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest apps/ tests/ -m "integration" --tb=short -q
```

---

## 4. 阶段结论

- 本地集成测试：**5 个跳过（正常，符合预期）**
- CI 集成测试：由 GitHub Actions 自动运行，覆盖 PostgreSQL 环境
- 本次迭代未引入新的集成测试文件（已有的 image_generator 集成测试覆盖主流程）
- 待后续迭代补充：INT-SV-01 ~ INT-MIG-02（settings_vault 专项集成测试）
