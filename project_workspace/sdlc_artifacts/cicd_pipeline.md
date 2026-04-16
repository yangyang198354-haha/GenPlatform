# CI/CD 流水线定义 — GenPlatform KB Extension
<!--
  file: cicd_pipeline.md
  author_agent: main_agent_pm
  project: genplatform_kb_extension
  phase: GROUP_E / PHASE_10
  created_at: 2026-04-16T11:00:00Z
  status: APPROVED
-->

---

## 1. 概述

本文档描述 GenPlatform 内容生成平台 KB 功能扩展的 CI/CD 流水线设计。
流水线实现载体：**GitHub Actions**（`.github/workflows/ci.yml`）。

### 1.1 流水线触发条件

| 触发事件 | 分支 | 执行阶段 |
|---------|------|---------|
| `push` | `main`, `develop` | Stage 1-9 全量 |
| `pull_request` | `main` | Stage 1-4（代码验证，不部署） |

---

## 2. 流水线阶段图

```
[Stage 1: Lint & Security]
         │
         ├──────────────────────────────────┐
         ▼                                  ▼
[Stage 2: Unit Tests]             [Stage 4: Frontend Build]
         │                                  │
         ▼                                  │
[Stage 3: Integration Tests]               │
         │                                  │
         └──────────────────────────────────┘
                        │
                        ▼ (main branch + push only)
             [Stage 5: Docker Build & Push]
                        │
                        ▼
             [Stage 6: Validate Image]
                        │
                        ▼ (需要用户 PRODUCTION_DEPLOY_CONFIRM)
             [Stage 7: Deploy to Production]
                        │
                        ▼
             [Stage 8: Smoke Tests]
                        │
                        ▼
             [Stage 9: E2E Tests (Playwright)]
```

---

## 3. 各阶段详细定义

### Stage 1: Lint & Security Scan

**目的**：静态代码质量检查和安全扫描，在任何测试之前快速发现明显问题。

| 工具 | 作用 | 失败策略 |
|-----|------|---------|
| `ruff` | Python 代码风格检查（PEP8 + import sort） | `continue-on-error: true`（警告性，不阻塞） |
| `bandit` | Python 安全漏洞扫描（SQL 注入、hardcoded secrets 等） | `continue-on-error: true` |
| `safety` | 依赖 CVE 扫描（基于 `requirements.txt`） | `continue-on-error: true` |

**工作目录**：`project_workspace/content_gen_platform/src/backend`

**安装命令**：
```bash
pip install ruff==0.4.9 bandit==1.7.9 safety==3.2.3
```

**执行命令**：
```bash
ruff check apps/ config/ core/
bandit -r apps/ -ll --exit-zero
safety scan -r requirements.txt
```

---

### Stage 2: Unit Tests（后端单元测试）

**目的**：验证所有模块独立逻辑正确性，覆盖率门控 ≥ 80%。

**依赖**：Stage 1 完成（`needs: lint`）

**服务依赖**：
- PostgreSQL + pgvector（`pgvector/pgvector:pg15`）— Django ORM + vector 列

**关键环境变量**：
```
DJANGO_SETTINGS_MODULE=config.settings.development
POSTGRES_DB=test_db / POSTGRES_USER=postgres / POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost / POSTGRES_PORT=5432
ENCRYPTION_KEY=<base64 test key>
DJANGO_SECRET_KEY=ci-test-secret-key-not-for-production
```

**执行命令**：
```bash
pip install -r requirements-ci.txt

pytest apps/ \
  --cov=apps \
  --cov-report=xml \
  --cov-fail-under=80 \
  -m "not integration and not e2e" \
  -x -q
```

**覆盖率报告**：上传到 Codecov，flag=`unit`。

**KB 功能相关测试文件**（Stage 2 覆盖范围）：
| 测试文件 | 覆盖内容 | 测试数量（估算） |
|---------|---------|--------------|
| `apps/knowledge_base/tests/test_models.py` | Document 模型 CRUD、状态约束 | ~6 |
| `apps/knowledge_base/tests/test_services.py` | `_chunk_text`, `_extract_text`, `_ocr_pdf`, `process_document`, `search` | ~20 |
| `apps/knowledge_base/tests/test_tasks.py` | Celery task 路由、max_retries、错误处理 | ~8 |
| `apps/knowledge_base/tests/test_batch_upload.py` | F-01/F-02/F-03 全部验收场景 | ~18 |
| `apps/knowledge_base/tests/test_views.py` | 单文件上传、DELETE、PATCH | ~12 |
| `apps/llm_gateway/tests/test_providers.py` | `get_provider` 工厂函数 | 3 |
| `apps/settings_vault/tests/test_views.py` | 设置存储 API | ~8 |

