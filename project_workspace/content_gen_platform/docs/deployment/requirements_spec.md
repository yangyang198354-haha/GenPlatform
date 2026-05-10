<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-05-10T00:00:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>1.0.0</version>
  <phase>PARTIAL_FLOW / GROUP_A</phase>
  <status>DRAFT</status>
  <scope>物理机部署方式扩展需求规格说明书</scope>
</file_header>

# 需求规格说明书 — 物理机部署方式扩展

## 文档概述

**变更背景**：GenPlatform 现有部署方式为纯 Docker Compose，每次发布需要 build 镜像并在生产环境拉取，耗时较长，影响发布效率。本需求描述在保留 Docker 部署的前提下，新增"物理机直接部署"路径作为默认部署方式。

**范围说明**：本文档仅覆盖部署基础设施层的需求变更，不涉及应用业务逻辑变更。

**来源引用**：所有需求均来源于用户在 2026-05-10 提交的业务需求描述（以下简称"原始需求"）。

---

## 1. 利益相关方

| 角色 | 关注点 |
|------|--------|
| 运维工程师 | 日常部署效率、操作简单性、失败时快速回滚 |
| 开发工程师 | 部署脚本可维护性、本地开发不受影响 |
| 项目负责人 | 发布速度提升、两种部署方式的长期可维护性 |

---

## 2. 功能需求

### REQ-DEPLOY-FUNC-001：物理机部署为默认路径

**来源**：原始需求 — "默认：物理部署（直接在宿主机安装依赖、启动服务）"

**描述**：系统必须提供物理机直接部署方式，作为标准发布路径。物理机部署指在宿主机上直接安装 Python、Node.js、PostgreSQL、Redis 等依赖，使用 systemd 或 Supervisor 管理进程，使用 Nginx 服务前端静态文件和反向代理。

**验收标准（Given/When/Then）**：
- Given 一台满足最低配置要求的 Linux 服务器（Ubuntu 22.04 / Debian 12）
- When 运维人员执行物理部署命令（如 `make deploy-physical`）
- Then 所有服务（Django ASGI、Celery Worker、Celery Beat、Nginx）在宿主机进程中运行，并通过健康检查

**优先级**：P0（必须实现）

---

### REQ-DEPLOY-FUNC-002：Docker 部署路径保留且可显式切换

**来源**：原始需求 — "可选：Docker 部署（通过显式参数/标志指定）"；"两种方式需要并存，不能废弃任何一种"

**描述**：现有 Docker Compose 部署路径必须完整保留，不做任何破坏性修改。运维人员可通过显式参数（如 `--mode=docker` 或 `make deploy-docker`）选择 Docker 部署。

**验收标准**：
- Given 生产环境希望使用 Docker 部署
- When 运维人员执行 Docker 部署命令（如 `make deploy-docker`）
- Then 系统以 Docker Compose 方式完整启动，行为与当前生产环境一致，现有 docker-compose.yml 不被破坏

**优先级**：P0（必须实现）

---

### REQ-DEPLOY-FUNC-003：物理机部署覆盖全部服务组件

**来源**：原始需求 — "后端（Django + Celery Worker + Celery Beat）、前端（Vue3 构建产物，通过 Nginx/类似方式服务）、PostgreSQL、Redis"

**描述**：物理机部署必须支持以下所有服务组件的安装与管理：
- 后端：Django ASGI（Gunicorn + Uvicorn Worker）
- 异步任务：Celery Worker（处理 default/video/publish 队列）
- 定时任务：Celery Beat（使用 Django DatabaseScheduler）
- 前端：Vue3 构建产物（通过 Nginx 服务静态文件）
- 数据库：PostgreSQL 15+ 含 pgvector 扩展
- 缓存/消息队列：Redis 7+

**验收标准**：
- Given 物理机部署完成
- When 运维人员执行服务状态检查（如 `make status`）
- Then 以上6个服务组件全部显示"运行中"，且全部通过健康检查

