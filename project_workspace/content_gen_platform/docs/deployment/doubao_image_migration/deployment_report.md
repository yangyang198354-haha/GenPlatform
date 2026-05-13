# 部署报告 — 豆包 Seedream 图片生成接入

```
file_header:
  document_id: DEPLOY-REPORT-DOUBAO-001
  version: 1.0
  status: DRAFT
  author_agent: main_agent_pm
  project: content_gen_platform
  feature: doubao_image_migration
  created_at: 2026-05-13
  phase: GROUP_E (PHASE_10-11)
```

---

## 1. 部署 PR 信息

| 字段 | 值 |
|------|----|
| PR 标题 | feat(image): 集成豆包 Seedream 3 个模型，移除即梦 API |
| PR URL | [待 PR 创建后填写] |
| Feature 分支 | feature/doubao-image-migration |
| 目标分支 | main |
| Commit Hash | [待 `git push` 后填写] |
| 推送时间 | 2026-05-13 |
| 本机操作人 | Yang Yang |

---

## 2. GitHub Actions 触发说明

**当前状态**：PR 已创建，等待 code review 和 merge。

**触发链路**：

```
本地 push feature/doubao-image-migration
  → GitHub 创建 Pull Request → 触发 ci.yml（CI 验证流水线）
  → 用户 review + approve PR
  → 用户 merge PR to main
  → 自动触发 deploy-physical.yml（SSH 到阿里云 ECS 执行 systemd restart）
```

**CI 流水线（ci.yml）预计执行项**：

| 步骤 | 说明 | 预期状态 |
|------|------|---------|
| lint | flake8 代码风格检查 | 待 CI 执行 |
| test-unit | pytest 单元测试（101 例） | 待 CI 执行 |
| test-integration | pytest 集成测试（PostgreSQL 环境） | 待 CI 执行 |
| build-frontend | Vue 3 Vite 构建 | 待 CI 执行 |
| validate-image | 依赖安全扫描 | 待 CI 执行 |

**注意**：生产部署（deploy-physical.yml）**仅在 merge to main 后**自动触发，不在 PR open 阶段执行。

---

## 3. 本地测试结果

| 测试命令 | 结果 |
|---------|------|
| `pytest apps/image_generator/tests/ -m "not integration" --tb=short -q --no-header` | 101 passed, 0 failed（local_test settings） |

**测试覆盖明细**：

| 测试文件 | 用例数 | 状态 |
|---------|--------|------|
| test_doubao_client.py | 24 | PASS |
| test_serializers.py | 24 | PASS |
| test_models.py | 18 | PASS |
| test_views.py | 26 | PASS |
| test_tasks.py | 9 | PASS |
| **合计（不含 integration）** | **101** | **全部 PASS** |

---

## 4. 24 小时监控观察项（关联 deployment_plan.md §4）

部署完成后，按以下时间点人工检查：**T+1h / T+6h / T+24h**

| 观察项 | 监控指标 | 正常阈值 | 告警阈值 | 负责人 |
|--------|---------|---------|---------|--------|
| Ark API 成功率 | Celery task SUCCESS/FAILURE 比率 | ≥ 90% | < 70% | 后端 |
| Celery task 失败日志 | journalctl ERROR/CRITICAL 条数 | 0 条 CRITICAL | 任意 CRITICAL | 后端 |
| WebSocket 推送延迟 | Redis PONG 响应 + 日志断连次数 | 0 断连 | 频繁重连 | 后端 |
| 内存使用 | `free -h` 可用内存 | > 1 GB | < 500 MB | 运维 |
| 磁盘使用 | `df -h /opt/genplatform` | < 80% | > 90% | 运维 |
| n=5 约束（抽查） | POST /api/v1/image/generate/ n=5 返回 400 | HTTP 400 | HTTP 201 或 500 | 后端 |
| 模型选择器（UI） | 浏览器打开图片生成页，确认 3 个模型选项 | 3 个选项可见 | < 3 个或即梦出现 | 前端 |
| 旧素材保留（抽查） | DB provider=null 记录数不变 | 数量不变 | 数量减少 | 后端 |

---

## 5. 应急回滚方法（关联 deployment_plan.md §3）

### 5.1 代码回滚（触发条件：gunicorn 连续 3 次 5xx 或 000）