---

### Stage 3: Integration Tests（集成测试）

**目的**：验证跨模块、跨服务的端到端 API 行为，覆盖率目标 ≥ 90%。

**依赖**：Stage 2 完成（`needs: test-unit`）

**服务依赖**：PostgreSQL + pgvector + Redis

**关键环境变量**：
```
DJANGO_SETTINGS_MODULE=config.settings.test
REDIS_URL=redis://localhost:6379/0
```

**执行命令**：
```bash
pip install -r requirements-ci.txt
python manage.py migrate --run-syncdb

pytest tests/ \
  --cov=apps \
  --cov-report=xml \
  -m integration \
  -v
```

**KB 集成测试重点场景**：
- `POST /api/v1/knowledge/documents/batch-upload/` 完整请求生命周期（含认证 JWT 头）
- 用户隔离：user_A 上传 → user_B GET/DELETE/PATCH 均返回 404
- 搜索隔离：`search(user_a.pk, ...)` 不返回 user_B 的 DocumentChunk
- 配额扣减：上传后 `user.used_storage_bytes` 正确增加，`has_storage_quota()` 返回 False

---

### Stage 4: Frontend Build（前端构建验证）

**目的**：验证前端代码能够成功构建为生产 artifact（防止 Vite 构建错误上线）。

**依赖**：Stage 1 完成（与 Stage 2 并行，`needs: lint`）

**工作目录**：`project_workspace/content_gen_platform/src/frontend`

**执行命令**：
```bash
npm install
npm run build
```

**产出物**：`frontend/dist/` 目录上传为 GitHub Actions artifact，保留 3 天。

**KB 功能相关验证点**：
- `KnowledgeBaseView.vue` 中 `markRaw()` 包装图标（防止生产构建 TDZ — SD-L014）
- `api/index.js` 中 `batchUpload` 和 `rename` 函数正确导出
- `<input webkitdirectory multiple>` 在 Vite 构建中无警告

---

### Stage 5: Docker Build & Push

**目的**：构建生产 Docker 镜像并推送至 GHCR，仅在 `main` 分支 push 事件触发。

**依赖**：Stage 3 + Stage 4 同时完成（`needs: [test-integration, build-frontend]`）

**触发条件**：
```yaml
if: github.ref == 'refs/heads/main' && github.event_name == 'push'
```

**镜像命名规则**：
```
ghcr.io/{owner}/{repo}/backend:{sha}
ghcr.io/{owner}/{repo}/backend:latest
ghcr.io/{owner}/{repo}/frontend:{sha}
ghcr.io/{owner}/{repo}/frontend:latest
```

**特殊处理（GFW 兼容）**：
- 将 `pgvector/pgvector:pg15`、`redis:7-alpine`、`nginx:1.25-alpine` 镜像同步到 GHCR
- 生产服务器使用 GHCR 地址拉取，绕过 Docker Hub 在中国大陆的访问限制

**构建参数**：
```
platforms: linux/amd64
cache-from/to: type=gha
```

**后端镜像构建关键步骤**：
1. 安装 CPU-only PyTorch（amd64 专用索引）
2. 预下载嵌入模型 `BAAI/bge-small-zh-v1.5`（~90MB，避免生产启动时下载）
3. `collectstatic`

---

### Stage 6: Validate Production Image

**目的**：在真正部署之前，用真实镜像验证启动流程，捕获：
- Django `check` 命令失败（app 配置错误）
- `migrate` 失败（migration 冲突、SQL 错误）
- gunicorn 启动崩溃（import error、TDZ 等）

**依赖**：Stage 5 完成（`needs: docker-build`）

**验证步骤**：
1. 启动临时 pgvector + Redis 容器
2. `docker run ... manage.py check` — Django 系统检查
3. `docker run ... manage.py migrate` — 迁移验证
4. 启动 gunicorn，轮询 `POST /api/v1/auth/login/`，HTTP 200/400/401/422 视为就绪

**KB 功能验证点**：
- `DocumentBatchUploadView` 正确注册（`check` 无 URL 冲突警告）
- `batch-upload/` 路由在 gunicorn 启动后可路由

---

### Stage 7: Deploy to Production（生产部署）

**目的**：将最新镜像部署到阿里云 ECS 生产服务器。

