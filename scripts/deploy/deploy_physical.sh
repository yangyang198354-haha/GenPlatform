#!/usr/bin/env bash
# scripts/deploy/deploy_physical.sh — 物理机完整部署 (MOD-DEPLOY-003)
# 用法: bash scripts/deploy/deploy_physical.sh
# 前置条件: sudo bash scripts/deploy/setup_system.sh 已执行完毕
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

APP_DIR="${APP_DIR:-/opt/genplatform}"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
APP_CODE_DIR="$APP_DIR/app"
VENV_DIR="$APP_DIR/venv"
BACKEND_DIR="$APP_CODE_DIR/project_workspace/content_gen_platform/src/backend"
FRONTEND_DIR="$APP_CODE_DIR/project_workspace/content_gen_platform/src/frontend"
STATIC_DIR="$APP_DIR/staticfiles"

log_info "===== GenPlatform 物理机首次部署 ====="
log_info "部署目录: $APP_DIR"
log_info "分支:     $BRANCH"

# ── 步骤 1: 配置校验 ──────────────────────────────────────────────────────────
log_info "--- 步骤 1/12: 校验 .env 配置 ---"
# .env 由 GitHub Actions workflow 生成在 $APP_DIR/app/.env（即 $PROJECT_ROOT/.env）
# systemd 服务的 EnvironmentFile 指向 $APP_DIR/.env，需要创建软链接保持一致
ENV_APP="$PROJECT_ROOT/.env"
ENV_SYSTEMD="$APP_DIR/.env"
if [[ ! -f "$ENV_APP" ]]; then
    # 如果 app 目录下没有 .env，检查 systemd 路径是否有（首次手动部署场景）
    if [[ -f "$ENV_SYSTEMD" ]] && [[ "$ENV_APP" != "$ENV_SYSTEMD" ]]; then
        log_warn "[WARN] $ENV_APP 不存在，使用 $ENV_SYSTEMD"
        cp "$ENV_SYSTEMD" "$ENV_APP"
    fi
fi
bash "$SCRIPT_DIR/validate_config.sh" "$ENV_APP"

# 确保 systemd EnvironmentFile 路径（$APP_DIR/.env）可被各服务读取
# systemd 服务以 genplatform 用户运行；.env 所有者由 setup_system.sh 的
# chown -R genplatform:genplatform 保证，chmod 600 对所有者可读写即可
if [[ "$ENV_APP" != "$ENV_SYSTEMD" ]]; then
    # 创建软链接：/opt/genplatform/.env -> /opt/genplatform/app/.env
    ln -sf "$ENV_APP" "$ENV_SYSTEMD" 2>/dev/null || \
        cp "$ENV_APP" "$ENV_SYSTEMD"
    log_info "[OK] $ENV_SYSTEMD -> $ENV_APP (systemd EnvironmentFile 已就位)"
fi

# 加载环境变量
load_env "$ENV_APP"

# ── 步骤 2: 记录当前 commit ───────────────────────────────────────────────────
log_info "--- 步骤 2/12: 记录部署时间和 commit ---"
DEPLOY_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
CURRENT_COMMIT="$(get_git_commit)"
echo "$CURRENT_COMMIT" > "$APP_DIR/.last_deployed_commit"
log_info "当前 commit: $CURRENT_COMMIT"

# ── 步骤 3: 同步代码 ──────────────────────────────────────────────────────────
log_info "--- 步骤 3/12: 同步代码到 $APP_CODE_DIR ---"
if [[ "${SKIP_CODE_SYNC:-}" == "1" ]]; then
    log_info "[SKIP] 代码同步已跳过（SKIP_CODE_SYNC=1，代码由外部工具（scp/rsync）同步）"
elif [[ -d "$APP_CODE_DIR/.git" ]]; then
    log_info "检测到已有代码目录，执行 git pull..."
    git -C "$APP_CODE_DIR" fetch origin
    git -C "$APP_CODE_DIR" checkout "$BRANCH"
    git -C "$APP_CODE_DIR" pull origin "$BRANCH"
    log_info "[OK] git pull 完成"
