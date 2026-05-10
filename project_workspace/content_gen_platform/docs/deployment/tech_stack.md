<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-05-10T00:20:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>1.0.0</version>
  <phase>PARTIAL_FLOW / GROUP_B</phase>
  <status>DRAFT</status>
  <input_files>
    <file>docs/deployment/requirements_spec.md (DRAFT)</file>
    <file>docs/deployment/architecture_design.md (DRAFT)</file>
    <file>docs/deployment/module_design.md (DRAFT)</file>
  </input_files>
  <scope>物理机部署工具链技术选型</scope>
</file_header>

# 技术选型表 — 物理机部署工具链

## 1. 物理机部署新增工具链

以下是物理机部署方式新引入的技术选型，均不影响现有应用技术栈。

### 1.1 进程管理

| 技术 | 版本要求 | 用途 | 选型理由 | ADR 引用 |
|------|---------|------|---------|---------|
| systemd | Ubuntu 22.04 内置（v249+） | 管理 gunicorn / celery worker / celery beat 进程 | OS 内置，零额外依赖；支持开机自启、崩溃重启、依赖声明、journald 日志 | ADR-DEPLOY-001 |
| Supervisor | 4.2+ | 降级备选（无 root 权限或非标准 Linux 场景） | 无需 root 即可安装运行；Web UI 方便管理 | ADR-DEPLOY-001 |

**主选：systemd**（Ubuntu 22.04 / Debian 12）
**降级：Supervisor**（CentOS Stream 9 或特殊环境）

---

### 1.2 Web 服务器 / 反向代理

| 技术 | 版本要求 | 用途 | 安装方式 |
|------|---------|------|---------|
| Nginx | 1.18+（Ubuntu 22.04 默认）或 1.25+（推荐） | 反向代理 Django ASGI（端口 8000）、直接服务 Vue3 构建产物静态文件、SSE/WebSocket 代理 | `apt install nginx` |

**配置文件**：`config/deploy/nginx/nginx-physical.conf`（物理机专用）
**与 Docker 版差异**：物理机版去掉 `proxy_pass http://frontend` 层，改为 `root /opt/genplatform/staticfiles; try_files` 直接服务静态文件，减少一次网络跳转。

---

### 1.3 Python 运行时与依赖管理

| 技术 | 版本要求 | 用途 | 安装方式 |
|------|---------|------|---------|
| Python | 3.12（与 Docker 中 `python:3.11-slim` 的升级对齐，推荐 3.12） | 运行 Django、Celery 等所有 Python 进程 | `apt install python3.12 python3.12-venv python3.12-dev` |
| venv | Python 内置 | Python 虚拟环境隔离 | `python3.12 -m venv /opt/genplatform/venv` |
| pip | 最新版（venv 内） | Python 包管理 | venv 内置 |

**注意**：Dockerfile 使用 `python:3.11-slim`；物理机部署推荐使用 Python 3.12（Ubuntu 22.04 的 `python3.12` apt 包），两者兼容（应用代码不依赖特定 Python 3.11 语法）。若需严格对齐，可在 `setup_system.sh` 中使用 `deadsnakes` PPA 安装 Python 3.11。

---

### 1.4 Node.js / 前端构建

| 技术 | 版本要求 | 用途 | 安装方式 |
|------|---------|------|---------|
| Node.js | 20 LTS | 执行 `npm ci` 和 `npm run build`（Vite 构建） | `apt install nodejs`（NodeSource 20.x PPA）|
| npm | 10+（Node.js 20 内置） | 前端依赖管理 | Node.js 内置 |

**构建产物路径**：`src/frontend/dist/` → 复制到 `/opt/genplatform/staticfiles/`

**可选优化**（无 Node.js 方案）：CI（GitHub Actions）构建前端产物，rsync 到服务器，服务器不安装 Node.js，节省约 150MB 磁盘和 RAM。详见 ADR-DEPLOY-003 选项 B。

---

### 1.5 数据库

| 技术 | 版本要求 | 用途 | 安装方式 | ADR 引用 |
|------|---------|------|---------|---------|
| PostgreSQL | 15（PGDG 官方 apt 源） | 主数据库，与 Docker 中 pgvector:pg15 镜像对应 | PGDG apt 源 + `apt install postgresql-15` | ADR-DEPLOY-004 |
| pgvector | 0.6+（`postgresql-15-pgvector`） | 向量存储扩展（知识库 Embedding） | `apt install postgresql-15-pgvector`（PGDG 源已包含） | ADR-DEPLOY-004 |

**PGDG 源添加**：
```bash
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
apt-get update
apt-get install -y postgresql-15 postgresql-15-pgvector
```

---

### 1.6 消息队列 / 缓存

| 技术 | 版本要求 | 用途 | 安装方式 |
|------|---------|------|---------|
| Redis | 7.x | Celery Broker + Django Channels Channel Layer + 缓存（与 Docker 中 redis:7-alpine 对应） | `apt install redis-server`（Ubuntu 22.04 仓库版本为 7.x）|

---

### 1.7 系统级工具

