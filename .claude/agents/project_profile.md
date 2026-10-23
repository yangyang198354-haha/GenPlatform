# Project Profile — content_gen_platform (GenPlatform)

> 由 pm-orchestrator 在无人值守模式下扫描仓库生成的**初稿**。写入 `.claude/agents/project_profile.md` 被拒绝（权限），故按 PM §2-4 暂存于此——**请移动到 `.claude/agents/project_profile.md`**。
> 每条事实后的 `〔出处〕` 为依据；"未知"/"待确认"项须用户确认。确认后把 `<status>` 改为 APPROVED，PM 才会启动流程。
> 本文件不含任何凭据值（只写凭据存放位置）。

<file_header>
  <author_agent>pm-orchestrator(draft)</author_agent>
  <timestamp>2026-10-22T18:15:11+08:00</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>1.0.0</version>
  <status>DRAFT</status>
</file_header>

## ⚠ 待用户确认的关键项（汇总）
| # | 问题 | 初稿取值 | 依据 |
|---|---|---|---|
| Q1 | 文档工作区 `docs_root` 与布局 | `project_workspace/content_gen_platform/`，nested；新需求的产物是直接写在根下 `requirements/` 等目录，还是 `docs/<area>/<feature>/` 子目录？ | 仓库中两种用法并存，见 P2 |
| Q2 | 本地单元测试命令以哪个为准 | 按 CI 写成 `pytest apps/ -m "not integration and not e2e"`（需要 PostgreSQL+pgvector） | CLAUDE.md、settings.json hook、ci.yml 三处写法不一致，见 P4 |
| Q3 | Python 版本 | 3.12（CLAUDE.md），与 CI 的 3.11 不一致 | 见 P1 |
| Q4 | **push 到 main = 自动部署生产**；commit/push 由谁执行 | 子代理不 commit/push；主会话在用户确认后执行 | 见 P7、P9 |
| Q5 | 是否存在 staging 环境 | 否（仓库中未发现） | 见 P7 |
| Q6 | 禁用项清单 | P8 中是根据仓库推断的候选项，需用户增删 | 见 P8 |
| Q7 | `.git/hooks/pre-commit` 不存在 | CLAUDE.md 说已配置，但本机未安装 | `ls .git/hooks` 只有 *.sample |

