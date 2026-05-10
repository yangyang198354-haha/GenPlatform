<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-05-10T00:15:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>1.0.0</version>
  <phase>PARTIAL_FLOW / GROUP_B</phase>
  <status>DRAFT</status>
  <input_files>
    <file>docs/deployment/requirements_spec.md (DRAFT)</file>
    <file>docs/deployment/architecture_design.md (DRAFT)</file>
  </input_files>
  <scope>部署工具链模块设计</scope>
</file_header>

# 模块设计 — 部署工具链

## 模块概览图

```
项目根目录/
├── Makefile                        ← MOD-DEPLOY-001：统一操作入口
├── scripts/
│   ├── deploy/
│   │   ├── setup_system.sh         ← MOD-DEPLOY-002：系统依赖安装
│   │   ├── deploy_physical.sh      ← MOD-DEPLOY-003：物理机部署主流程
│   │   ├── deploy_docker.sh        ← MOD-DEPLOY-004：Docker 部署入口
│   │   ├── update_physical.sh      ← MOD-DEPLOY-005：物理机增量更新
│   │   ├── rollback_physical.sh    ← MOD-DEPLOY-006：物理机回滚
│   │   ├── rollback_docker.sh      ← MOD-DEPLOY-007：Docker 回滚
│   │   ├── validate_config.sh      ← MOD-DEPLOY-008：配置校验
│   │   └── smoke_test.sh           ← MOD-DEPLOY-009：冒烟测试
│   └── lib/
│       └── common.sh               ← MOD-DEPLOY-010：公共函数库
├── config/
│   └── deploy/
│       ├── systemd/
│       │   ├── genplatform-backend.service   ← systemd 服务单元文件
│       │   ├── genplatform-celery.service
│       │   └── genplatform-beat.service
│       ├── supervisor/                        ← 降级方案（Supervisor）
│       │   ├── genplatform.conf
│       │   └── README.md
│       └── nginx/
│           ├── nginx-physical.conf            ← 物理机模式 Nginx 配置
│           └── nginx-docker.conf              ← 现有 Docker 模式（src/nginx/nginx.conf 的符号链接或副本）
└── .env.physical.example           ← 物理机模式环境变量示例（区分 Docker .env.example）
```

**无循环依赖**：所有模块的调用关系为单向（Makefile → 部署脚本 → 公共函数库），无循环。

---

## MOD-DEPLOY-001：Makefile — 统一操作入口

**文件**：`Makefile`（项目根目录）

**职责**：提供所有部署操作的自文档化统一入口，屏蔽脚本路径细节。

**对外接口（Make targets）**：

```makefile
# 初始化与配置
make setup-physical          # 安装系统依赖（首次使用）
make validate-config         # 校验 .env 配置完整性

# 物理机部署
make deploy-physical         # 首次完整物理机部署
make update-physical         # 增量更新（代码已存在时）
make rollback-physical       # 回滚物理机到上次稳定版本
make rollback-physical VERSION=<commit>  # 回滚到指定 commit

# Docker 部署
make deploy-docker           # Docker Compose 方式部署（显式指定）
make rollback-docker TAG=<tag>  # Docker 回滚到指定镜像 tag

# 服务管理
make start-physical          # 启动所有物理机服务
make stop-physical           # 停止所有物理机服务
make restart-physical        # 重启所有物理机服务
make status                  # 查看所有服务运行状态

# 日志
make logs                    # 查看所有服务最近日志
make logs SERVICE=backend    # 查看指定服务日志（backend/celery_worker/celery_beat）
make logs-follow SERVICE=backend  # 实时跟踪指定服务日志

# 测试
make smoke-test              # 执行部署后冒烟测试

# 帮助
make help                    # 输出所有 target 说明
```

**依赖**：调用 `scripts/deploy/` 中的各子脚本，传递环境变量（`DEPLOY_MODE`、`APP_DIR`、`VERSION` 等）。

---

## MOD-DEPLOY-002：setup_system.sh — 系统依赖安装

**文件**：`scripts/deploy/setup_system.sh`

**职责**：在全新服务器上安装所有系统级依赖，幂等执行。

**执行步骤**：
1. 检测 OS 类型（Ubuntu/Debian 处理 apt；CentOS 处理 dnf；不支持的 OS 报错退出）
2. 添加 PostgreSQL 官方 apt 源（PGDG）
3. 安装系统包：`python3.12 python3.12-venv python3.12-dev build-essential libpq-dev postgresql-15 postgresql-15-pgvector redis-server nginx nodejs npm ffmpeg tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng poppler-utils`
4. 确保 PostgreSQL 和 Redis 服务开机自启（`systemctl enable postgresql redis`）
5. 创建部署目录：`/opt/genplatform/{app,venv,staticfiles,media,logs}`
6. 创建系统用户 `genplatform`（无登录权限），设置目录所有者
7. 安装 systemd 服务单元文件（复制 `config/deploy/systemd/*.service` 到 `/etc/systemd/system/`），执行 `systemctl daemon-reload`，`systemctl enable genplatform-backend genplatform-celery genplatform-beat`
8. 安装 Nginx 配置（复制 `config/deploy/nginx/nginx-physical.conf`，测试配置合法性）

