<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-05-10T00:10:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>1.0.0</version>
  <phase>PARTIAL_FLOW / GROUP_B</phase>
  <status>DRAFT</status>
  <input_files>
    <file>docs/deployment/requirements_spec.md (DRAFT)</file>
    <file>docs/deployment/user_stories.md (DRAFT)</file>
    <file>src/docker-compose.yml (APPROVED)</file>
    <file>architecture/architecture_design.md (APPROVED)</file>
    <file>src/backend/Dockerfile (APPROVED)</file>
  </input_files>
  <scope>物理机部署架构决策记录</scope>
</file_header>

# 架构决策记录 — 物理机部署方式扩展

---

## ADR-DEPLOY-001：进程管理工具选型

**决策点**：物理机部署时，用什么工具管理 Django ASGI、Celery Worker、Celery Beat 进程？

### 选项 A — systemd（Linux 原生服务管理）

**描述**：为每个进程编写 `.service` unit 文件，由 systemd 托管。

**优势**：
- Linux 标准，Ubuntu/Debian/CentOS 均内置，无需额外安装
- 自动开机启动（`systemctl enable`）
- journald 统一日志，`journalctl -u genplatform-backend` 即可查看
- 支持依赖声明（`After=postgresql.service redis.service`），确保启动顺序
- `systemctl status` 输出标准化，易于脚本集成
- 支持资源限制（CPU/内存 cgroup）

**劣势**：
- 需要 root 权限配置 `/etc/systemd/system/` 目录
- 修改 `.service` 文件后需 `systemctl daemon-reload`，稍显繁琐
- 不同发行版的 systemd 版本有细微差异

**适用场景**：Ubuntu 22.04 / Debian 12 生产服务器，运维工程师有 sudo 权限

---

### 选项 B — Supervisor

**描述**：安装 `supervisord`，编写 `.conf` 文件管理进程。

**优势**：
- 独立安装，不依赖 OS 版本
- Web UI（supervisorctl web）方便直观管理
- 支持进程分组，一条命令管理多个相关进程
- 非 root 用户也可以运行（supervisor 本身以特定用户启动）

**劣势**：
- 额外依赖（pip install supervisor），需单独安装和配置
- 自身需要另一个进程管理工具（如 systemd）来保证其开机自启
- 日志在 `/var/log/supervisor/` 下，与系统日志分离
- 社区活跃度下降（相比 systemd 原生方案）

**适用场景**：需要在非标准 Linux 环境或无 root 权限场景下运行

---

### 选项 C — 纯 Shell 脚本（tmux/screen/nohup）

**描述**：使用 `nohup` 或 `tmux` 在后台运行进程，不使用服务管理工具。

**优势**：零额外依赖

**劣势**：无崩溃重启、无开机自启、无标准状态查看接口，生产环境不可接受

**排除**：不适合生产部署，排除。

---

**选择：选项 A — systemd（主选）+ 选项 B — Supervisor（降级备选）**

**理由**：
- 目标 OS 为 Ubuntu 22.04 / Debian 12，systemd 为原生组件，零额外依赖，开机自启可靠
- systemd 的依赖声明机制（`After=postgresql.service redis.service`）天然满足 REQ-DEPLOY-FUNC-005 的启动顺序要求
- journald 日志与 `make logs SERVICE=backend` 的实现（`journalctl -u genplatform-backend -n 100 -f`）完美结合
- 提供 Supervisor 配置作为降级方案，满足 CentOS Stream 9 或无 root 权限环境

---

## ADR-DEPLOY-002：Python 虚拟环境管理策略

**决策点**：物理机部署时，如何隔离 Python 依赖？

### 选项 A — venv（Python 标准库）

**描述**：`python3.12 -m venv /opt/genplatform/venv`，部署目录 `/opt/genplatform/`。

**优势**：Python 内置，无额外安装；操作简单直观；完全隔离系统 Python

**劣势**：版本切换不如 pyenv 灵活（但该项目 Python 版本固定为 3.12，无需灵活切换）

---

### 选项 B — conda/miniconda

**描述**：使用 conda 管理 Python 版本和依赖。

**优势**：同时管理 Python 版本和系统库（如 BLAS）

**劣势**：安装包体积大（300MB+）；对于已知 Python 版本的生产部署过于重量级；与 pip requirements.txt 的兼容性有时有摩擦

---

### 选项 C — pyenv + venv

**描述**：使用 pyenv 管理多个 Python 版本，再创建 venv。

**优势**：精确控制 Python 版本

**劣势**：安装链（git clone pyenv → shell 初始化 → python build）增加部署脚本复杂度；apt 安装的 Python 3.12 对该项目已经足够

---

**选择：选项 A — venv**

**理由**：Python 版本固定为 3.12，Ubuntu 22.04 的 `python3.12` 包可直接 apt 安装，venv 满足隔离需求；轻量、无额外依赖、脚本化最简单，符合 REQ-DEPLOY-NFUNC-001（幂等性）要求。