## P1. 项目概况
- 一句话描述：AI 内容生成平台——知识库（RAG/pgvector）、LLM 网关、图片/视频生成、媒体库、内容发布〔`git ls-files` 中 `src/backend/apps/` 下的 app：accounts, content, image_generator, knowledge_base, llm_gateway, media_library, notifications, publisher, settings_vault, video_generator〕
- 技术栈：
  | 层 | 技术 | 版本 |
  |---|---|---|
  | 后端 | Python / Django / DRF / SimpleJWT | Python 3.12〔CLAUDE.md〕**vs CI 3.11**〔ci.yml test-unit `python-version`〕；Django 4.2.16、DRF 3.15.2〔requirements.txt〕 |
  | 异步 | Celery 5.4.0 + django-celery-beat + Channels 4.1（WebSocket） | 〔requirements.txt〕 |
  | 数据 | PostgreSQL 15 + pgvector 0.3.2、Redis | 〔ci.yml service `pgvector/pgvector:pg15`；requirements.txt；setup_system.sh〕 |
  | 前端 | Vue 3.4 + Vue Router 4 + Pinia 2 + Element Plus 2.7 + Vite 5 + TypeScript 5 | 〔frontend/package.json〕 |
  | 测试 | pytest 8.3 + pytest-django + pytest-cov；Playwright 1.44 | 〔requirements.txt；package.json〕 |
  | Web/进程 | gunicorn 22 + nginx + systemd | 〔deploy/systemd/*.service；deploy/nginx/〕 |
- 运行形态：Web 服务（前后端分离 SPA + REST/WebSocket API + Celery worker/beat）
- 权威说明文档：`CLAUDE.md`（开发规范）、`Makefile`（`make help`）、`docs/deployment/deployment_plan.md`、`docs/ci/e2e_branch_protection.md`。仓库没有 README。
- 外部服务：火山引擎/豆包（图片）、即梦（视频）等〔`core/volcengine_signing.py`；ci.yml 注释〕；第三方 API 密钥由 `settings_vault` 加密存储〔`core/encryption.py`，`ENCRYPTION_KEY` 环境变量〕。

## P2. 文档工作区
- `docs_root`: `project_workspace/content_gen_platform/` **（待确认 Q1）**
- `docs_layout`: nested **（待确认 Q1）**
  - 现状：根下已有 nested 结构 `requirements/ architecture/ development/ testing/ deployment/` 以及 `phase_status.md`、`delivery_report.md`（首个大版本）；后续增量需求的产物放在 `docs/{requirements|architecture|development|testing|deployment|design|features}/<feature>/`（如 `doubao_image_migration`、`v1.2_image_enhancement`、`v1.2.1_image_bugfix`、`llm_selection`）〔`git ls-files project_workspace/content_gen_platform`〕
  - 另有旧套件产物 `project_workspace/sdlc_artifacts/`（含 `agent_kb/*_lessons.md`），视为历史资料，不再写入。
  - 建议（待确认）：每个新需求用 `docs_root = project_workspace/content_gen_platform/docs/features/<feature>/`、nested，避免覆盖已批准的首版产物。
- 是否入库：是（上述文档均被 git 跟踪）〔`git ls-files`〕

## P3. 代码布局
- `code_mode`: in-repo
- 代码目录：
  | 组件 | 目录 | 语言 |
  |---|---|---|
  | 后端 Django 项目 | `project_workspace/content_gen_platform/src/backend/`（`apps/`、`config/`、`core/`） | Python |
  | 前端 | `project_workspace/content_gen_platform/src/frontend/`（`src/views`、`src/components`、`src/stores`） | Vue/TS/JS |
  | nginx（容器版） | `project_workspace/content_gen_platform/src/nginx/` | conf |
  | docker-compose | `project_workspace/content_gen_platform/src/docker-compose.yml` | YAML |
  | 部署脚本 | `scripts/deploy/*.sh`、`scripts/lib/common.sh`、`Makefile` | Bash |
  | 物理机部署配置 | `deploy/systemd/*.service`、`deploy/nginx/genplatform-physical.conf` | ini/conf |
- 测试位置约定：
  | 组件 | 新测试放在 | 命名 | 框架 |
  |---|---|---|---|
  | 后端单元/应用级集成 | `src/backend/apps/<app>/tests/` | `test_*.py`，`Test*` 类 | pytest + pytest-django；共享 fixture 在 `src/backend/conftest.py`；用到 DB/Celery 的标 `@pytest.mark.integration`〔pytest.ini；apps/*/tests〕 |
  | 后端跨模块集成 | `src/backend/tests/` | `test_*.py` | 同上（`tests/test_integration.py`） |
  | settings 测试 | `src/backend/config/tests/` | `test_*.py` | 同上 |
  | 前端 E2E | `src/frontend/e2e/` | `*.spec.ts` | Playwright（`playwright.config.ts` 本地用；`playwright.config.ci.ts` 是 CI 用的，mock 后端并自动起 vite） |
  | 旧 E2E（待确认是否仍维护） | `src/tests/e2e/*.spec.js`、`src/tests/playwright/`（根目录 `playwright.config.ts` 指向后者） | | Playwright |
- `pytest.ini` 开启了 `--strict-markers`，已注册的 marker：`unit`、`integration`；新 marker 必须先注册〔pytest.ini〕
- 不可修改的目录：`node_modules/`、`dist/`、`.venv/`（.gitignore）；`src/frontend/e2e/.auth/`（运行时生成的登录态）

## P4. 命令（全部在开发机/CI 上运行，严禁连生产）
| 用途 | 工作目录 | 命令 | 备注 |
|---|---|---|---|
| 环境准备 | `src/backend` | `pip install -r requirements-ci.txt`；需要 `DJANGO_SETTINGS_MODULE=config.settings.test` 和 POSTGRES_* 环境变量（取值见 ci.yml test-unit 的 `env`，仅测试库用） | 〔ci.yml〕**本机当前没装 Django**（`import django` 失败）——缺依赖时如实标 BLOCKED，不安装 |
| 静态检查 | `src/backend` | `ruff check apps/ config/ core/`；`bandit -r apps/ -ll --exit-zero` | 〔ci.yml lint〕 |
| 单元测试 | `src/backend` | `pytest apps/ -m "not integration and not e2e" -q` | **待确认 Q2**。CI 另加 `--cov=apps --cov-fail-under=65 -x`〔ci.yml〕；CLAUDE.md 写的是 `pytest apps/ tests/ -m "not integration" --tb=short -q`；settings.json hook 用 `apps/ -m "not integration and not e2e" -x`。注意：`config.settings.test` 仍连 PostgreSQL（pgvector），所以"单元"层也需要本地 PG；没有 PG 时可用 `DJANGO_SETTINGS_MODULE=config.settings.local_test`（SQLite，会排除 knowledge_base）〔config/settings/local_test.py〕 |
| 集成测试 | `src/backend` | 先 `python manage.py migrate`，再 `pytest tests/ apps/ -m integration -v` | 需要 PostgreSQL(pgvector)+Redis〔ci.yml test-integration〕；本地通常没有 → 由 CI 跑〔CLAUDE.md〕 |
| E2E 测试 | `src/frontend` | `npm install && npx playwright install chromium && npx playwright test --config=playwright.config.ci.ts` | CI 版 mock 后端、自动起 vite〔ci.yml e2e-frontend〕；本地版 `npx playwright test` 需要手动起前后端，baseURL 取 `E2E_BASE_URL`，缺省 `http://localhost:5173` |
| 全量回归 | `src/backend` + `src/frontend` | 单元 + 集成 + E2E 依次跑 | 耗时：未知 |
| 构建（前端） | `src/frontend` | `npm run build` | 〔ci.yml build-frontend〕 |
| 后端系统检查 | `src/backend` | `python manage.py check` | 〔ci.yml validate-image〕 |
- 已知既有失败 / 基线来源：未知。以改动前实跑为准；历史 CI 修复记录见 `project_workspace/sdlc_artifacts/agent_kb/*_lessons.md`。
- 缺依赖时的处理：如实标 BLOCKED，不安装。