elif [[ -n "$REPO_URL" ]]; then
    log_info "执行 git clone $REPO_URL..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_CODE_DIR"
    log_info "[OK] git clone 完成"
else
    # 部署脚本在项目根目录内运行时（本地部署），直接 rsync
    log_info "REPO_URL 未设置，使用当前项目目录作为源..."
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='node_modules' \
        "$PROJECT_ROOT/" "$APP_CODE_DIR/"
    log_info "[OK] 本地文件同步完成"
fi

# ── 步骤 4: Python 虚拟环境 ───────────────────────────────────────────────────
log_info "--- 步骤 4/12: 创建/更新 Python 虚拟环境 ---"
# 优先使用 python3.12，降级顺序：3.11 → 3.10 → 3.9 → python3
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3.9; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [[ -z "$PYTHON_BIN" ]]; then
    log_error "未找到可用的 Python 3.9+ 解释器（PyTorch 2.x 最低要求 Python 3.9）"
    log_error "请运行 setup_system.sh 安装 Python 3.11，或手动安装 python3.9/3.11/3.12"
    exit 1
fi
PYTHON_VERSION="$($PYTHON_BIN --version 2>&1)"
if [[ "$PYTHON_BIN" == "python3.12" ]]; then
    log_info "[OK] 使用 $PYTHON_BIN ($PYTHON_VERSION)"
else
    log_warn "[WARN] python3.12 不可用，使用 $PYTHON_BIN ($PYTHON_VERSION)"
    log_warn "       如依赖 Python 3.12 特性，请升级服务器 Python 版本"
fi

# 如果 venv 存在但 Python 版本不匹配，自动重建（避免用旧版 pip 安装新版包）
if [[ -f "$VENV_DIR/bin/python" ]]; then
    EXISTING_VER="$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')"
    EXPECTED_VER="$("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')"
    if [[ "$EXISTING_VER" != "$EXPECTED_VER" ]]; then
        log_warn "[WARN] venv Python 版本不匹配（现有: $EXISTING_VER，期望: $EXPECTED_VER），重建 venv..."
        rm -rf "$VENV_DIR"
    fi
fi

if [[ ! -f "$VENV_DIR/bin/python" ]]; then
    log_info "创建 venv: $VENV_DIR (使用 $PYTHON_BIN)..."
    # 诊断信息：解析真实 python 路径（alinux3 上可能是 wrapper）
    REAL_PYTHON="$(realpath "$(command -v "$PYTHON_BIN")" 2>/dev/null || echo "$PYTHON_BIN")"
    log_info "  $PYTHON_BIN 真实路径: $REAL_PYTHON"

    _try_venv() {
        local mode="$1"; shift
        rm -rf "$VENV_DIR"
        if "$@" 2>&1 && [[ -f "$VENV_DIR/bin/python" ]]; then
            log_info "[OK] venv 创建完成（$mode）"
            return 0
        fi
        return 1
    }

    VENV_OK=false
    # 策略1: 标准 venv
    if ! $VENV_OK && _try_venv "标准模式" "$PYTHON_BIN" -m venv "$VENV_DIR"; then VENV_OK=true; fi
    # 策略2: --without-pip（跳过 ensurepip bootstrap，可能源头是 pip 装失败）
    if ! $VENV_OK && _try_venv "无pip模式" "$PYTHON_BIN" -m venv --without-pip "$VENV_DIR"; then VENV_OK=true; fi
    # 策略3: --without-pip --copies（避开 symlink，对 wrapper 更兼容）
    if ! $VENV_OK && _try_venv "硬拷贝模式" "$PYTHON_BIN" -m venv --without-pip --copies "$VENV_DIR"; then VENV_OK=true; fi
    # 策略4: 用 realpath 解析后的真实 python（绕开 wrapper 脚本）
    if ! $VENV_OK && [[ "$REAL_PYTHON" != "$PYTHON_BIN" ]] && [[ -x "$REAL_PYTHON" ]]; then
        if _try_venv "real-python" "$REAL_PYTHON" -m venv --without-pip --copies "$VENV_DIR"; then VENV_OK=true; fi
    fi
    # 策略5: virtualenv.pyz（独立 zipapp，比 venv 更鲁棒）
    if ! $VENV_OK; then
        log_warn "venv 模块全部失败，尝试 virtualenv.pyz..."
        if curl -fsSL https://bootstrap.pypa.io/virtualenv.pyz -o /tmp/virtualenv.pyz 2>/dev/null; then
            rm -rf "$VENV_DIR"
            if "$PYTHON_BIN" /tmp/virtualenv.pyz "$VENV_DIR" 2>&1 && [[ -f "$VENV_DIR/bin/python" ]]; then
                log_info "[OK] venv 创建完成（virtualenv.pyz）"
                VENV_OK=true
            fi
            rm -f /tmp/virtualenv.pyz
        fi
    fi

    if ! $VENV_OK; then
        log_error "venv 创建失败：所有策略均无法生成 $VENV_DIR/bin/python"
        log_error "请检查 $PYTHON_BIN 安装完整性: $PYTHON_BIN --version, ls $REAL_PYTHON"
        ls -la "$VENV_DIR/bin/" 2>&1 || log_error "venv 目录不存在或为空"
        exit 1
    fi
    log_info "[OK] venv binary 已就位: $VENV_DIR/bin/python (${PYTHON_VERSION})"
