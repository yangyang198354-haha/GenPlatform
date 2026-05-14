# CI/CD 流水线文档 — 增量补丁 v1.1
# 豆包图片迁移 UX 修复迭代

**文档编号**：CICD-DPL-IMG-001-PATCH
**基准版本**：v1.0（已随 PR #4 / commit c0506c0 上线生产）
**本补丁版本**：v1.1
**创建日期**：2026-05-14
**状态**：DRAFT — 等待 PM 门控评审
**作者**：devops-engineer 子代理（由 PM 编排）
**阅读方式**：本文档为**增量补丁**，与 v1.0 联合使用。凡未提及之处，v1.0 规则继续有效。

---

## 一、与 v1.0 的差异概览

| 维度 | v1.0（已上线） | v1.1（本次迭代） | 变更类型 |
|------|-------------|----------------|---------|
| Python 依赖 | tenacity、httpx 等 | **无新增** | 不变 |
| Workflow 文件 | ci.yml、deploy-physical.yml | **无修改** | 不变 |
| 新增测试文件 | — | test_ark_validator.py / test_service_status_view.py / test_test_and_save_view.py（新增3个测试方法） | 自动纳入 CI |
| DB Migration | 无 | 0003_userserviceconfig_last_validated_at.py（新增可空字段） | 需显式迁移 |
| 集成测试 | image_generator 1个 | **新增 5 例 @integration 需求**（待补充，见 §3） | 待补充 |
| 安全门禁 | 硬编码 sk- 检测 | **复用，不变** | 不变 |

**本次迭代 CI/CD 工作量极小**：无新 workflow、无新依赖，主要影响是单元测试文件自动被扫描、migration 0003 自动在 CI 中被 apply。

---

## 二、现有 Workflow 结构复用说明

### 2.1 ci.yml — 单元测试与安全门禁

v1.0 已配置的 `unit-tests` job 扫描路径：

```
pytest apps/ tests/ -m "not integration" --tb=short -q
```

本次迭代新增的以下测试文件将**自动被扫描**，无需任何 ci.yml 修改：

| 新增测试文件（相对于 backend/） | 新增测试数量 |
|-------------------------------|-----------|
| `apps/settings_vault/tests/test_ark_validator.py` | 10 个单元测试 |
| `apps/settings_vault/tests/test_service_status_view.py` | 7 个单元测试（含 TODO-03 Canary 守卫） |
| `apps/settings_vault/tests/test_test_and_save_view.py` | 新增 3 个原子性测试方法（TestTestAndSaveViewAtomicity） |

**预期 CI unit-tests 结果**：141 passed, 5 deselected (integration), 0 failed

---

### 2.2 ci.yml — deploy-production job

> **重要警告：ci.yml deploy-production job 冲突风险**

#### 背景

v1.0 部署时已踩过此坑：`ci.yml` 中存在一个 `deploy-production` job，在每次 merge 到 main 后自动触发，会尝试执行 `docker compose pull + up`，与物理机的 systemd 服务部署方式存在冲突。

上次（PR #4 merge 后）通过 `gh run cancel` 在 `docker compose pull` 阶段中止，才避免了 Docker 覆盖 physical 部署的问题。

#### 本次迭代操作规程（必须执行）

```
本次 PR merge 到 main 后，必须立即执行以下命令阻止 deploy-production job：

  gh run list --workflow=ci.yml --limit=3
  # 找到刚触发的 run ID，确认 status=in_progress

  gh run cancel <ci-run-id>
  # 在 docker compose pull 阶段完成之前取消

验证取消成功：
  gh run view <ci-run-id>
  # status 应显示 cancelled
```

#### 长期修复建议（本期不在范围内）

建议在下一个 PR 中对 `ci.yml` 的 deploy-production job 添加条件门控，例如：

```yaml
# 建议改造方向（仅参考，本期不实施）：
deploy-production:
  if: github.event_name == 'workflow_dispatch'  # 仅允许手动触发
```

或完全删除 ci.yml 中的 deploy-production job，改为通过 deploy-physical.yml 唯一入口管理生产部署。

---

### 2.3 deploy-physical.yml — 热更新触发

v1.0 已建立的触发方式，本次迭代完全复用：

```
deploy-physical.yml 仅支持 workflow_dispatch（手动触发），merge main 不会自动部署。

热更新命令：
  gh workflow run deploy-physical.yml --ref main -f run_setup=false

完整安装（仅首次或系统包变更时需要）：
  gh workflow run deploy-physical.yml --ref main -f run_setup=true
```