**优先级**：P0（必须实现）

---

### REQ-DEPLOY-FUNC-004：部署方式选择不影响应用配置

**来源**：原始需求隐含 — 两种部署方式共存，环境变量配置应统一

**描述**：无论选择物理机部署还是 Docker 部署，应用层的环境变量配置格式（`.env` 文件格式）必须一致，不需要为不同部署方式维护两套应用配置文件。数据库连接、Redis 地址、API Key 等配置项在两种模式下使用相同的 `.env` 结构。

**验收标准**：
- Given 已存在 `.env` 配置文件（符合 `.env.example` 格式）
- When 运维人员分别用物理机和 Docker 方式部署同一份配置
- Then 应用行为一致，不需要修改 `.env` 中的应用级变量（只有 DB Host、Redis URL 等连接地址因部署方式不同而不同，且有文档说明）

**优先级**：P1（重要）

---

### REQ-DEPLOY-FUNC-005：物理机部署支持服务进程管理

**来源**：原始需求 — "直接在宿主机安装依赖、启动服务"

**描述**：物理机部署必须通过 systemd 或 Supervisor 管理所有应用进程（Django ASGI、Celery Worker、Celery Beat），实现：开机自启、进程崩溃后自动重启、统一的日志收集路径、标准的 start/stop/restart/status 操作接口。

**验收标准**：
- Given 物理机部署完成，systemd/Supervisor 单元已配置
- When 运维人员手动 kill Django 进程
- Then 进程管理器在 5 秒内自动重启该进程，并在系统日志中记录重启事件

**优先级**：P0（必须实现）

---

### REQ-DEPLOY-FUNC-006：物理机部署包含数据库初始化和迁移

**来源**：原始需求隐含 — 物理机部署必须完整可用

**描述**：物理机部署流程必须包含：PostgreSQL 数据库创建、pgvector 扩展安装、Django migrations 执行、初始超级用户创建（可选）。后续增量部署时，必须自动执行新增 migrations。

**验收标准**：
- Given 目标物理机已安装 PostgreSQL 15+
- When 运维人员执行首次部署
- Then PostgreSQL 中创建目标数据库、pgvector 扩展可用、所有 Django migrations 已执行，`manage.py migrate --check` 返回 0

**优先级**：P0（必须实现）

---

### REQ-DEPLOY-FUNC-007：物理机部署的前端静态文件服务

**来源**：原始需求 — "前端（Vue3 构建产物，通过 Nginx/类似方式服务）"

**描述**：物理机部署时，必须在部署流程中执行 `npm run build` 生成前端构建产物，并配置 Nginx 服务这些静态文件，同时配置 API 代理（/api/）、WebSocket 代理（/ws/）、SSE 支持和媒体文件服务（/media/）。

**验收标准**：
- Given 物理机部署完成，Nginx 已配置
- When 用户通过浏览器访问部署域名
- Then 前端 SPA 正常加载，API 请求正常代理到 Django，WebSocket 连接正常建立

**优先级**：P0（必须实现）

---

### REQ-DEPLOY-FUNC-008：增量更新部署（物理机热更新）

**来源**：原始需求隐含 — 解决发布效率问题的核心场景

**描述**：物理机部署必须支持增量更新场景（即不重装依赖的情况下，仅更新代码和配置）。更新流程应包括：git pull 拉取最新代码、pip install（仅在 requirements.txt 变更时）、npm build（仅在前端代码变更时）、migrate 迁移、collectstatic、进程重启。

**验收标准**：
- Given 物理机已有运行中的应用
- When 运维人员执行增量更新命令（如 `make update-physical`）
- Then 服务在 60 秒内完成更新并重新对外服务，期间 downtime 控制在最短（目标 < 30 秒）

**优先级**：P1（重要）

---

### REQ-DEPLOY-FUNC-009：部署失败回滚机制