**幂等保障**：所有步骤使用 `apt-get install -y`（已安装则跳过）；`systemctl enable`（已启用则无操作）；目录创建使用 `mkdir -p`；systemd 文件复制前先 diff，无变更则跳过。

**输入**：无参数，读取脚本所在目录的相对路径确认项目根目录

**输出**：
- 控制台：每步完成后输出状态（`[OK]` / `[SKIP]` / `[ERROR]`）
- 退出码：0 = 成功，1 = 错误（含错误原因）

---

## MOD-DEPLOY-003：deploy_physical.sh — 物理机部署主流程

**文件**：`scripts/deploy/deploy_physical.sh`

**职责**：完整的物理机首次/重新部署流程，包含代码获取、依赖安装、构建、数据库初始化、服务启动。

**执行步骤**：
1. 调用 `validate_config.sh` — 校验 `.env` 文件（失败则终止）
2. 记录当前 git commit（写入 `/opt/genplatform/.last_deployed_commit`）
3. 同步代码：git clone 或 git pull（依据 `APP_DIR` 是否已存在）
4. Python 虚拟环境：创建或更新 `/opt/genplatform/venv/`
5. 安装 Python 依赖：
   - 安装 PyTorch CPU-only（amd64 使用 PyPI CPU 源，避免 CUDA 包体积膨胀）
   - 安装其余依赖：`venv/bin/pip install -r requirements.txt`
6. 前端构建：
   - `cd src/frontend && npm ci && npm run build`
   - 复制 `dist/` 到 `/opt/genplatform/staticfiles/`
7. Django 准备：
   - `venv/bin/python manage.py migrate`
   - `venv/bin/python manage.py collectstatic --noinput`
8. PostgreSQL 初始化：
   - 创建数据库用户和数据库（若不存在）
   - 在目标 DB 中启用 pgvector 扩展：`CREATE EXTENSION IF NOT EXISTS vector;`
9. 预热嵌入模型（与 Docker compose 中的 pre-warm 逻辑等效）：
   - `HF_ENDPOINT=... venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"`
   - 失败时打印警告但不中止部署（Worker 首次启动时会重试下载）
10. 启动所有服务：`systemctl start genplatform-backend genplatform-celery genplatform-beat`
11. 重启 Nginx：`systemctl reload nginx`
12. 执行冒烟测试：调用 `smoke_test.sh`

**失败处理**：每步检查退出码，失败时输出具体错误，提示运维人员执行 `make rollback-physical`。

**输入**：读取当前目录的 `.env` 文件；`APP_DIR`（默认 `/opt/genplatform`）

**输出**：退出码 0 = 成功，非 0 = 失败

---

## MOD-DEPLOY-004：deploy_docker.sh — Docker 部署入口

**文件**：`scripts/deploy/deploy_docker.sh`

**职责**：作为 `make deploy-docker` 的实现，调用现有 `docker-compose.yml`，加入端口冲突检测。

**执行步骤**：
1. 检测是否安装了 Docker 和 Docker Compose V2（`docker compose version`）
2. 检测端口 80 是否被非 Docker 进程占用（避免物理机 Nginx 冲突）
3. 调用 `validate_config.sh` — 校验 `.env` 文件
4. `docker compose pull` — 拉取最新镜像
5. `docker compose up -d` — 启动所有容器
6. 等待 healthcheck 全部 healthy（最多 120 秒）
7. 执行冒烟测试：调用 `smoke_test.sh`

**输入**：`.env`；`COMPOSE_FILE`（默认 `src/docker-compose.yml`）

**输出**：退出码 0 = 成功，非 0 = 失败

---

## MOD-DEPLOY-005：update_physical.sh — 物理机增量更新

**文件**：`scripts/deploy/update_physical.sh`

**职责**：在已部署的物理机上执行增量更新，最小化停机时间。

**执行步骤**：
1. 记录当前 git commit（写入 `.last_deployed_commit`，覆盖）
2. `git pull origin main`（或指定分支）
3. 检测 `requirements.txt` 是否有变更（对比 git diff）：
   - 有变更：`venv/bin/pip install -r requirements.txt`
   - 无变更：跳过（输出 `[SKIP] pip install`）
4. 检测前端代码是否有变更（`src/frontend/` 目录）：
   - 有变更：`npm ci && npm run build`，覆盖 `staticfiles/`
   - 无变更：跳过