**本次迭代使用热更新模式（run_setup=false）**，因为：
- 无新 Python 系统级依赖
- 不需要重新安装系统包
- 仅需更新代码 + 跑 migration + 重建前端 + 重启服务

---

## 三、测试矩阵更新（v1.1 增量）

### 3.1 单元测试矩阵（全量，含新增）

| 测试文件 | 测试类 | 测试方法数 | 标记 | CI job |
|---------|-------|----------|------|-------|
| test_ark_validator.py | TestValidateDoubaoKey | 10 | 无 | unit-tests |
| test_service_status_view.py | TestServiceStatusView | 7 | 无（含 Canary 守卫） | unit-tests |
| test_test_and_save_view.py | TestTestAndSaveView | 原有 N 个 | 无 | unit-tests |
| test_test_and_save_view.py | **TestTestAndSaveViewAtomicity（新增）** | **3** | django_db(transaction=True) | unit-tests |
| test_views.py | 原有视图测试 | 7 | 无 | unit-tests |
| apps/image_generator/tests/ | 原有（不修改） | 原有 | 部分 integration | unit-tests / integration-tests |

**v1.1 单元测试汇总**：141 passed, 5 deselected, 0 failed

### 3.2 集成测试矩阵（新增需求，待补充）

以下 5 例 `@integration` 测试尚未实现（记录于 integration_test_report_v1.1.md），建议在后续迭代中由 test-engineer 补充：

| 测试 ID | 场景描述 | 优先级 | 依赖 |
|--------|---------|-------|------|
| INT-SV-01 | 登录 → GET status（未配置）→ POST test-and-save（mock Ark 200）→ GET status（已配置） | 高 | PostgreSQL |
| INT-SV-02 | test-and-save 成功后重复调用（update_or_create 幂等性） | 中 | PostgreSQL |
| INT-MIG-01 | Migration 0003（last_validated_at）正向 apply | 高 | PostgreSQL |
| INT-MIG-02 | Migration 0003 回滚（migrate settings_vault 0002） | 中 | PostgreSQL |
| INT-GEN-01 | 登录 → GET status（已配置）→ POST 生成 → 素材库入库 | 高 | PostgreSQL + Redis + Celery |

**当前 CI 集成测试**：沿用 v1.0 的 image_generator 1 例，本期新增 5 例需求待下期补充。

---

## 四、安全门禁（复用 v1.0，不变）

| 门禁项 | 实现方式 | v1.1 变更 |
|-------|---------|---------|
| 硬编码 api_key 检测（sk- 前缀） | CI 静态扫描 | 不变 |
| api_key 不出现在 response body | test_test_and_save_view.py Canary 守卫 | 覆盖新增视图 |
| api_key 不出现在日志 | test_ark_validator.py Canary 守卫 | 覆盖 ark_validator |
| TODO-03 白名单守卫（未知 service_type → 400） | test_service_status_view.py Canary 守卫 | 新增守卫 |
| 用户数据隔离 | test_service_status_view.py + test_test_and_save_view.py | 覆盖两个新视图 |

---

## 五、Migration 门禁（v1.1 新增）

本次迭代引入 Migration 0003，CI 需确保：

1. **CI unit-tests job**：`python manage.py migrate` 在测试前自动执行，0003 自动 apply（使用 SQLite，兼容 nullable 字段）
2. **CI integration-tests job**：使用 PostgreSQL，`last_validated_at DateTimeField(null=True)` 在 PG 中正常 apply
3. **生产部署前**：必须显式执行 `python manage.py migrate settings_vault 0003`（见 deployment_plan_v1.1.md §四）

---

## 六、本期 CI/CD 变更总结

```
本次迭代（v1.1）对 CI/CD 系统影响最小化：

  无变更项：
    - ci.yml（不修改）
    - deploy-physical.yml（不修改）
    - requirements.txt（无新依赖）
    - Dockerfile（不涉及）

  自动生效项：
    - 3 个新增单元测试文件 → 自动被 pytest 扫描
    - Migration 0003 → CI 测试前自动 apply

  需要手动操作项：
    - PR merge 后立即 gh run cancel <ci-run-id>（阻止 deploy-production docker job）
    - 生产部署显式使用 deploy-physical.yml + run_setup=false
    - 生产环境显式执行 migrate settings_vault 0003
```

---

*文档版本 v1.1，状态 DRAFT，等待 PM 门控评审。*
*门控通过后，状态升级为 APPROVED，作为 deployment_plan_v1.1.md 的上游输入。*
