#!/usr/bin/env bash
# scripts/deploy/rollback_physical.sh — 物理机代码回退 + 进程重启 (MOD-DEPLOY-006)
# 用法:
#   bash scripts/deploy/rollback_physical.sh             # 回滚到 .last_deployed_commit
#   bash scripts/deploy/rollback_physical.sh <commit>    # 回滚到指定 commit
#   make rollback-physical VERSION=<commit>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

APP_DIR="${APP_DIR:-/opt/genplatform}"
APP_CODE_DIR="$APP_DIR/app"
VENV_DIR="$APP_DIR/venv"
BACKEND_DIR="$APP_CODE_DIR/project_workspace/content_gen_platform/src/backend"
FRONTEND_DIR="$APP_CODE_DIR/project_workspace/content_gen_platform/src/frontend"
STATIC_DIR="$APP_DIR/staticfiles"

# ── 确定目标 VERSION ──────────────────────────────────────────────────────────
TARGET_VERSION="${1:-${VERSION:-}}"

if [[ -z "$TARGET_VERSION" ]]; then
    LAST_COMMIT_FILE="$APP_DIR/.last_deployed_commit"
    if [[ -f "$LAST_COMMIT_FILE" ]]; then
        TARGET_VERSION="$(cat "$LAST_COMMIT_FILE")"
        log_info "未指定 VERSION，从 .last_deployed_commit 读取: $TARGET_VERSION"
    else
        log_error "未指定 VERSION，且 .last_deployed_commit 文件不存在"
        log_error "用法: make rollback-physical VERSION=<commit_hash>"
        exit 1
    fi
fi

CURRENT_COMMIT="$(git -C "$APP_CODE_DIR" rev-parse --short HEAD 2>/dev/null || get_git_commit)"
log_info "===== GenPlatform 物理机回滚 ====="
log_info "当前 commit:  $CURRENT_COMMIT"
log_info "目标 commit:  $TARGET_VERSION"

if [[ "$CURRENT_COMMIT" == "$TARGET_VERSION" ]]; then
    log_warn "当前 commit 与目标 commit 相同 ($TARGET_VERSION)，无需回滚"
    exit 0
fi

# 回滚是危险操作，要求确认
confirm_action "即将把代码回滚到 $TARGET_VERSION，当前版本 $CURRENT_COMMIT 的变更将被撤销。继续？"

# ── 步骤 1: git checkout 回退代码 ────────────────────────────────────────────
log_info "--- 步骤 1/8: git checkout $TARGET_VERSION ---"
git -C "$APP_CODE_DIR" fetch --all
git -C "$APP_CODE_DIR" checkout "$TARGET_VERSION"
log_info "[OK] 代码已切换到 $TARGET_VERSION"

# ── 步骤 2: 重新安装依赖（依据回退版本的 requirements.txt）──────────────────
log_info "--- 步骤 2/8: 重新安装 Python 依赖 ---"
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
log_info "[OK] Python 依赖安装完成"

# ── 步骤 3: 数据库迁移说明 ────────────────────────────────────────────────────
log_info "--- 步骤 3/8: 数据库迁移 ---"
log_warn "注意: 代码回滚不会自动执行 down migration（数据库降级迁移）"
log_warn "      若回滚版本删除了数据库字段，请人工执行:"
log_warn "      $VENV_DIR/bin/python manage.py migrate <app_name> <migration_number>"
log_warn "      在继续之前，请确认当前数据库 schema 与 $TARGET_VERSION 兼容。"

# 执行 migrate（处理无需降级的情况，幂等）
(
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" manage.py migrate --noinput
)
log_info "[OK] 数据库迁移完成（如有 down migration 需求，请人工处理）"

# ── 步骤 4: 前端重新构建 ──────────────────────────────────────────────────────
log_info "--- 步骤 4/8: 重新构建前端 ---"
if [[ -f "$FRONTEND_DIR/package.json" ]]; then
    # 检测前端代码与当前部署是否不同
    FRONT_DIFF=$(git -C "$APP_CODE_DIR" diff --name-only "$CURRENT_COMMIT" "$TARGET_VERSION" 2>/dev/null \
        | grep "^project_workspace/content_gen_platform/src/frontend/" || true)
    if [[ -n "$FRONT_DIFF" ]]; then
        log_info "前端代码有差异，重新构建..."
        (
            cd "$FRONTEND_DIR"
            npm ci --silent
            npm run build
        )
        rm -rf "${STATIC_DIR:?}/assets" "${STATIC_DIR:?}/index.html" 2>/dev/null || true
        cp -r "$FRONTEND_DIR/dist/." "$STATIC_DIR/"
        log_info "[OK] 前端重新构建完成"
    else
        log_info "[SKIP] 前端代码无差异，跳过构建"
    fi
else
    log_warn "[WARN] 未找到 package.json，跳过前端构建"
fi

# ── 步骤 5: 收集静态文件 ──────────────────────────────────────────────────────
log_info "--- 步骤 5/8: 收集静态文件 ---"
(
    cd "$BACKEND_DIR"
    STATIC_ROOT="$STATIC_DIR/static" \
    "$VENV_DIR/bin/python" manage.py collectstatic --noinput
)
log_info "[OK] collectstatic 完成"

# ── 步骤 6: 重启所有 GenPlatform 服务 ────────────────────────────────────────
log_info "--- 步骤 6/8: 重启所有服务 ---"
systemctl restart genplatform-backend
systemctl stop genplatform-celery && systemctl start genplatform-celery
systemctl restart genplatform-celery-beat
log_info "[OK] 所有服务已重启"

# ── 步骤 7: Nginx 重载 ───────────────────────────────────────────────────────
log_info "--- 步骤 7/8: Nginx 重载 ---"
systemctl reload nginx
log_info "[OK] Nginx 重载完成"

# ── 步骤 8: 冒烟测试 ─────────────────────────────────────────────────────────
log_info "--- 步骤 8/8: 执行冒烟测试 ---"
DEPLOY_MODE=physical bash "$SCRIPT_DIR/smoke_test.sh"

# 更新 .last_deployed_commit 为回滚目标版本
echo "$TARGET_VERSION" > "$APP_DIR/.last_deployed_commit"

log_info "===== 物理机回滚完成 ====="
log_info "已回滚到: $TARGET_VERSION"
log_info "此前版本: $CURRENT_COMMIT"