5. `venv/bin/python manage.py migrate`（无待迁移时快速完成，幂等）
6. `venv/bin/python manage.py collectstatic --noinput`
7. Gunicorn graceful reload：`systemctl reload genplatform-backend`（发送 HUP 信号，零停机）
8. Celery warm shutdown + restart：
   - `systemctl stop genplatform-celery`（Celery 默认 warm shutdown，已接受任务执行完成后退出）
   - `systemctl start genplatform-celery`
9. `systemctl restart genplatform-beat`
10. `systemctl reload nginx`
11. 冒烟测试

**零停机目标**：Gunicorn 使用 graceful reload（`--timeout 120`，与 Dockerfile 一致），Celery worker 使用 warm shutdown（已接受的任务不丢失，基于 `acks_late=True` 和 Celery 的 SIGTERM 处理）。

**输入**：`.env`；`BRANCH`（默认 `main`）

---

## MOD-DEPLOY-006：rollback_physical.sh — 物理机回滚

**文件**：`scripts/deploy/rollback_physical.sh`

**职责**：将物理机应用回滚到指定 git commit 版本。

**参数**：`VERSION`（可选，默认读取 `.last_deployed_commit`）

**执行步骤**：
1. 确认 `VERSION`（若未提供则从 `.last_deployed_commit` 读取）
2. `git checkout <VERSION>` — 回退代码
3. 重新安装依赖（依据该版本的 `requirements.txt`）
4. `venv/bin/python manage.py migrate`（回退不自动执行 down migration，需人工确认）
5. 重新构建前端（若该版本前端代码与当前不同）
6. `venv/bin/python manage.py collectstatic --noinput`
7. 重启所有服务
8. 冒烟测试

**注意**：database migration 回滚（down migration）不自动执行，脚本会输出提示："如果回滚的版本删除了数据库字段，需要人工执行 `python manage.py migrate <app> <migration_number>`"。

---

## MOD-DEPLOY-007：rollback_docker.sh — Docker 回滚

**文件**：`scripts/deploy/rollback_docker.sh`

**职责**：Docker 部署的镜像版本回滚。

**参数**：`TAG`（必须，目标镜像 tag，如 `sha-abc1234`）

**执行步骤**：
1. 修改环境变量（临时覆盖）：`BACKEND_IMAGE_TAG=<TAG> FRONTEND_IMAGE_TAG=<TAG>`
2. `docker compose pull` — 拉取指定 tag 镜像
3. `docker compose up -d` — 重启服务（无 migrate 回滚）
4. 等待 healthcheck
5. 冒烟测试

---

## MOD-DEPLOY-008：validate_config.sh — 配置校验

**文件**：`scripts/deploy/validate_config.sh`

**职责**：校验 `.env` 文件是否包含所有必填变量，并检测常见配置错误。

**必填变量清单**：
```
DJANGO_SECRET_KEY          # 非空，长度 >= 50
ENCRYPTION_KEY             # 非空，base64 格式
POSTGRES_PASSWORD          # 非空
POSTGRES_DB                # 非空（默认 content_gen_platform）
ALLOWED_HOSTS              # 非空
CORS_ALLOWED_ORIGINS       # 非空
REDIS_URL                  # 非空（物理机时应为 redis://localhost:6379/0）
```

**检测规则**：
1. 变量存在性检查：逐一检查上述变量是否在 `.env` 中定义且非空
2. 长度检查：`DJANGO_SECRET_KEY` 长度 >= 50 字符
3. Docker/物理机连接地址一致性警告：
   - 检测到 `DATABASE_URL` 含 `@db:` 或 `REDIS_URL` 含 `redis://redis:` → 输出警告（物理机部署时应改为 localhost）
   - 检测到 `DJANGO_SECRET_KEY=change-me` 或包含默认示例值 → 输出错误并退出 1
4. 敏感变量掩码：输出时将 `DJANGO_SECRET_KEY`、`ENCRYPTION_KEY`、`POSTGRES_PASSWORD` 显示为 `****`

**输出**：
- 成功：`[OK] 配置校验通过，共检查 N 个变量`
- 警告：`[WARN] DATABASE_URL 中检测到 Docker 服务名 (@db:)，物理机部署时请修改为 localhost 或实际 IP`
- 错误：`[ERROR] 缺少必填变量：ENCRYPTION_KEY`，退出码 1

---

## MOD-DEPLOY-009：smoke_test.sh — 冒烟测试

**文件**：`scripts/deploy/smoke_test.sh`

**职责**：部署完成后执行最小化的可用性验证，作为部署成功的门控。

