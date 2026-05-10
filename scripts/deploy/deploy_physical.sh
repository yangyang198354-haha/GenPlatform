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
bash "$SCRIPT_DIR/validate_config.sh" "$PROJECT_ROOT/.env"

# 加载环境变量
load_env "$PROJECT_ROOT/.env"

# ── 步骤 2: 记录当前 commit ───────────────────────────────────────────────────
log_info "--- 步骤 2/12: 记录部署时间和 commit ---"
DEPLOY_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
CURRENT_COMMIT="$(get_git_commit)"
echo "$CURRENT_COMMIT" > "$APP_DIR/.last_deployed_commit"
log_info "当前 commit: $CURRENT_COMMIT"

# ── 步骤 3: 同步代码 ──────────────────────────────────────────────────────────
log_info "--- 步骤 3/12: 同步代码到 $APP_CODE_DIR ---"
if [[ -d "$APP_CODE_DIR/.git" ]]; then
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
if [[ ! -f "$VENV_DIR/bin/python" ]]; then
    python3.12 -m venv "$VENV_DIR"
    log_info "[OK] venv 创建完成: $VENV_DIR"
else
    log_info "[SKIP] venv 已存在，跳过创建"
fi
"$VENV_DIR/bin/pip" install --upgrade pip --quiet

# ── 步骤 5: 安装 Python 依赖 ──────────────────────────────────────────────────
log_info "--- 步骤 5/12: 安装 Python 依赖 ---"
# 先安装 PyTorch CPU-only（避免拉取 CUDA 版本，节约磁盘）
log_info "安装 PyTorch CPU-only..."
"$VENV_DIR/bin/pip" install \
    "torch==2.3.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu \
    --quiet
log_info "[OK] PyTorch CPU-only 安装完成"

log_info "安装其余 Python 依赖..."
"$VENV_DIR/bin/pip" install \
    -r "$BACKEND_DIR/requirements.txt" \
    --quiet
log_info "[OK] Python 依赖安装完成"

# ── 步骤 6: 前端构建 ──────────────────────────────────────────────────────────
log_info "--- 步骤 6/12: 前端构建 ---"
if [[ -f "$FRONTEND_DIR/package.json" ]]; then
    (
        cd "$FRONTEND_DIR"
        npm ci --silent
        npm run build
    )
    # 清空旧的静态文件（保留 Django collectstatic 子目录）
    rm -rf "${STATIC_DIR:?}/assets" "${STATIC_DIR:?}/index.html" 2>/dev/null || true
    cp -r "$FRONTEND_DIR/dist/." "$STATIC_DIR/"
    log_info "[OK] 前端构建完成，产物已复制到 $STATIC_DIR"
else
    log_warn "[WARN] frontend/package.json 不存在，跳过前端构建"
fi

# ── 步骤 7: Django 准备 ───────────────────────────────────────────────────────
log_info "--- 步骤 7/12: 执行数据库迁移 ---"
(
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" manage.py migrate --noinput
)
log_info "[OK] 数据库迁移完成"

log_info "--- 步骤 7b/12: 收集静态文件 ---"
(
    cd "$BACKEND_DIR"
    STATIC_ROOT="$STATIC_DIR/static" \
    "$VENV_DIR/bin/python" manage.py collectstatic --noinput --clear
)
log_info "[OK] collectstatic 完成"

# ── 步骤 8: PostgreSQL 初始化 ─────────────────────────────────────────────────
log_info "--- 步骤 8/12: 初始化 PostgreSQL 数据库和 pgvector 扩展 ---"
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-content_gen_platform}"
DB_PASS="${POSTGRES_PASSWORD:-}"

# 创建数据库用户（若不存在）
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 2>/dev/null; then
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    log_info "[OK] 数据库用户 $DB_USER 已创建"
else
    log_info "[SKIP] 数据库用户 $DB_USER 已存在"
fi

# 创建数据库（若不存在）
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 2>/dev/null; then
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    log_info "[OK] 数据库 $DB_NAME 已创建"
else
    log_info "[SKIP] 数据库 $DB_NAME 已存在"
fi

# 启用 pgvector 扩展
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null
log_info "[OK] pgvector 扩展已启用"

# ── 步骤 9: 嵌入模型预热 ──────────────────────────────────────────────────────
log_info "--- 步骤 9/12: 预热嵌入模型（可失败，Worker 启动时会重试）---"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-BAAI/bge-small-zh-v1.5}"
set +e
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}" \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    "$VENV_DIR/bin/python" -c \
    "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL'); print('模型预热完成')" \
    2>&1
PREWARM_EXIT=$?
set -e
if (( PREWARM_EXIT == 0 )); then
    log_info "[OK] 嵌入模型预热成功"
else
    log_warn "[WARN] 嵌入模型预热失败（可能网络原因），Worker 首次启动时会重试下载"
fi

# 确保 app 目录所有者正确（文件可能由 root 创建）
chown -R genplatform:genplatform "$APP_DIR" 2>/dev/null || true

# ── 步骤 10: 启动服务 ─────────────────────────────────────────────────────────
log_info "--- 步骤 10/12: 启动 GenPlatform 服务 ---"
systemctl start genplatform-backend
systemctl start genplatform-celery
systemctl start genplatform-celery-beat
log_info "[OK] 所有服务已启动"

# ── 步骤 11: 重启 Nginx ───────────────────────────────────────────────────────
log_info "--- 步骤 11/12: 重载 Nginx ---"
systemctl reload nginx
log_info "[OK] Nginx 已重载"

# ── 步骤 12: 冒烟测试 ────────────────────────────────────────────────────────
log_info "--- 步骤 12/12: 执行冒烟测试 ---"
DEPLOY_MODE=physical bash "$SCRIPT_DIR/smoke_test.sh"

log_info "===== 物理机部署完成 ====="
log_info "部署时间:   $DEPLOY_TIMESTAMP"
log_info "Git commit: $CURRENT_COMMIT"
log_info "如需回滚:   make rollback-physical"
