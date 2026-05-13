# CI/CD 流水线定义 — 豆包 Seedream 图片生成接入

**文档版本**：v1.0 DRAFT
**所属迁移**：doubao_image_migration
**编写日期**：2026-05-13
**状态**：DRAFT（待 PM 门控评审）

---

## 目录

1. [现有 workflow 影响分析](#1-现有-workflow-影响分析)
2. [测试矩阵](#2-测试矩阵)
3. [构建与发布](#3-构建与发布)
4. [质量门禁](#4-质量门禁)
5. [CI workflow 变更清单](#5-ci-workflow-变更清单)

---

## 1. 现有 workflow 影响分析

### 1.1 当前 workflow 清单

项目 `.github/workflows/` 下共有三个 workflow：

| 文件 | 触发方式 | 用途 |
|------|---------|------|
| `ci.yml` | push/PR 自动触发 | 完整 CI 流水线（lint → unit → integration → 前端构建 → Docker 镜像 → 镜像验证 → 生产部署 → 冒烟测试 → E2E） |
| `deploy-physical.yml` | 手动触发（workflow_dispatch） | 物理机热更新部署（scp 上传源码 + 远程 SSH 执行） |
| `diagnose-prod.yml` | 手动触发 | 生产环境诊断（不部署，仅采集状态信息） |

### 1.2 本次改动对 ci.yml 的影响

#### Stage 2（Unit Tests，`test-unit` job）

**变化**：本次新增了以下测试文件，`test-unit` job 扫描 `apps/` 目录，这些文件将自动被纳入执行范围，无需修改 workflow：

- `apps/image_generator/tests/test_doubao_client.py` — DoubaoImageClient 单元测试（mock HTTP 调用，不需要 PG/Redis）
- `apps/image_generator/tests/test_models.py` — ImageBatch / ImageGenerationRequest 模型字段测试
- `apps/image_generator/tests/test_serializers.py` — 序列化器验证（含 watermark 默认值修复回归测试）
- `apps/image_generator/tests/test_tasks.py` — Celery task 单元测试（mock Doubao API）
- `apps/image_generator/tests/test_views.py` — 视图层单元测试

**需要确认的 `--cov-fail-under` 阈值**：当前 `test-unit` job 设置为 `65`。本次新增 image_generator 测试覆盖率预计提升，建议在首次 CI 通过后根据实际报告评估是否上调阈值（不强制）。

**无需修改的内容**：`test-unit` job 已使用 `pytest apps/ -m "not integration and not e2e"`，新文件自动包含。

#### Stage 3（Integration Tests，`test-integration` job）

**变化**：`apps/image_generator/tests/test_integration.py` 中的集成测试标注了 `@pytest.mark.integration`，需要 PostgreSQL service container。该 job 已扫描 `tests/ apps/`，自动包含，无需修改。

**本次集成测试新增场景**：
- 端到端 Doubao API 调用（使用 mock，避免真实计费）
- `ImageBatch` + `ImageGenerationRequest` 数据库写入与读取
- `settings_vault` 中 `doubao_image` service_type 的加密存储与读取

#### Stage 4（Frontend Build，`build-frontend` job）

**变化**：前端改动（模型选择器 UI、批次进度展示）已包含在源码中，`npm run build` 会自动处理，无需修改 workflow。

#### Stage 6（Validate Production Image，`validate-image` job）

**变化**：`validate-image` job 执行 `python manage.py migrate` 验证迁移可用性。本次新增两条迁移：
- `image_generator/0002_imagebatch_and_fields`
- `settings_vault/0002_add_doubao_image_service`

这两条迁移将在 `validate-image` 阶段的"Verify all migrations apply cleanly"步骤中自动验证，**无需修改 workflow**。若迁移有语法错误或依赖缺失，此 job 将提前拦截，阻止部署流程继续。

#### Stage 7（Deploy，`deploy-production` job）

**变化**：本次部署步骤中需要在生产环境运行新迁移。`ci.yml` 的 `deploy-production` job 使用 Docker Compose，容器启动时在 entrypoint 中执行 `python manage.py migrate`，自动包含新迁移，**无需修改 workflow**。

### 1.3 本次改动对 deploy-physical.yml 的影响

本次迭代的生产环境使用**物理机部署**（systemd 管理），通过 `deploy-physical.yml` 手动触发。

**影响点**：
- `pip install -r requirements.txt` 步骤将自动安装新增依赖 `tenacity==8.5.0`（已写入 requirements.txt）
- 数据库迁移步骤需要显式执行（见 deployment_plan.md 第 3 节）
- 不需要修改 deploy-physical.yml 的 workflow 定义本身，变更体现在部署脚本执行的命令中

---

## 2. 测试矩阵

### 2.1 Unit job（无外部依赖）

| 属性 | 值 |
|------|---|
| 运行环境 | ubuntu-latest，GitHub Actions runner |
| Python 版本 | 3.11 |
| Django settings | `config.settings.test`（LocMemCache，无 Redis，CELERY_TASK_ALWAYS_EAGER=True） |
| 数据库 | PostgreSQL service container（test_db，复用现有配置） |
| 命令 | `pytest apps/ --cov=apps --cov-fail-under=65 -m "not integration and not e2e" -x -q` |
| 覆盖率报告 | XML 上传至 Codecov（flags: unit） |
| 本次新增测试文件 | test_doubao_client.py、test_models.py（新字段）、test_serializers.py、test_tasks.py、test_views.py |
| 预计新增 test case 数 | 约 101 个（本地已全部通过） |

**注意**：`test_doubao_client.py` 中所有 HTTP 调用均已通过 `unittest.mock.patch` mock，不会触发真实 Ark API，CI 中无需注入 `ARK_API_KEY`。

### 2.2 Integration job（需要 PG + Redis service container）

| 属性 | 值 |
|------|---|
| 运行环境 | ubuntu-latest |
| Python 版本 | 3.11 |
| Django settings | `config.settings.test` |
| 数据库 | PostgreSQL（pgvector/pgvector:pg15）+ Redis（redis:7-alpine）service container |
| 命令 | `pytest tests/ apps/ --cov=apps --cov-report=xml -m integration -v` |
| 本次新增集成测试 | `apps/image_generator/tests/test_integration.py`（标注 `@pytest.mark.integration`） |
| 通过率要求 | ≥ 90%（本次新增场景均为 mock Ark API，应达 100%） |
| 迁移步骤 | `python manage.py migrate --run-syncdb`（自动含新迁移 0002） |

**注意**：集成测试中若需要验证 Doubao API 响应格式，使用 `responses` 库或 `unittest.mock` mock `httpx.AsyncClient`，绝对不允许在 CI 中硬编码或注入真实 `ARK_API_KEY`。

### 2.3 Frontend job（lint + build）

| 属性 | 值 |
|------|---|
| 运行环境 | ubuntu-latest |
| Node 版本 | 20 |
| 工作目录 | `project_workspace/content_gen_platform/src/frontend` |
| 命令序列 | `npm install` → `npm run build` |
| 构建产物 | `dist/`，上传为 artifact（retention-days: 3） |
| lint | 通过 `npm run build` 时 Vite 内置检查；如有独立 eslint 步骤，本次前端改动（模型选择器）需通过 eslint 检查 |
| 本次改动 | 新增模型选择器组件、批次数量输入框、进度展示组件；构建产物路径不变 |

---

## 3. 构建与发布

### 3.1 依赖变更与 pip cache

本次在 `requirements.txt` 中新增：

```
# 重试工具（DoubaoImageClient 网络错误重试，ADR-07）
tenacity==8.5.0
```

**pip cache key 影响**：

`ci.yml` 的 `test-unit` 和 `test-integration` job 使用 `actions/setup-python@v5` 的 `cache: pip`，cache key 依赖路径为 `requirements-ci.txt`。

**需要确认**：`requirements-ci.txt` 是否包含 `tenacity==8.5.0`。若 `requirements-ci.txt` 是 `requirements.txt` 的子集或软链，添加 tenacity 后 cache key（基于文件 hash）会自动 bust，CI 首次运行时将重新安装依赖，后续恢复正常缓存。

**建议操作**：在本次 PR 中同步更新 `requirements-ci.txt`（若独立维护），确保 `tenacity==8.5.0` 包含其中。

### 3.2 Docker 镜像构建

本次后端镜像构建（`docker-build` job）通过 `docker/build-push-action` 执行，`context` 为 `project_workspace/content_gen_platform/src/backend`，`pip install -r requirements.txt` 在 Dockerfile 中执行，自动包含 tenacity。镜像 cache 策略（`cache-from/cache-to: registry`）会因 requirements.txt 变更而对 pip layer 重新构建，其余 layer（OS、系统依赖）保持缓存，构建时间增量有限。

### 3.3 前端构建产物路径

前端构建产物输出至 `dist/`，通过 `actions/upload-artifact@v4` 上传，artifact 名称为 `frontend-dist`。本次改动不涉及构建输出路径变更。

物理机部署中，前端 dist 通过 `scp` 上传至 ECS，由 nginx 静态服务，路径不变。

---

## 4. 质量门禁

以下门禁条件**全部满足**后，才允许触发物理机生产部署（deployment_plan.md）：

### 门禁 1 — 单元测试通过率 100%

- 判定依据：`pytest -m "not integration and not e2e"` 零失败
- CI job：`test-unit`
- 本地预验证：`pytest apps/ tests/ -m "not integration" --tb=short -q`（已通过 101/101）
- 阻断条件：任意 1 个 test 失败，禁止继续

### 门禁 2 — 集成测试通过率 ≥ 90%

- 判定依据：`pytest -m integration` 失败数 / 总数 ≤ 10%
- CI job：`test-integration`
- 阻断条件：通过率 < 90%，禁止继续

### 门禁 3 — 硬编码 API Key 检查（阻断）

禁止任何 Python 源文件中出现真实 Ark API Key 模式。CI 中增加以下安全扫描步骤（建议加入 `lint` job）：

```yaml
- name: 检查硬编码 API Key（安全门禁）
  run: |
    # 检查 Ark/Volcengine API Key 前缀模式
    if grep -r --include="*.py" -n "sk-[A-Za-z0-9]\{20,\}" apps/ tests/ config/; then
      echo "FATAL: 检测到疑似硬编码 API Key，部署被阻断"
      exit 1
    fi
    # 检查 Bearer Token 直接赋值模式
    if grep -r --include="*.py" -n '"Authorization".*Bearer sk-' apps/ tests/ config/; then
      echo "FATAL: 检测到 Bearer Token 硬编码，部署被阻断"
      exit 1
    fi
    echo "API Key 安全检查通过"
```

**背景**：本次接入 Doubao/Ark API，API Key 统一通过 `settings_vault` AES-256-GCM 加密存储（用户级配置），或通过 `.env` 的 `ARK_API_KEY` 环境变量注入（全局回退）。任何情况下都不允许 Key 出现在源代码中。

### 门禁 4 — 前端构建成功

- 判定依据：`npm run build` 退出码 0，`dist/` 目录非空
- CI job：`build-frontend`
- 阻断条件：构建失败，禁止继续

### 门禁 5 — 镜像迁移验证（Docker 部署路径）

- 判定依据：`validate-image` job 中 `python manage.py migrate` 应用两条新迁移成功，无报错
- 特别验证：`image_generator/0002_imagebatch_and_fields` 含 DB CHECK 约束（`n ≤ 4`），迁移中会在 PostgreSQL 侧创建约束，需确认无 FK/CHECK 冲突
- 阻断条件：迁移失败，禁止继续

### 门禁 6 — 依赖安全扫描（参考项）

`lint` job 中 `safety scan -r requirements.txt` 设置了 `continue-on-error: true`（不阻断流水线）。建议在发布前人工确认 tenacity==8.5.0 无高危 CVE（当前版本无已知漏洞）。

---

## 5. CI workflow 变更清单

以下是本次迭代需要对 CI 配置文件做的**具体变更**，以 diff 形式描述：

### 5.1 ci.yml — 新增硬编码 API Key 安全扫描（必须）

在 `lint` job 中，在现有 `bandit` 扫描步骤之后，新增：

```yaml
      - name: 检查硬编码 Ark API Key
        run: |
          if grep -r --include="*.py" -n "sk-[A-Za-z0-9]\{20,\}" apps/ tests/ config/ 2>/dev/null; then
            echo "FATAL: 检测到疑似硬编码 API Key"
            exit 1
          fi
          echo "API Key 安全检查通过"
```

**注意**：此步骤不加 `continue-on-error: true`，属于硬阻断门禁。

### 5.2 requirements-ci.txt — 新增 tenacity（必须确认）

若 `requirements-ci.txt` 独立维护，需同步添加：

```
tenacity==8.5.0
```

### 5.3 其余 workflow（deploy-physical.yml、diagnose-prod.yml）— 无需修改

物理机部署通过 `deploy-physical.yml` 手动触发，具体执行命令在 deployment_plan.md 中描述，workflow 文件定义本身无需变更。

---

## 参考文档

- `docs/deployment/lessons_learned.md` — 6 类元根因，特别是"元根因 A：静默失败"（CI 检查中避免 `continue-on-error` 掩盖真实错误）
- `docs/deployment/troubleshooting_runbook.md` — F07（DB 密码认证失败）、F09（Celery 启动超时）章节，对应 CI 中的集成测试注意事项
- `docs/architecture/doubao_image_migration/module_design.md` — DoubaoImageClient 架构设计，包含 tenacity 重试策略说明
- `docs/requirements/doubao_image_migration/` — FR-1..FR-7，AC 定义（测试覆盖来源）