**测试步骤**（最多等待 60 秒）：
1. `GET /api/v1/auth/login/` — 期望返回非 500 状态码（Django 正常响应）
2. `GET /` — 期望返回包含 `<!DOCTYPE html>` 的 HTML（前端静态文件服务正常）
3. Celery Worker 活跃检查：
   - 物理机：`systemctl is-active genplatform-celery` 返回 `active`
   - Docker：`docker compose exec celery_worker celery -A config inspect active`
4. 数据库连接检查：`venv/bin/python manage.py check --database default`（物理机）

**输出**：
- 每步输出 `[PASS]` 或 `[FAIL]` 及响应详情
- 所有 PASS → 退出码 0，任一 FAIL → 退出码 1

---

## MOD-DEPLOY-010：common.sh — 公共函数库

**文件**：`scripts/lib/common.sh`

**职责**：提供所有脚本共用的函数，通过 `source scripts/lib/common.sh` 引入。

**函数清单**：
```bash
log_info  "<message>"     # 输出带时间戳的信息行
log_warn  "<message>"     # 输出带时间戳的警告行（黄色）
log_error "<message>"     # 输出带时间戳的错误行（红色）
check_command "<cmd>"     # 检查命令是否存在，不存在则 log_error + exit 1
load_env  "<path>"        # 加载 .env 文件（export 所有变量）
wait_for_port "<host>" "<port>" "<timeout>"  # 等待端口可用
get_git_commit            # 返回当前 git commit hash（短格式）
confirm_action "<message>"  # 显示确认提示，等待用户输入 yes/no
```

---

## systemd 服务单元文件设计

### genplatform-backend.service

```ini
[Unit]
Description=GenPlatform Django ASGI Backend
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=notify
User=genplatform
Group=genplatform
WorkingDirectory=/opt/genplatform/app/src/backend
EnvironmentFile=/opt/genplatform/.env
ExecStart=/opt/genplatform/venv/bin/gunicorn \
    config.asgi:application \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 4 \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --log-file /opt/genplatform/logs/gunicorn.log \
    --access-logfile /opt/genplatform/logs/gunicorn-access.log
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
Restart=always
RestartSec=5
StartLimitBurst=3
StartLimitInterval=60s

[Install]
WantedBy=multi-user.target
```

### genplatform-celery.service

```ini
[Unit]
Description=GenPlatform Celery Worker
After=network.target postgresql.service redis.service genplatform-backend.service

[Service]
Type=forking
User=genplatform
Group=genplatform
WorkingDirectory=/opt/genplatform/app/src/backend
EnvironmentFile=/opt/genplatform/.env
Environment=HF_ENDPOINT=https://hf-mirror.com
Environment=HF_HUB_DISABLE_PROGRESS_BARS=1
ExecStart=/opt/genplatform/venv/bin/celery \
    -A config worker \
    -l info \
    -Q default,video,publish \
    -c 2 \
    --logfile /opt/genplatform/logs/celery-worker.log \
    --pidfile /run/genplatform/celery-worker.pid \
    --detach
ExecStop=/bin/sh -c '/opt/genplatform/venv/bin/celery -A config control shutdown'
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=10
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

**TimeoutStartSec=300**：嵌入模型首次下载最多 5 分钟，避免 systemd 因启动超时 kill Worker 进程（对应 REQ-DEPLOY-FUNC-010）。

### genplatform-beat.service

```ini
[Unit]
Description=GenPlatform Celery Beat Scheduler
After=network.target postgresql.service redis.service genplatform-backend.service

[Service]
Type=simple
User=genplatform
Group=genplatform
WorkingDirectory=/opt/genplatform/app/src/backend
EnvironmentFile=/opt/genplatform/.env
ExecStart=/opt/genplatform/venv/bin/celery \
    -A config beat \
    -l info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --logfile /opt/genplatform/logs/celery-beat.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Nginx 物理机配置设计（nginx-physical.conf）

```nginx
server {
    listen 80;
    server_name _;
    client_max_body_size 100M;

    # API → Django ASGI（本地进程）
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection "";
        chunked_transfer_encoding on;
    }

    # WebSocket → Django Channels
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
    }

    # Admin → backend
    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 媒体文件（用户上传）
    location /media/ {
        alias /opt/genplatform/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # 静态文件（Django collectstatic + Vue3 构建产物）
    location /static/ {
        alias /opt/genplatform/staticfiles/static/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # Vue3 SPA — 直接服务构建产物，history mode fallback
    location / {
        root /opt/genplatform/staticfiles;
        try_files $uri $uri/ /index.html;
        expires -1;
        add_header Cache-Control "no-store";
    }
}
```

**关键差异（对比 Docker 版 nginx.conf）**：
- `proxy_pass http://127.0.0.1:8000`（物理机）替代 `http://backend`（Docker DNS）
- `location /` 直接 `root` 服务静态文件，替代 `proxy_pass http://frontend:80`（无 frontend 容器）
- 增加 `/static/` location（Django collectstatic 产物）