else
    log_info "[SKIP] venv 已存在（Python ${EXISTING_VER:-unknown}），跳过创建"
fi

# 确保 pip 在 venv 中可用（源码编译 Python 可能无 SSL，导致 ensurepip/get-pip 失败）
if ! "$VENV_DIR/bin/python" -m pip --version &>/dev/null 2>&1; then
    log_warn "[WARN] venv 中 pip 不可用，尝试安装..."
    # 方案1: ensurepip（不加 --upgrade，使用内嵌 wheel，无需网络/SSL）
    "$VENV_DIR/bin/python" -m ensurepip 2>/dev/null || true
    # 方案2: 从系统 Python 的 site-packages 直接复制 pip 包（源码编译 altinstall 会装 pip）
    if ! "$VENV_DIR/bin/python" -m pip --version &>/dev/null 2>&1; then
        PY_MINOR="${PYTHON_BIN##python}"  # e.g. "3.11"
        SYSTEM_SITE="/usr/local/lib/python${PY_MINOR}/site-packages"
        VENV_SITE="$VENV_DIR/lib/python${PY_MINOR}/site-packages"
        if [[ -d "$SYSTEM_SITE/pip" ]]; then
            log_warn "[WARN] 从系统 Python 复制 pip 包到 venv..."
            cp -r "$SYSTEM_SITE/pip" "$VENV_SITE/" 2>/dev/null || true
            for di in "$SYSTEM_SITE/pip"-*.dist-info "$SYSTEM_SITE/setuptools"-*.dist-info; do
                [[ -d "$di" ]] && cp -r "$di" "$VENV_SITE/" 2>/dev/null || true
            done
            cp -r "$SYSTEM_SITE/setuptools" "$VENV_SITE/" 2>/dev/null || true
        fi
    fi
    # 方案3: get-pip.py（优先 https，降级 http，用 --trusted-host 绕过证书校验）
    if ! "$VENV_DIR/bin/python" -m pip --version &>/dev/null 2>&1; then
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null || \
            curl -fSL http://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null || true
        [[ -f /tmp/get-pip.py ]] && \
            "$VENV_DIR/bin/python" /tmp/get-pip.py \
                --trusted-host pypi.org --trusted-host files.pythonhosted.org \
                --no-ssl-check 2>/dev/null || true
        rm -f /tmp/get-pip.py
    fi
    if "$VENV_DIR/bin/python" -m pip --version &>/dev/null 2>&1; then
        log_info "[OK] pip 安装成功"
    else
        log_error "无法在 venv 中安装 pip，请检查 Python SSL 模块是否编译正确"
        log_error "建议: bash scripts/deploy/setup_system.sh 将重新编译带 SSL 的 Python"
        exit 1
    fi
fi
"$VENV_DIR/bin/pip" install --upgrade pip --quiet 2>/dev/null || true