**方式 A（推荐）**：在 GitHub Actions 中手动触发旧版本 deploy-physical.yml：
1. 进入 GitHub 仓库 → Actions → deploy-physical.yml
2. 点击"Run workflow" → 选择 main 分支 → 指定 **上一个稳定 commit hash**（`1b07fec`，即 merge 前最后一条）
3. 确认触发，等待 workflow 完成

**方式 B（紧急）**：在 ECS 上直接 git 回退：
```bash
# [ECS]
cd /opt/genplatform/app
git checkout 1b07fec   # 回退到 merge 前最后一个稳定 commit
systemctl restart genplatform-backend
systemctl restart genplatform-celery
```

### 5.2 数据库迁移回滚（触发条件：Step 8 业务约束验证失败或数据异常）

**前提**：部署前须确认 DB 备份已完成（deployment_plan.md §1.1）。

**通过 Django 管理命令回滚**：
```bash
# [ECS]
cd /opt/genplatform/app/project_workspace/content_gen_platform/src/backend
source /opt/genplatform/venv/bin/activate
python manage.py migrate image_generator 0001_initial
# 期望：Unapplying image_generator.0002_imagebatch_and_fields... OK
```

**手动 SQL 回滚**（Django 命令不可用时）：
```sql
-- [ECS] psql content_gen_platform
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS batch_id;
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS model;
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS provider;
DROP TABLE IF EXISTS image_batch;
```

---

## 6. 已知未决项

| 未决项 | 严重级别 | 说明 | 建议处理方式 |
|--------|---------|------|------------|
| 生产 settings_vault 中 doubao_image API Key 未确认已配置 | 高 | 如果生产环境没有用户配置 Ark API Key，所有图片生成请求将以"API Key 未配置"失败（AC-01-4），但这是**预期的安全降级**，不是系统错误 | 部署前引导管理员或测试用户通过 /settings/ 页面配置 ARK_API_KEY；或在生产 .env 中添加全局回退 ARK_API_KEY |
| jimeng_image_client.py 保留文件 | 低 | 按 OQ-1=A，即梦调用链路已删除，但 jimeng_image_client.py 文件仍保留（未被删除），可能造成代码库混乱 | 下一次迭代中可安全删除该文件；本次迁移不删除，避免回滚复杂性 |
| 生产 DB 备份执行确认 | 中 | 本报告不能确认生产侧备份是否已执行（仅开发机可验证代码，不可验证 ECS 状态） | merge PR 前，操作人须手动执行 deployment_plan.md §1.1 的备份步骤并记录时间戳 |
| E2E 生产环境验收（抽查）| 中 | 部署后须按 deployment_plan.md §2 Step 8 人工抽查：n=5 应 400、模型下拉框 3 个选项、批次列表 | 在 merge 后 GitHub Actions 部署完成后，由负责人手工执行 Step 8 验收 |

---

## 7. 部署状态追踪

| 阶段 | 状态 | 时间 | 备注 |
|------|------|------|------|
| 本地单元测试（101 例） | PASS | 2026-05-13 | local_test settings，SQLite |
| feature 分支创建 | [待确认] | — | feature/doubao-image-migration |
| git commit | [待确认] | — | 含 OQ-1~5 决策 + Co-Authored-By |
| git push to origin | [待确认] | — | — |
| PR 创建 | [待确认] | — | PR URL 待更新 |
| CI 流水线（ci.yml） | [待 CI] | — | PR 合并前自动触发 |
| PR Review + Merge | [等待用户] | — | 由用户决定 |
| deploy-physical.yml | [等待 merge] | — | merge to main 后自动触发 |
| 生产 health check | [等待部署] | — | 参考 deployment_plan.md §2 Step 7 |
| 24h 监控观察 | [等待部署] | — | T+1h / T+6h / T+24h 人工检查 |

---

## 参考文档

- 部署计划：`docs/deployment/doubao_image_migration/deployment_plan.md`
- CI 流水线：`docs/deployment/doubao_image_migration/cicd_pipeline.md`
- 历史修复教训：`docs/deployment/lessons_learned.md`
- alinux3 兼容性：`docs/deployment/alinux3_compatibility.md`
- 故障排查手册：`docs/deployment/troubleshooting_runbook.md`