| 技术 | 版本要求 | 用途 | 安装方式 |
|------|---------|------|---------|
| FFmpeg | 5.x+（Ubuntu 22.04 默认）| 视频合成（`VideoCompositorService.compose()`，与 Dockerfile 中 `ffmpeg` 包一致） | `apt install ffmpeg` |
| Tesseract OCR | 4.1+（Ubuntu 22.04 默认）| PDF 文本提取（`pytesseract`） | `apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng` |
| Poppler | 22.x+（Ubuntu 22.04 默认）| PDF 转图片（`pdf2image`） | `apt install poppler-utils` |
| libpq-dev | PostgreSQL 15 对应版本 | Python `psycopg2` 编译依赖 | `apt install libpq-dev` |
| build-essential | Ubuntu 22.04 默认 | 编译 Python C 扩展 | `apt install build-essential` |
| curl / wget | 系统内置 | 脚本中 health check 调用 | 系统内置 |

---

### 1.8 部署脚本工具

| 技术 | 版本要求 | 用途 | 来源 |
|------|---------|------|------|
| GNU Make | 4.x（Ubuntu 22.04 内置） | 统一操作入口（`Makefile`） | `build-essential` 包含 |
| Bash | 5.1+（Ubuntu 22.04 内置） | 部署脚本实现（`scripts/deploy/*.sh`） | OS 内置 |
| git | 2.x（Ubuntu 22.04 内置） | 代码获取、版本回退 | `apt install git` |

---

## 2. 现有技术栈（保持不变）

以下为现有应用技术栈，物理机部署不改变这些选型，仅改变其运行方式（从容器内运行到宿主机运行）。

### 2.1 应用层（物理机部署时在宿主机 venv 中运行）

| 技术 | 版本 | 运行方式变更 |
|------|------|------------|
| Django 4.2 LTS | 无变更 | 容器内 → `venv/bin/gunicorn` 在宿主机运行 |
| Gunicorn + Uvicorn Worker | 无变更 | 容器内 → 宿主机进程（systemd 管理） |
| Celery 5.x | 无变更 | 容器内 → 宿主机进程（systemd 管理） |
| sentence-transformers + bge-small-zh-v1.5 | 无变更 | 容器内预下载 → 宿主机首次运行时下载（HF_ENDPOINT 配置） |

### 2.2 Docker 部署（保留，不变）

| 技术 | 说明 |
|------|------|
| Docker Engine | 保留现有 docker-compose.yml，不做任何修改 |
| Docker Compose V2 | `make deploy-docker` 调用，与当前生产环境完全一致 |
| GHCR 镜像仓库 | ghcr.io/yangyang198354-haha/genplatform/* 继续使用 |

---

## 3. 操作系统支持矩阵

| OS | 版本 | systemd | apt 包 | 支持级别 |
|----|------|---------|--------|---------|
| Ubuntu | 22.04 LTS | 249 | PostgreSQL 15 PGDG / Redis 7 可用 | 完全支持（首选） |
| Debian | 12 (Bookworm) | 252 | PostgreSQL 15 PGDG / Redis 7 可用 | 完全支持 |
| CentOS Stream | 9 | 252 | 需 PostgreSQL PGDG rpm，Redis 通过 remi repo | 部分支持（需 Supervisor 降级方案） |
| Ubuntu | 20.04 LTS | 245 | PostgreSQL 15 PGDG 可用，Python 3.12 需 deadsnakes PPA | 有限支持 |

**推荐**：Ubuntu 22.04 LTS，与 Dockerfile 的 `python:3.11-slim`（基于 Debian Bookworm）生态完全对应，依赖包版本最接近。

---

## 4. 外部服务依赖（物理机部署新增）

| 服务/资源 | 用途 | 网络要求 |
|----------|------|---------|
| apt.postgresql.org | 安装 PostgreSQL 15 + pgvector | 仅首次 setup 需要访问 |
| hf-mirror.com | 下载嵌入模型（BAAI/bge-small-zh-v1.5） | 首次 Worker 启动时需要（GFW 内服务器使用此镜像） |
| PyPI (pypi.org) | Python 包安装 | 部署时需要访问（或使用 PyPI 镜像） |
| download.pytorch.org/whl/cpu | PyTorch CPU-only 包 | 首次部署时需要（或预先缓存） |
| NodeSource (deb.nodesource.com) | 安装 Node.js 20 | 仅首次 setup 需要 |

---

## 5. 版本锁定策略

| 组件 | 锁定方式 | 说明 |
|------|---------|------|
| Python 依赖 | `requirements.txt`（现有，含版本钉） | 不变 |
| 前端依赖 | `package-lock.json`（`npm ci` 严格安装） | 不变 |
| 系统包 | `setup_system.sh` 中明确指定版本号（如 `postgresql-15`） | 避免 apt 升级到不兼容版本 |
| PyTorch（物理机） | `pip install "torch==2.3.1+cpu"` — 与 Dockerfile 保持一致 | 确保 CPU-only 包体积可控 |
| 嵌入模型 | `EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`（从 `.env` 读取） | 与 Docker 部署保持一致 |