# ── 步骤 5: 安装 Python 依赖 ──────────────────────────────────────────────────
log_info "--- 步骤 5/12: 安装 Python 依赖 ---"
# 先安装 PyTorch CPU-only（避免拉取 CUDA 版本，节约磁盘和内存）
# 注意：requirements.txt 中的 torch==2.3.1 需要被跳过，避免覆盖 cpu-only 版本
log_info "安装 PyTorch CPU-only..."
"$VENV_DIR/bin/pip" install \
    "torch==2.3.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu \
    --progress-bar off
log_info "[OK] PyTorch CPU-only 安装完成"

log_info "安装其余 Python 依赖（跳过 torch，避免覆盖 CPU-only 版本）..."
# 写 constraint 文件固定 torch 版本（防止 requirements.txt 中的 torch 行触发重新安装 CUDA 版）
echo "torch==2.3.1+cpu" > /tmp/torch_constraint.txt
"$VENV_DIR/bin/pip" install \
    -r "$BACKEND_DIR/requirements.txt" \
    --constraint /tmp/torch_constraint.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --progress-bar off
rm -f /tmp/torch_constraint.txt
log_info "[OK] Python 依赖安装完成"

# ── 步骤 6: 前端构建 ──────────────────────────────────────────────────────────
log_info "--- 步骤 6/12: 前端构建 ---"
log_info "FRONTEND_DIR=$FRONTEND_DIR"

# 释放内存：停掉已有服务（避免 npm build OOM）
# 内存有限的服务器上 gunicorn 4 workers + celery + sentence-transformers 模型 +
# Vite/Rollup 构建会很容易超内存。restart 在 step 10 重新启动。
log_info "构建前停止已有服务以释放内存..."
systemctl stop genplatform-celery 2>/dev/null || true
systemctl stop genplatform-celery-beat 2>/dev/null || true
systemctl stop genplatform-backend 2>/dev/null || true
sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
log_info "[OK] 服务已停止；构建后将在步骤 10 重新启动"

if [[ -f "$FRONTEND_DIR/package.json" ]]; then
    # 检查 npm/node 可用性
    if ! command -v node &>/dev/null; then
        log_error "node 不可用，请运行 setup_system.sh 安装 Node.js 20"
        exit 1
    fi
    if ! command -v npm &>/dev/null; then
        log_error "npm 不可用"
        exit 1
    fi
    log_info "Node: $(node --version), npm: $(npm --version)"
    # 确保静态文件目录存在
    mkdir -p "$STATIC_DIR"
    # 不用 --silent，否则错误信息也被吞
    (
        cd "$FRONTEND_DIR"
        # 优先用国内镜像加速 npm install
        npm config set registry https://registry.npmmirror.com 2>/dev/null || true
        if [[ -f package-lock.json ]]; then
            npm ci --no-audit --no-fund
        else
            log_warn "[WARN] package-lock.json 缺失，使用 npm install（构建可能不可重现）"
            npm install --no-audit --no-fund
        fi
        # 限制 Node heap 上限，避免 OOM Killer 杀进程（默认 1.7GB，限制为 1GB）
        NODE_OPTIONS="--max-old-space-size=1024" npm run build
    ) || {
        log_error "前端构建失败，请检查 npm 日志"
        # 显示内存状态帮诊断
        log_error "当前内存状态："
        free -h 2>&1 || true
        log_error "OOM 历史："
        dmesg 2>/dev/null | grep -i "killed process" | tail -5 || true
        exit 1
    }
    # 清空旧的静态文件（保留 Django collectstatic 子目录）
    rm -rf "${STATIC_DIR:?}/assets" "${STATIC_DIR:?}/index.html" 2>/dev/null || true
    cp -r "$FRONTEND_DIR/dist/." "$STATIC_DIR/"
    log_info "[OK] 前端构建完成，产物已复制到 $STATIC_DIR"
else
    log_warn "[WARN] $FRONTEND_DIR/package.json 不存在，跳过前端构建"
    # 列出实际目录帮诊断
    if [[ -d "$FRONTEND_DIR" ]]; then
        log_warn "  $FRONTEND_DIR 内容:"
        ls -la "$FRONTEND_DIR" 2>&1 | head -20 || true
    else
        log_warn "  $FRONTEND_DIR 目录不存在"
    fi