**来源**：原始需求 — "失败回滚场景"（运维人员视角）

**描述**：物理机部署和 Docker 部署均必须提供回滚机制：
- 物理机部署：通过 git checkout 回退代码版本，配合 migrate 反向迁移（可选），重启进程
- Docker 部署：通过 docker compose pull 指定旧镜像 tag，重新 up

**验收标准**：
- Given 一次部署操作导致应用启动失败（Django 无法启动）
- When 运维人员执行回滚命令（如 `make rollback-physical VERSION=<commit>`）
- Then 应用回退到指定版本并重新正常运行，回滚耗时 < 5 分钟

**优先级**：P1（重要）

---

### REQ-DEPLOY-FUNC-010：嵌入模型（Embedding Model）的物理机加载

**来源**：现有 Dockerfile 和 docker-compose.yml 中的 embedding model pre-warm 逻辑（BAAI/bge-small-zh-v1.5，约 90MB）

**描述**：物理机部署时必须处理 sentence-transformers 嵌入模型的首次下载（或离线预置）问题。需支持通过配置 HF_ENDPOINT（如 hf-mirror.com）绕过网络限制；首次部署时需明确文档说明模型下载时间预期，并在 systemd/Supervisor 启动配置中设置足够的启动超时时间。

**验收标准**：
- Given 物理机位于网络受限环境（GFW）
- When 运维人员执行物理机部署
- Then 通过配置 HF_ENDPOINT=https://hf-mirror.com，嵌入模型可正常下载，Celery Worker 成功启动

**优先级**：P1（重要）

---

## 3. 非功能需求

### REQ-DEPLOY-NFUNC-001：部署操作的幂等性

**来源**：原始需求隐含 — 运维友好性

**描述**：所有部署脚本/命令必须是幂等的：在已部署状态下重复执行不产生副作用（不重复创建数据库、不重复安装已有的系统包）。

**优先级**：P1

---

### REQ-DEPLOY-NFUNC-002：部署文档完整性

**来源**：原始需求 — 运维人员视角的使用场景

**描述**：必须提供完整的物理机部署操作手册，涵盖：最低系统要求、前置依赖清单、逐步操作指南、常见错误排查、回滚操作。文档必须以实际命令为主，减少说明性文字。

**优先级**：P1

---

### REQ-DEPLOY-NFUNC-003：两种部署方式的配置一致性校验

**来源**：原始需求 — 两种方式需要并存

**描述**：构建/部署工具必须提供配置校验命令（如 `make validate-config`），验证 `.env` 文件包含所有必需的变量，避免因配置缺失导致启动失败。

**优先级**：P2

---

### REQ-DEPLOY-NFUNC-004：物理机最低配置要求

**来源**：原始需求隐含 — 运维人员需了解硬件要求

**描述**：
- CPU：2 核及以上
- 内存：4 GB（含嵌入模型加载，推荐 8 GB）
- 磁盘：20 GB（系统 + 应用 + 模型缓存 + 媒体文件）
- OS：Ubuntu 22.04 LTS / Debian 12（首选），CentOS Stream 9（次选）
- 网络：能访问 hf-mirror.com 或已预置模型缓存

**优先级**：P1

---

## 4. 约束与排除项

| 约束/排除项 | 说明 |
|------------|------|
| 不废弃 Docker 部署 | 现有 `docker-compose.yml` 不做破坏性修改，保留完整功能 |
| 不修改应用业务逻辑 | 本次变更仅限部署基础设施层，不改动 Django apps 代码 |
| 不引入 Kubernetes | 当前规模不需要 K8s，增加运维复杂度 |
| 物理机 PostgreSQL 需支持 pgvector | 必须确认目标 OS 的 PostgreSQL 包含 pgvector 扩展或可单独安装 |
| 不改变 CI/CD 触发方式 | GitHub Actions 现有 CI 流程不变，CD 部分可选扩展物理机部署步骤 |