## P5. 质量判定
- FULL_FLOW `gate_mode`: threshold — unit_pass 0.80 / integration_pass 0.90 / critical_path 1.00 / coverage_min 0.65（单元层，与 CI `--cov-fail-under=65` 一致）〔ci.yml〕
- INCREMENTAL `gate_mode`: baseline — 零新增失败（缺省；**本项目大部分需求预计是 INCREMENTAL**）
- `inferred_max`: 0.20（缺省，没找到项目特定值）

## P6. 开发约定
- 数据迁移：Django migrations（各 app 的 `migrations/`，目前入库 16 个）〔`git ls-files '*migrations/0*'`〕；部署时 `deploy_physical.sh`/`update_physical.sh` 自动执行 `manage.py migrate --noinput`。初稿建议（待确认）：用 `makemigrations <app>` 生成后人工审查；**已入库/已上线的迁移不得修改**；删列/删表的迁移须标 `[MANUAL_ROLLBACK_REQUIRED]`（`rollback_physical.sh` 不降级迁移，只打印提示〔rollback_physical.sh:64〕）。
- 鉴权与权限：JWT（djangorestframework-simplejwt），API 前缀 `/api/v1/`〔requirements.txt；smoke_test.sh:55〕；数据按用户隔离（历史缺陷集中点）〔software_developer_lessons.md〕。细节：未知。
- 代码风格 / lint：后端 ruff〔ci.yml〕；前端未发现 lint 配置。
- 依赖管理：后端 `requirements.txt`（生产）和 `requirements-ci.txt`（CI）都 pin 精确版本，改依赖时**两处同步**；前端 `package-lock.json` 已入库〔commit 8aa9b79〕。
- 其他约定：
  - 凭据一律从环境变量读（变量名见 `.env.example`）；第三方 API key 经 `core/encryption.py` 加密后存 DB。
  - Celery 中处理文件/ML 推理的任务必须设 `soft_time_limit` 并分批〔software_developer_lessons.md 经验五〕。
  - 前端新增表单控件要加唯一的 `name`/`data-testid`〔test_engineer_lessons.md 经验三〕。
  - 生产机内存紧张（已有 4GB swap 运维 workflow 和内存阈值守护）〔.github/workflows/add_swap.yml；commit 5ab060a〕，新增常驻进程或加载大模型要评估内存。

## P7. 环境、CI 与部署
- 环境：
  | 环境 | 存在 | 访问方式（不含口令） | 部署需用户确认 | 备注 |
  |---|---|---|---|---|
  | dev/local | 是 | 本机；`npm run dev`（vite :5173）+ Django；`docker-compose.yml` 可起全套 | 否 | 〔package.json；src/docker-compose.yml〕 |
  | CI | 是 | GitHub Actions（PG/Redis 服务容器） | 否 | 只跑测试；PR 不部署〔ci.yml compute-deploy-mode〕 |
  | staging | **否（待确认 Q5）** | — | — | 仓库里没有 staging 配置（`git grep -i staging` 无结果） |
  | production | 是 | 阿里云 ECS 单机；SSH 凭据在 GitHub Secrets `PROD_HOST`/`PROD_USER`/`PROD_PASSWORD`；GitHub environment `production` | **是** | 〔ci.yml deploy-physical-prod〕 |