**重要约束**：本阶段需要用户在 GitHub Actions UI 中手动 Approve（通过 `environment: production` 保护规则实现）。在 GitHub 仓库 Settings → Environments → production 中配置审批人。

**依赖**：Stage 6 通过（`needs: validate-image`）

**目标服务器**：阿里云 ECS（通过 GitHub Secrets 配置 `PROD_HOST`, `PROD_USER`, `PROD_PASSWORD`）

**部署流程**：
1. SCP 上传 `docker-compose.yml` 和 nginx 配置到 `/opt/content-gen-platform/`
2. 首次部署：自动生成 `.env`（随机 `DJANGO_SECRET_KEY` + `ENCRYPTION_KEY`）
3. `docker system prune -f`（清理磁盘，后端镜像含 PyTorch ~2GB）
4. `docker compose pull` + `docker compose up -d --remove-orphans`
5. 等待 backend container 进入 `running` 状态（最长 120s）
6. 等待 gunicorn 响应（最长 300s，首次部署含 migrate 时间）
7. `docker compose logs celery_worker`（确认模型加载日志）

---

### Stage 8: Post-deploy Smoke Tests

**目的**：生产部署后的快速健康验证，确认关键端点可用。

**依赖**：Stage 7 完成（`needs: deploy-production`）

**执行脚本**：`project_workspace/content_gen_platform/src/tests/smoke_test.sh`

**超时**：5 分钟

**KB 功能 Smoke Test 检查点**（需在 `smoke_test.sh` 中实现）：
```bash
# 检查批量上传端点可路由（401 = 认证失败但端点存在）
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE_URL/api/v1/knowledge/documents/batch-upload/)
[ "$HTTP" = "401" ] || { echo "FAIL batch-upload endpoint"; exit 1; }

# 检查文档列表端点
HTTP=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/api/v1/knowledge/documents/)
[ "$HTTP" = "401" ] || { echo "FAIL documents list endpoint"; exit 1; }
```

---

### Stage 9: E2E Tests（Playwright 端对端测试）

**目的**：浏览器级端对端验证，覆盖真实用户操作流程。

**依赖**：Stage 8 完成（`needs: smoke-test`）

**工具**：Playwright + Chromium

**工作目录**：`project_workspace/content_gen_platform/src/tests`

**KB 功能 E2E 测试场景**（`playwright test` 覆盖）：
- 登录 → 进入知识库页面 → 点击"上传目录" → 选择含嵌套子目录的文件集 → 确认文档列表出现新条目
- 点击重命名按钮 → 输入新名称 → 确认列表行名称更新
- 登出 → 登录 user_B → 确认 user_A 的文档不可见

---

## 4. 覆盖率目标汇总

| 测试阶段 | 工具 | 目标 | 强制门控 |
|---------|------|------|---------|
| 单元测试通过率 | pytest | ≥ 80% | `--cov-fail-under=80` |
| 集成测试通过率 | pytest | ≥ 90% | 任何失败即流水线中止 |
| US-* 用户故事覆盖 | 测试文件映射 | 8/8 (100%) | Code Review 验证 |
| E2E critical path | Playwright | 100% | 部署后强制 |

---

## 5. GitHub Secrets 配置清单

| Secret 名称 | 用途 | 配置位置 |
|------------|------|---------|
| `PROD_HOST` | 生产服务器 IP | Repository Secrets |
| `PROD_USER` | SSH 用户名 | Repository Secrets |
| `PROD_PASSWORD` | SSH 密码 | Repository Secrets |
| `GITHUB_TOKEN` | GHCR 推送（自动提供） | 系统自动注入 |

**Environment Protection（生产部署审批）**：
在 GitHub 仓库 Settings → Environments → `production` 中：
- Required reviewers：添加仓库 Owner 或指定审批人
- Wait timer：0 分钟（可按需调整）

---

## 6. 与 KB 新功能的关联

| 新功能 | 相关流水线阶段 | 验证方式 |
|-------|-------------|---------|
| F-01: 批量上传 | Stage 2 (unit) + Stage 3 (integration) + Stage 6 (image validate) + Stage 9 (E2E) | test_batch_upload.py + Playwright 目录上传场景 |
| F-02: 用户隔离 | Stage 2 (unit) + Stage 3 (integration) | TestUserIsolation + TestSearchUserIsolation |
| F-03: 默认文件名 + 重命名 | Stage 2 (unit) + Stage 9 (E2E) | TestFilenameDefaultAndRename + Playwright 重命名场景 |