fi

# ── 步骤 7: PostgreSQL 初始化 ─────────────────────────────────────────────────
# 必须在 migrate 之前执行：确保 PostgreSQL 服务运行，且目标数据库已创建
log_info "--- 步骤 7/12: 初始化 PostgreSQL 数据库和 pgvector 扩展 ---"
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-content_gen_platform}"
DB_PASS="${POSTGRES_PASSWORD:-}"

# 确保 PostgreSQL 服务正在运行（alinux3 上服务名为 postgresql-15）
if ! systemctl is-active --quiet postgresql-15 2>/dev/null && \
   ! systemctl is-active --quiet postgresql 2>/dev/null; then
    log_warn "[WARN] PostgreSQL 未运行，尝试启动..."
    systemctl start postgresql-15 2>/dev/null || systemctl start postgresql 2>/dev/null || {
        log_error "PostgreSQL 启动失败，请检查安装"
        exit 1
    }
    sleep 3
fi

# 确保 psql 命令可用（PGDG 安装路径可能不在 PATH）
if ! command -v psql &>/dev/null; then
    export PATH="/usr/pgsql-15/bin:$PATH"
fi

# 创建/同步数据库用户密码（确保密码与 .env 一致）
# postgres 用户系统默认存在，CREATE USER 会被跳过；必须用 ALTER USER 同步密码
if [[ -z "$DB_PASS" ]]; then
    log_error "POSTGRES_PASSWORD 为空，无法配置数据库用户密码"
    exit 1
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' CREATEDB;"
    log_info "[OK] 数据库用户 $DB_USER 已创建"
else
    # 始终同步密码（首次部署 postgres 已存在，密码未设；后续部署支持密码轮转）
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';" >/dev/null
    log_info "[OK] 数据库用户 $DB_USER 密码已同步至 .env 配置"
fi

# 创建数据库（若不存在）
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    log_info "[OK] 数据库 $DB_NAME 已创建"
else
    log_info "[SKIP] 数据库 $DB_NAME 已存在"
fi

# 启用 pgvector 扩展
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || \
    log_warn "[WARN] pgvector 扩展启用失败（可能未安装），向量检索功能将不可用"
log_info "[OK] PostgreSQL 初始化完成"

# ── 步骤 8: Django 准备（migrate + collectstatic）────────────────────────────
# 必须在 PostgreSQL 初始化之后执行
log_info "--- 步骤 8/12: 执行数据库迁移 ---"
(
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" manage.py migrate --noinput
)
log_info "[OK] 数据库迁移完成"

log_info "--- 步骤 8b/12: 收集静态文件 ---"
(
    cd "$BACKEND_DIR"
    STATIC_ROOT="$STATIC_DIR/static" \
    "$VENV_DIR/bin/python" manage.py collectstatic --noinput --clear
)
log_info "[OK] collectstatic 完成"

# ── 步骤 9: 嵌入模型预热 ──────────────────────────────────────────────────────
log_info "--- 步骤 9/12: 预热嵌入模型（可失败，Worker 启动时会重试）---"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-BAAI/bge-small-zh-v1.5}"

# HF_HOME 必须与 systemd 服务文件保持一致（/opt/genplatform/.cache/huggingface），
# 否则预热在 /root/.cache/huggingface 下载，celery 用 genplatform 身份起来读不到，
# 会重新下载——而 /home/genplatform 不存在导致 PermissionError，任务永久 failed。
HF_CACHE_DIR="$APP_DIR/.cache/huggingface"
mkdir -p "$HF_CACHE_DIR"
chown -R genplatform:genplatform "$APP_DIR/.cache"

set +e
HF_HOME="$HF_CACHE_DIR" \
    HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}" \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    "$VENV_DIR/bin/python" -c \
    "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL'); print('模型预热完成')" \
    2>&1
PREWARM_EXIT=$?
set -e
if (( PREWARM_EXIT == 0 )); then
    log_info "[OK] 嵌入模型预热成功（缓存路径: $HF_CACHE_DIR）"
else
    log_warn "[WARN] 嵌入模型预热失败（可能网络原因），Worker 首次启动时会重试下载"
