<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-05-10T00:05:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>1.0.0</version>
  <phase>PARTIAL_FLOW / GROUP_A</phase>
  <status>DRAFT</status>
  <scope>物理机部署方式扩展用户故事</scope>
</file_header>

# 用户故事清单 — 物理机部署方式扩展

## 角色定义

- **运维工程师（Ops）**：负责日常部署、维护、监控的人员，熟悉 Linux 命令行，但不一定熟悉 Django/Python 内部细节
- **开发工程师（Dev）**：修改代码并触发部署的人员
- **项目负责人（PO）**：关注发布效率和系统稳定性的决策人

---

## US-DEPLOY-001：首次物理机部署

**角色**：运维工程师

**故事**：作为运维工程师，我希望通过一套清晰的命令完成首次物理机部署，这样我不需要深入理解 Django 和 Python 环境就能成功部署整个系统。

**验收标准（AC）**：

**AC-001-1：环境准备**
- Given 一台全新的 Ubuntu 22.04 服务器，已安装 git
- When 运维工程师执行 `make setup-physical`（或等效的初始化命令）
- Then 系统自动安装：Python 3.12、Node.js 20+、PostgreSQL 15+、Redis 7+、Nginx、ffmpeg、tesseract-ocr 及其中文语言包、libpq-dev 等系统依赖；安装完成后各组件版本可通过命令验证

**AC-001-2：应用部署**
- Given 环境准备完成，`.env` 文件已按 `.env.example` 填写完毕
- When 运维工程师执行 `make deploy-physical`
- Then Python 虚拟环境创建、pip 依赖安装、前端构建（npm ci && npm run build）、Django migrate、collectstatic 均成功执行，无报错

**AC-001-3：服务启动**
- Given 应用部署完成
- When 运维工程师执行 `make start-physical` 或 systemd/Supervisor 服务启动命令
- Then 以下进程在宿主机运行：gunicorn（Django ASGI）、celery worker、celery beat、nginx；通过 `make status` 可查看所有服务状态为"运行中"

**AC-001-4：首次部署冒烟测试**
- Given 所有服务启动完成
- When 运维工程师执行 `make smoke-test` 或访问健康检查端点
- Then `GET /api/v1/auth/login/` 返回 200 或 405（非 500），`GET /` 返回前端 HTML，WebSocket 端点 `/ws/notifications/` 可建立连接

---

## US-DEPLOY-002：增量更新（热更新发布）

**角色**：运维工程师

**故事**：作为运维工程师，我希望在代码更新时能够快速执行增量部署，这样发布效率比 Docker 构建镜像要高，且不会因为网络问题导致发布阻塞。

**验收标准（AC）**：

**AC-002-1：代码更新部署**
- Given 物理机已运行，新版本代码已推送到 main 分支
- When 运维工程师执行 `make update-physical`
- Then 自动完成：git pull、pip install（仅 requirements.txt 有变更时）、npm build（仅前端代码有变更时）、migrate、collectstatic、进程重启；整个流程在 60 秒内完成

**AC-002-2：无变更时的幂等性**
- Given 物理机已运行当前最新代码
- When 运维工程师再次执行 `make update-physical`
- Then 操作成功完成（返回 0），服务继续运行，不产生副作用（不重复安装依赖、不产生冗余迁移）

**AC-002-3：零停机目标**
- Given 增量更新过程中
- When 运维工程师或自动化脚本执行进程重启
- Then Django 服务使用 gunicorn 的 graceful reload（`kill -HUP`）或短暂停机（< 30 秒）重启，期间 Celery worker 已接受的任务不丢失（通过 acks_late 或 warm shutdown 保障）

---

## US-DEPLOY-003：切换到 Docker 部署

**角色**：运维工程师

**故事**：作为运维工程师，我希望在需要时能够切换到 Docker 部署方式，这样在物理机部署出现问题时有备用方案，或者在新服务器上快速复制环境。

**验收标准（AC）**：

**AC-003-1：显式指定 Docker 部署**
- Given 服务器已安装 Docker 和 Docker Compose
- When 运维工程师执行 `make deploy-docker`（或 `--mode=docker`）
- Then 以 Docker Compose 方式启动所有服务，现有 `docker-compose.yml` 不被修改，行为与当前生产环境一致

**AC-003-2：Docker 路径不被物理机路径干扰**
- Given 物理机部署已存在（虚拟环境、systemd 服务等）
- When 运维工程师在同一台机器上执行 `make deploy-docker`
- Then Docker 部署独立运行，不与物理机部署的进程/端口冲突（或有明确的端口冲突检测和提示）

---

## US-DEPLOY-004：部署失败后回滚

**角色**：运维工程师

**故事**：作为运维工程师，我希望在部署失败时能够快速回滚到上一个稳定版本，这样能将对用户的影响降到最低。

**验收标准（AC）**：