**部署路径约定**：
```
/opt/genplatform/
├── app/              # git clone 或 rsync 的应用代码
├── venv/             # Python 虚拟环境
├── media/            # 用户上传文件
├── staticfiles/      # collectstatic 输出
├── logs/             # 应用日志
└── .env              # 环境变量（mode 600）
```

---

## ADR-DEPLOY-003：前端构建与静态文件服务策略

**决策点**：物理机部署时，前端如何构建和服务？

### 选项 A — 部署时 npm build，Nginx 直接服务构建产物

**描述**：在目标服务器上执行 `npm ci && npm run build`，将 `dist/` 目录配置为 Nginx 的 `root`，Nginx 直接服务静态文件。

**优势**：
- 无需额外的前端进程（现有 Docker 方案中 frontend 容器承担的 Nginx 功能合并到主 Nginx）
- 静态文件直接由 Nginx 服务，性能最优（无 proxy_pass 中间环节）
- 构建产物直接在宿主机，方便问题排查

**劣势**：
- 目标服务器需要安装 Node.js（构建时依赖）
- 每次前端有变更时需在服务器上重新 build
- Node.js 安装增加服务器依赖

---

### 选项 B — CI 构建前端，只上传 dist/ 目录

**描述**：在 GitHub Actions 中构建前端，将 `dist/` 目录打包上传到服务器（rsync/scp），服务器不需要安装 Node.js。

**优势**：
- 服务器不需要 Node.js，依赖更轻
- 构建在 CI 环境执行，与本地环境无关
- 构建产物版本与 git commit 对应，可追溯

**劣势**：
- 需要 CI 配置配合（增加 rsync 步骤），改造范围稍大
- 手动部署时需要单独处理 dist/ 来源

---

### 选项 C — 保留 frontend Docker 容器，只用物理机部署后端

**描述**：只对后端、Celery、数据库做物理机部署，前端依然跑在 Docker 中。

**优势**：前端部署改动最小

**劣势**：混合模式增加了部署复杂度，运维需要同时管理物理进程和容器，概念不统一；违背"物理部署即直接在宿主机"的目标

---

**选择：选项 A 作为首选（标准物理机部署），选项 B 作为 CI 集成优化路径**

**理由**：
- 物理机部署的核心价值是"简单直接"，选项 A 完全自包含，一条 `make deploy-physical` 命令完成从代码到服务；
- 选项 B 作为进阶优化：在 CI 已集成后，由 GitHub Actions 构建前端并 rsync 到服务器，服务器可不安装 Node.js；
- 选项 C 的混合模式增加认知负担，明确排除。

**Nginx 配置变更**：物理机模式下的 Nginx 配置与 Docker 模式不同：
- Docker 模式：`proxy_pass http://frontend:80`（代理到 frontend 容器）
- 物理机模式：`root /opt/genplatform/staticfiles; try_files $uri /index.html;`（直接服务静态文件）
- 两套 nginx.conf 分别维护（`nginx/nginx.conf`=Docker 版，`nginx/nginx-physical.conf`=物理机版）

---

## ADR-DEPLOY-004：PostgreSQL 安装与 pgvector 扩展策略

**决策点**：物理机部署时，如何安装 PostgreSQL 15+ 和 pgvector 扩展？

### 选项 A — apt 安装官方 PostgreSQL + 独立编译 pgvector

**描述**：通过 PostgreSQL 官方 apt 源安装 PostgreSQL 15，从源码编译安装 pgvector（`make && make install`）。

**优势**：版本精确可控，pgvector 安装最新版

**劣势**：编译 pgvector 需要 build-essential、postgresql-server-dev，步骤较多，脚本复杂度增加

---

### 选项 B — apt 安装 postgresql-15-pgvector

**描述**：Ubuntu 22.04 的 apt 源中已有 `postgresql-15-pgvector` 包（PGDG 官方源），一条命令安装。

**优势**：最简单，与 apt 包管理一致，版本经过验证

**劣势**：PGDG 源中 pgvector 版本可能落后于最新版（通常落后 1-2 个小版本，不影响功能）

---

### 选项 C — 使用 Docker 只运行 PostgreSQL，其他服务物理部署

**描述**：PostgreSQL 用 pgvector 官方镜像运行，其余服务物理部署。

**优势**：避免 pgvector 编译问题

**劣势**：混合模式，概念不统一（排除，同 ADR-DEPLOY-003 选项 C 的理由）

---

**选择：选项 B — apt 安装 postgresql-15-pgvector（PGDG 源）**

**理由**：PGDG 官方源（`apt.postgresql.org`）提供的 pgvector 包版本（通常 0.6+）满足项目需求（512/1024 维向量存储），安装最简单，满足 REQ-DEPLOY-NFUNC-001（幂等性）；`apt install` 是幂等操作，重复执行不报错。

---

## ADR-DEPLOY-005：部署工具链统一入口