fi

# 确保 app 目录所有者正确（文件可能由 root 创建，包括上面写入的 HF 缓存）
chown -R genplatform:genplatform "$APP_DIR" 2>/dev/null || true

# ── 步骤 10: 启动服务 ─────────────────────────────────────────────────────────
log_info "--- 步骤 10/12: 启动 GenPlatform 服务 ---"

# 同步 systemd 服务文件（run_setup=false 时 setup_system.sh 不会跑，
# 服务定义变更必须在此处生效，否则 systemctl 拿到的是旧版 Requires=postgresql.service）
SYSTEMD_SRC="$APP_CODE_DIR/deploy/systemd"
SYSTEMD_DEST="/etc/systemd/system"
if [[ -d "$SYSTEMD_SRC" ]]; then
    daemon_reload=0
    for svc_file in "$SYSTEMD_SRC"/*.service; do
        svc_name="$(basename "$svc_file")"
        dest_file="$SYSTEMD_DEST/$svc_name"
        if [[ ! -f "$dest_file" ]] || ! diff -q "$svc_file" "$dest_file" &>/dev/null; then
            cp "$svc_file" "$dest_file"
            log_info "[OK] systemd 服务已同步: $svc_name"
            daemon_reload=1
        fi
    done
    if (( daemon_reload == 1 )); then
        systemctl daemon-reload
        log_info "[OK] systemctl daemon-reload 完成"
    fi
fi

# 确保基础设施服务（Redis / PostgreSQL）正在运行
log_info "确保 Redis 运行中..."
systemctl start redis 2>/dev/null || systemctl start redis-server 2>/dev/null || \
    log_warn "[WARN] Redis 启动失败，Celery 将无法连接"

log_info "确保 PostgreSQL 运行中..."
systemctl start postgresql-15 2>/dev/null || systemctl start postgresql 2>/dev/null || \
    log_warn "[WARN] PostgreSQL 启动失败"

# 服务重启辅助函数（失败时输出诊断信息，可选致命/非致命）
_restart_service() {
    local svc="$1"
    local fatal="${2:-false}"
    if systemctl restart "$svc" 2>&1; then
        log_info "[OK] $svc 已启动"
        return 0
    fi
    log_error "$svc 启动失败，诊断信息："
    systemctl status "$svc" --no-pager --lines=20 2>&1 | head -30 || true
    journalctl -u "$svc" --no-pager --lines=30 2>&1 | tail -30 || true
    if [[ "$fatal" == "true" ]]; then
        return 1
    fi
    log_warn "[WARN] $svc 启动失败，但部署继续（请手动排查后启动）"
    return 0
}

# backend 是核心服务，启动失败必须 fail（API 不可用就没意义）
_restart_service genplatform-backend true || exit 1

# celery worker 启动可能因为下载嵌入模型超时（首次部署低内存机器）；非致命
# 部署后可手动: systemctl restart genplatform-celery
_restart_service genplatform-celery false

# celery-beat 相对轻量，但也设为非致命避免阻塞
_restart_service genplatform-celery-beat false

log_info "[OK] 服务启动阶段完成（warn 见上方）"

# ── 步骤 11: 重启 Nginx ───────────────────────────────────────────────────────
log_info "--- 步骤 11/12: 重载/启动 Nginx ---"
# 首次部署：Nginx 可能还未运行，用 start；已运行时用 reload（零停机）
if systemctl is-active --quiet nginx 2>/dev/null; then
    nginx -t && systemctl reload nginx
    log_info "[OK] Nginx 已重载（零停机）"
else
    nginx -t && systemctl start nginx
    log_info "[OK] Nginx 已启动"
fi

# ── 步骤 12: 冒烟测试 ────────────────────────────────────────────────────────
log_info "--- 步骤 12/12: 执行冒烟测试 ---"
DEPLOY_MODE=physical bash "$SCRIPT_DIR/smoke_test.sh"

log_info "===== 物理机部署完成 ====="
log_info "部署时间:   $DEPLOY_TIMESTAMP"
log_info "Git commit: $CURRENT_COMMIT"
log_info "如需回滚:   make rollback-physical"