**AC-004-1：物理机部署回滚**
- Given 一次物理机增量更新导致 Django 启动失败（如 migration 错误）
- When 运维工程师执行 `make rollback-physical VERSION=<git_commit_or_tag>`
- Then 代码回退到指定版本、dependencies 恢复、migrate 反向（如有 down migration）、进程重启；服务在 5 分钟内恢复正常

**AC-004-2：回滚前的状态保存**
- Given 执行部署操作之前
- When 部署脚本启动
- Then 自动记录当前 git commit hash 到本地文件（如 `.last_deployed_commit`），供回滚命令使用；若无指定 VERSION，回滚命令默认使用此记录

**AC-004-3：Docker 部署回滚**
- Given 一次 Docker 镜像更新导致服务异常
- When 运维工程师执行 `make rollback-docker TAG=<previous_image_tag>`
- Then Docker Compose 切换到指定旧镜像版本并重启服务，回滚过程 < 5 分钟

---

## US-DEPLOY-005：服务状态监控与日志查看

**角色**：运维工程师

**故事**：作为运维工程师，我希望通过统一的命令查看所有服务的状态和日志，这样排查问题时不需要记忆不同服务的日志路径。

**验收标准（AC）**：

**AC-005-1：统一状态查看**
- Given 物理机部署已启动
- When 运维工程师执行 `make status`
- Then 一次性显示：gunicorn/celery-worker/celery-beat/nginx 的运行状态（running/stopped/failed）、PID、运行时间

**AC-005-2：日志快速访问**
- Given 物理机部署已运行
- When 运维工程师执行 `make logs SERVICE=backend`（或 `celery_worker`、`celery_beat`）
- Then 显示对应服务最近 100 行日志，并支持 `-f` 参数实时跟踪

**AC-005-3：Docker 部署的状态一致性**
- Given Docker 部署已运行
- When 运维工程师执行 `make status`（相同命令）
- Then 显示 Docker 容器的运行状态，格式与物理机部署状态输出结构一致（尽管实现不同）

---

## US-DEPLOY-006：环境变量配置管理

**角色**：运维工程师

**故事**：作为运维工程师，我希望有工具帮我验证 `.env` 文件配置是否完整，这样在部署前能提前发现配置缺失问题，而不是在服务启动时才报错。

**验收标准（AC）**：

**AC-006-1：配置完整性校验**
- Given 运维工程师已准备 `.env` 文件
- When 运维工程师执行 `make validate-config`
- Then 工具检查所有必填变量是否存在（DJANGO_SECRET_KEY、ENCRYPTION_KEY、POSTGRES_PASSWORD、ALLOWED_HOSTS、CORS_ALLOWED_ORIGINS、REDIS_URL/DATABASE_URL）；缺失时列出缺失项，并给出对应的说明

**AC-006-2：物理机 vs Docker 连接地址差异提示**
- Given 运维工程师使用同一份 `.env` 文件
- When 工具检测到 DATABASE_URL 包含 `@db:5432`（Docker 服务名）而当前选择物理机部署
- Then 工具输出警告，提示物理机部署时 PostgreSQL host 应为 `localhost` 或实际 IP，并说明如何修改

---

## US-DEPLOY-007：嵌入模型的离线/镜像加速处理

**角色**：运维工程师

**故事**：作为运维工程师，我希望在网络受限的服务器（如 GFW 内）也能完成物理机部署，这样不需要依赖 HuggingFace 官网的直连访问。

**验收标准（AC）**：

**AC-007-1：HF 镜像加速配置**
- Given 服务器无法直连 huggingface.co，`.env` 中配置了 `HF_ENDPOINT=https://hf-mirror.com`
- When 运维工程师执行 `make deploy-physical`（触发 Celery Worker 首次启动）
- Then 嵌入模型（BAAI/bge-small-zh-v1.5）通过镜像站成功下载，Worker 正常启动

**AC-007-2：模型缓存预置**
- Given 运维工程师已在本地下载好模型文件（`~/.cache/huggingface/`）
- When 手动将模型文件复制到目标服务器对应路径
- Then Celery Worker 启动时使用本地缓存，不触发网络下载；部署文档中有此操作的详细说明

---

## US-DEPLOY-008：开发工程师的本地开发不受影响

**角色**：开发工程师

**故事**：作为开发工程师，我希望新增的物理机部署工具链不影响我的本地开发环境，这样不需要了解部署细节就能继续开发。

**验收标准（AC）**：

**AC-008-1：本地开发环境隔离**
- Given 开发工程师使用 `docker compose up` 在本地运行开发环境
- When 项目引入物理机部署工具链（Makefile、systemd 配置、部署脚本）
- Then 本地开发流程（`docker compose up`、`pytest`、`npm run dev`）完全不变，无新增强制依赖

**AC-008-2：CI 测试不受影响**
- Given GitHub Actions CI 现有测试流程（`pytest apps/ tests/ -m "not integration"`）
- When 引入物理机部署工具链
- Then CI 测试 pipeline 继续通过，无新增测试失败