**决策点**：用什么作为物理机和 Docker 两种部署方式的统一操作入口？

### 选项 A — Makefile

**描述**：用 GNU Make 提供统一的 target，如 `make deploy-physical`、`make deploy-docker`、`make status`、`make rollback-physical`。

**优势**：
- 无额外依赖（GNU Make 在 Ubuntu 中极广泛，`build-essential` 即包含）
- 语法简单，Shell 脚本可内嵌
- `make help` 可自动列出所有可用命令
- 与现有开发习惯（`make test`、`make lint`）一致

**劣势**：
- Makefile 语法对不熟悉的人有一定学习曲线
- 复杂逻辑难以在 Makefile 中维护，需要拆分到 `scripts/` 子脚本

---

### 选项 B — Ansible Playbook

**描述**：编写 Ansible Playbook，通过 `ansible-playbook deploy.yml -e mode=physical` 执行。

**优势**：
- 声明式，可描述服务器期望状态
- 支持多服务器批量部署
- 内置幂等性（Ansible 模块天然幂等）
- 支持 Vault 加密敏感配置

**劣势**：
- 需要额外安装 Ansible（`pip install ansible`），增加依赖
- 对于单服务器部署，Ansible 的复杂度远超需求
- 需要 SSH 密钥配置和 inventory 文件，对简单部署场景增加入门门槛
- Ansible 控制节点与目标节点的概念对运维工程师有额外认知成本

---

### 选项 C — Shell 脚本集合（deploy.sh、update.sh 等）

**描述**：每个操作对应一个 `.sh` 脚本文件。

**优势**：最直观，无额外依赖

**劣势**：无统一入口，命令分散，难以提供 `help`；脚本间依赖关系需人工维护；不如 Makefile 统一

---

**选择：选项 A — Makefile（作为统一入口）+ `scripts/` 子脚本（实现复杂逻辑）**

**理由**：
- Makefile 提供统一的自文档化入口（`make help`），符合 REQ-DEPLOY-NFUNC-002（文档完整性）
- 对于当前单服务器部署场景，Ansible 的复杂度远超所需（排除选项 B）
- 复杂操作（如 pgvector 安装验证、rollback 逻辑）抽取到 `scripts/` 目录的 Shell 脚本中，Makefile 仅作为入口调用
- 若未来需要多服务器批量部署，可在 Makefile 之上增加 Ansible 层，不需要废弃现有接口

---

## 物理机部署架构总览

```
宿主机 (Ubuntu 22.04)
├── /opt/genplatform/
│   ├── app/                    ← git clone 的应用代码
│   │   ├── src/backend/        ← Django 应用
│   │   └── src/frontend/       ← Vue3 源码（构建后产物在 staticfiles/）
│   ├── venv/                   ← Python 3.12 虚拟环境
│   ├── staticfiles/            ← collectstatic + npm build 产物
│   ├── media/                  ← 用户上传文件
│   ├── logs/                   ← 应用日志（gunicorn、celery）
│   └── .env                    ← 环境变量（mode 600）
│
├── 系统服务（systemd）
│   ├── postgresql.service      ← 系统 PostgreSQL 15+pgvector
│   ├── redis.service           ← 系统 Redis 7
│   ├── genplatform-backend.service   ← Gunicorn ASGI
│   ├── genplatform-celery.service    ← Celery Worker
│   └── genplatform-beat.service      ← Celery Beat
│
└── Nginx
    ├── /etc/nginx/sites-available/genplatform  ← 物理机专用 nginx 配置
    └── 直接服务 /opt/genplatform/staticfiles/  ← Vue3 构建产物

对比：Docker 部署（保留不变）
└── docker-compose.yml          ← 6个容器：db/redis/backend/celery_worker/celery_beat/frontend/nginx
    ├── frontend 容器 (nginx:alpine)  ← 服务前端静态文件
    └── nginx 容器 (nginx:alpine)     ← 反向代理，proxy_pass 到 frontend/backend 容器
```

---

## 两种部署方式对比矩阵

| 维度 | 物理机部署 | Docker 部署 |
|------|-----------|------------|
| 发布速度 | 快（git pull + 重启，60s 内） | 慢（build + push + pull 镜像，5-15min） |
| 依赖隔离 | 通过 venv 隔离 Python；OS 级依赖直接安装 | 完全容器隔离 |
| 进程管理 | systemd（内置） | Docker Compose |
| 日志 | journald / 文件日志 | `docker compose logs` |
| 水平扩展 | 手动（需要 LB 配置） | docker compose scale |
| 资源开销 | 低（无容器层） | 略高（容器运行时） |
| 环境复现 | 依赖脚本精确性 | 镜像保证完全复现 |
| 适用场景 | 日常快速发布、单机生产 | 新服务器快速启动、CI/CD 标准化 |
| 默认路径 | 是（`make deploy-physical`） | 否（`make deploy-docker`，显式指定） |
