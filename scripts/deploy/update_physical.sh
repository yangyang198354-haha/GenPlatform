#!/usr/bin/env bash
# scripts/deploy/update_physical.sh — 物理机增量热更新 (MOD-DEPLOY-005)
# 用法: bash scripts/deploy/update_physical.sh
# 目标: 最小化停机时间（Gunicorn graceful reload + Celery warm shutdown）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

APP_DIR="${APP_DIR:-/opt/genplatform}"
BRANCH="${BRANCH:-main}"
APP_CODE_DIR="$APP_DIR/app"
VENV_DIR="$APP_DIR/venv"
BACKEND_DIR="$APP_CODE_DIR/project_workspace/content_gen_platform/src/backend"
FRONTEND_DIR="$APP_CODE_DIR/project_workspace/content_gen_platform/src/frontend"
STATIC_DIR="$APP_DIR/staticfiles"

log_info "===== GenPlatform 物理机增量热更新 ====="

# ── 步骤 1: 记录当前 commit（更新前，用于回滚参考）────────────────────────────
log_info "--- 步骤 1/11: 记录当前 commit ---"
# 从部署目录读取当前 commit（APP_CODE_DIR 是 git 仓库位置）
PREV_COMMIT="$(git -C "$APP_CODE_DIR" rev-parse --short HEAD 2>/dev/null || get_git_commit)"
log_info "更新前 commit: $PREV_COMMIT"
echo "$PREV_COMMIT" > "$APP_DIR/.last_deployed_commit"

# ── 步骤 2: 拉取最新代码 ──────────────────────────────────────────────────────
log_info "--- 步骤 2/11: 拉取最新代码 (origin/$BRANCH) ---"
git -C "$APP_CODE_DIR" fetch origin
git -C "$APP_CODE_DIR" checkout "$BRANCH"
git -C "$APP_CODE_DIR" pull origin "$BRANCH"
NEW_COMMIT="$(git -C "$APP_CODE_DIR" rev-parse --short HEAD)"
log_info "[OK] git pull 完成，新 commit: $NEW_COMMIT"

# ── 步骤 3: 检测 requirements.txt 变更 ───────────────────────────────────────
log_info "--- 步骤 3/11: 检测 Python 依赖变更 ---"
REQUIREMENTS_CHANGED=false
if git -C "$APP_CODE_DIR" diff --name-only "$PREV_COMMIT" "$NEW_COMMIT" 2>/dev/null \
        | grep -q "requirements.txt"; then
    REQUIREMENTS_CHANGED=true
fi

if $REQUIREMENTS_CHANGED; then
    log_info "requirements.txt 有变更，重新安装 Python 依赖..."
    "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
    log_info "[OK] Python 依赖更新完成"
else
    log_info "[SKIP] requirements.txt 无变更，跳过 pip install"
fi

# ── 步骤 4: 检测前端代码变更 ─────────────────────────────────────────────────
log_info "--- 步骤 4/11: 检测前端代码变更 ---"
FRONTEND_CHANGED=false
if git -C "$APP_CODE_DIR" diff --name-only "$PREV_COMMIT" "$NEW_COMMIT" 2>/dev/null \
        | grep -q "^project_workspace/content_gen_platform/src/frontend/"; then
    FRONTEND_CHANGED=true
fi

if $FRONTEND_CHANGED; then
    log_info "前端代码有变更，重新构建..."
    (
        cd "$FRONTEND_DIR"
        npm ci --silent
        npm run build
    )
    rm -rf "${STATIC_DIR:?}/assets" "${STATIC_DIR:?}/index.html" 2>/dev/null || true
    cp -r "$FRONTEND_DIR/dist/." "$STATIC_DIR/"
    log_info "[OK] 前端重新构建完成"
else
    log_info "[SKIP] 前端代码无变更，跳过 npm build"
fi

# ── 步骤 5: 数据库迁移（幂等）────────────────────────────────────────────────
log_info "--- 步骤 5/11: 数据库迁移 ---"
(
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" manage.py migrate --noinput
)
log_info "[OK] 数据库迁移完成（无待迁移项时快速完成）"

# ── 步骤 6: 收集静态文件 ──────────────────────────────────────────────────────
log_info "--- 步骤 6/11: 收集静态文件 ---"
(
    cd "$BACKEND_DIR"
    STATIC_ROOT="$STATIC_DIR/static" \
    "$VENV_DIR/bin/python" manage.py collectstatic --noinput
)
log_info "[OK] collectstatic 完成"

# ── 步骤 7: Gunicorn Graceful Reload（零停机）────────────────────────────────
log_info "--- 步骤 7/11: Gunicorn graceful reload （零停机）---"
# systemctl reload 发送 HUP 信号，Gunicorn 完成当前请求后热重启 Worker
systemctl reload genplatform-backend
log_info "[OK] Gunicorn graceful reload 已触发"

# ── 步骤 8: Celery Worker warm shutdown + restart ─────────────────────────────
log_info "--- 步骤 8/11: Celery Worker warm shutdown + restart ---"
log_info "停止 Celery Worker（warm shutdown，已接受任务执行完成后退出）..."
systemctl stop genplatform-celery
log_info "重新启动 Celery Worker..."
systemctl start genplatform-celery
log_info "[OK] Celery Worker 重启完成"

# ── 步骤 9: Celery Beat 重启 ──────────────────────────────────────────────────
log_info "--- 步骤 9/11: Celery Beat 重启 ---"
systemctl restart genplatform-celery-beat
log_info "[OK] Celery Beat 重启完成"

# ── 步骤 10: Nginx 重载 ───────────────────────────────────────────────────────
log_info "--- 步骤 10/11: Nginx 重载 ---"
systemctl reload nginx
log_info "[OK] Nginx 重载完成"

# ── 步骤 11: 冒烟测试 ────────────────────────────────────────────────────────
log_info "--- 步骤 11/11: 执行冒烟测试 ---"
DEPLOY_MODE=physical bash "$SCRIPT_DIR/smoke_test.sh"

log_info "===== 物理机增量更新完成 ====="
log_info "更新前 commit: $PREV_COMMIT"
log_info "更新后 commit: $NEW_COMMIT"
log_info "如需回滚:      make rollback-physical  （回滚到 $PREV_COMMIT）"