- **部署方式**：
  - **push 到 `main` 会自动触发生产物理机部署**（ci.yml：test-integration + build-frontend 通过后跑 `deploy-physical-prod` → `smoke-test`）。所以 **`git push origin main` 本身就是一次生产部署**，需要与 E2 同级的授权。〔ci.yml:618-622〕
  - push 到 `develop` 也会解析成 physical，但部署 job 要求 `github.ref == 'refs/heads/main'`，所以不会部署。
  - 手动方式：`workflow_dispatch`（ci.yml，可选 physical/docker/none），或 `.github/workflows/deploy-physical.yml`（只能手动）。
  - 物理机：代码上传到 `/opt/genplatform/app` → `scripts/deploy/deploy_physical.sh`（可选先跑 `setup_system.sh`）；前端在 Runner 上构建后上传 dist〔ci.yml；commit 5ab060a〕。
  - Docker 模式（GHCR 镜像 + compose）保留为需显式选择的可选模式〔ci.yml docker-build/deploy-production；Makefile〕。
- 允许的部署策略：recreate（单机重启 / graceful reload；`update_physical.sh` 做 gunicorn graceful reload + celery warm shutdown）。不支持 blue-green/canary（单机、无负载均衡）〔scripts/deploy/〕
- 构建产物管理：物理机模式无制品库（源码 + Runner 构建的前端 dist artifact）；Docker 模式用 GHCR `ghcr.io`〔ci.yml〕
- 运行单元与"改什么要重启什么"：
  | 运行单元 | systemd unit | 触发重启的改动 |
  |---|---|---|
  | Django API（gunicorn） | `genplatform-backend` | 任何后端 Python/settings 改动 |
  | Celery worker | `genplatform-celery`（先 stop 再 start，不用 restart） | tasks/services/模型改动 |
  | Celery beat | `genplatform-celery-beat` | 定时任务配置改动 |
  | nginx | `nginx`（reload） | nginx 配置、前端 dist |
  | PostgreSQL 15 / Redis | `postgresql-15`/`redis` | 不随应用重启 |
  〔deploy/systemd/*.service；Makefile restart-physical；rollback_physical.sh:108-115〕
- 目标机上必须保留的本地状态：`/opt/genplatform/app/.env` 和 `/opt/genplatform/.env`（首次部署生成，含生成的密钥，**不得覆盖或删除**）、`/opt/genplatform/media`（MEDIA_ROOT，用户上传和生成的内容）、`/opt/genplatform/staticfiles`、`/opt/genplatform/.last_deployed_commit`、`/opt/genplatform/venv`、PostgreSQL 数据、HuggingFace 模型缓存（路径未知）〔ci.yml deploy-physical-prod 步骤 1；update_physical.sh；deploy_physical.sh〕
- 回滚方式：`make rollback-physical [VERSION=<commit>]`（缺省回到 `.last_deployed_commit`：git checkout + migrate + 重启；**不降级迁移**）；Docker 模式用 `make rollback-docker TAG=<tag>`。也可以 revert 提交后重新 push（会再次触发自动部署）。偏好哪种：未知（待确认）。
- 部署后验证：`make smoke-test` / `scripts/deploy/smoke_test.sh --mode physical --url http://<PROD_HOST>`（检查 `/api/v1/auth/login/` 可达、前端首页、celery 服务 active、数据库）；`make status`；`make logs SERVICE=backend|celery|celery-beat|nginx`（journalctl）〔Makefile；smoke_test.sh〕
- CI 系统与配置文件：GitHub Actions — `.github/workflows/ci.yml`（主流水线）、`deploy-physical.yml`（手动部署）、`add_swap.yml`、`diagnose-prod.yml`、`diagnose-kb-upload.yml`（运维/诊断）。E2E 不允许被跳过（有 `assert-e2e-ran` job）〔ci.yml；docs/ci/e2e_branch_protection.md〕
- 部署相关配置文件：`Makefile`、`scripts/deploy/*.sh`、`scripts/lib/common.sh`、`deploy/systemd/*.service`、`deploy/nginx/genplatform-physical.conf`、`project_workspace/content_gen_platform/src/docker-compose.yml`、`src/backend/Dockerfile`、`src/frontend/Dockerfile`、`src/nginx/nginx.conf`、`.env.example`、`src/.env.example`

## P8. 禁用项（门控时任一出现即 FAIL）— **候选，待用户确认 Q6**
| 禁用的技术 / 操作 | 原因 |
|---|---|
| 未经用户当轮授权 `git push` 到 `main`（含合并到 main） | push 即自动部署生产（ci.yml） |
| 子代理 ssh/scp 到生产机、手动触发部署 workflow | settings.json 已把 ssh/scp/git push 设为 ask；生产操作须用户授权 |
| 覆盖或重新生成目标机 `.env`、删除 `/opt/genplatform/media` 或数据库数据 | 这些本地状态包含生成的密钥和用户数据 |
| 修改已入库的 Django migration 文件 | 生产已执行过，改了会导致 schema 不一致 |
| 测试连接生产数据库/服务；在测试或文档里写真实凭据 | 协议 §L |
| 依赖 Redis 或真实外部 API 的测试不标 `integration`（混进单元层） | CI 单元层没有 Redis（test.py 用 LocMem 和内存 broker） |
| 跳过/禁用 E2E 或 `assert-e2e-ran` job；不加说明就降低 `--cov-fail-under` | 历史事故 INC-2026-05-15-e2e-job-skipped |
| 引入新的数据库（替代 PostgreSQL/pgvector）或消息队列（替代 Celery+Redis） | 现有架构约束（推断，待确认） |

## P9. 版本控制与远程操作权限
- 分支策略：主分支 `main`（push 即部署生产）；`develop` 触发 CI 但不部署；PR 到 `main` 只跑测试；远程有 `claude/*` 分支〔`git branch -a`；ci.yml〕。是否要求所有改动都走 PR：未知（待确认）。
- 谁执行 commit / push：**子代理一律不执行**；主会话在用户确认后执行 commit；push 到 `main` 视为生产部署，须用户在当轮明确授权〔初稿缺省，待确认 Q4〕。
- 子代理能否 ssh / 部署：否。E2 授权后 devops-engineer 用哪种方式部署（直接 push / 触发 workflow_dispatch / ssh 执行 make）：未知，待确认。
- 提交前必须通过的检查：后端单元测试全部通过（CLAUDE.md）。实现机制：`.claude/settings.json` 的 PreToolUse hook 在 `git commit` 前跑 `pytest apps/ -m "not integration and not e2e" -x`，**但本地 5432 端口没有 PostgreSQL 时会直接跳过**；CLAUDE.md 说的 `.git/hooks/pre-commit` 本机不存在（Q7）。紧急情况可用 `--no-verify`，但下次提交前要补跑〔CLAUDE.md〕。

## P10. 额外必读（PM 填入 required_reading）
| Agent | 额外文件 |
|---|---|
| software-developer | `CLAUDE.md`；`project_workspace/sdlc_artifacts/agent_kb/software_developer_lessons.md` |
| test-engineer | `CLAUDE.md`；`project_workspace/content_gen_platform/src/backend/pytest.ini`；`project_workspace/sdlc_artifacts/agent_kb/test_engineer_lessons.md`；`docs/ci/e2e_branch_protection.md` |
| devops-engineer | `Makefile`；`.github/workflows/ci.yml`；`docs/deployment/deployment_plan.md`；`project_workspace/sdlc_artifacts/agent_kb/devops_engineer_lessons.md` |
| system-architect | `project_workspace/content_gen_platform/architecture/architecture_design.md`、`module_design.md`（首版基线，可能已过时——以代码为准） |
| requirement-analyst | `project_workspace/content_gen_platform/requirements/requirements_spec.md`（首版基线） |


## 沙箱试运行建议（2026-10-22，非用户确认；请逐项核对，确认后把 status 改为 APPROVED）
> 以下是沙箱测试时为跑通流程采用的选择，供确认时参考；基线数字来自测试机，换机器后以实跑为准。
- docs_root = `project_workspace/sdlc/{project_name}/`，docs_layout = nested（避免与 `project_workspace/content_gen_platform/` 下的代码和历史文档混在一起）。
- 本地测试命令以 CI 为准：`cd project_workspace/content_gen_platform/src/backend && DJANGO_SECRET_KEY=x ENCRYPTION_KEY=dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ= python -m pytest apps/ -m "not integration and not e2e" -q`。
- **本机没有 PostgreSQL/Redis**：需要数据库的用例会报 `psycopg2.OperationalError: connection refused`，属环境失败。基线（2026-10-22 实跑）：204 passed / 2 skipped / 322 errors（全部为 PostgreSQL 连接拒绝）。integration 层在本机无法执行，如实标 BLOCKED；不得安装数据库或启动容器。
- Python 3.12（以本机 venv 为准）。
- 没有 staging。push 到 main 会触发生产部署：子代理不 commit/push，本次测试不授权任何部署。
- 禁用项按 P8 候选项确认，另加：测试中启动 Docker/安装系统服务。
- pre-commit hook 未安装：忽略 Q7。
