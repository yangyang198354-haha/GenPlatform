#!/usr/bin/env bash
# scripts/deploy/smoke_test.sh — 部署后冒烟测试 (MOD-DEPLOY-009)
# 用法: bash scripts/deploy/smoke_test.sh [--mode physical|docker]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

APP_DIR="${APP_DIR:-/opt/genplatform}"
DEPLOY_MODE="${DEPLOY_MODE:-physical}"
BASE_URL="${BASE_URL:-http://localhost}"
TIMEOUT="${SMOKE_TIMEOUT:-60}"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            DEPLOY_MODE="$2"
            shift 2
            ;;
        --url)
            BASE_URL="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

pass_count=0
fail_count=0

# ── 辅助函数 ─────────────────────────────────────────────────────────────────
check_pass() {
    local label="$1"
    echo -e "  ${COLOR_GREEN}[PASS]${COLOR_RESET} $label"
    (( pass_count++ )) || true
}

check_fail() {
    local label="$1"
    local detail="${2:-}"
    echo -e "  ${COLOR_RED}[FAIL]${COLOR_RESET} $label"
    [[ -n "$detail" ]] && echo "         $detail"
    (( fail_count++ )) || true
}

log_info "===== 冒烟测试开始 (mode=$DEPLOY_MODE, url=$BASE_URL) ====="

# ── 测试 1: Django API 健康检查 ───────────────────────────────────────────────
log_info "--- 测试 1/4: Django API 响应检查 ---"
api_url="${BASE_URL}/api/v1/auth/login/"
elapsed=0
api_ok=false
while (( elapsed < TIMEOUT )); do
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$api_url" 2>/dev/null || echo "000")
    if [[ "$http_code" != "000" && "$http_code" != "5"* ]]; then
        check_pass "GET $api_url -> HTTP $http_code（非 5xx，Django 正常响应）"
        api_ok=true
        break
    fi
    sleep 3
    (( elapsed += 3 )) || true
done
if ! $api_ok; then
    check_fail "GET $api_url" "超时 ${TIMEOUT}s 或返回 5xx（HTTP: $http_code）"
fi

# ── 测试 2: 前端静态文件服务 ──────────────────────────────────────────────────
log_info "--- 测试 2/4: 前端 HTML 响应检查 ---"
front_url="${BASE_URL}/"
front_body=$(curl -s --max-time 10 "$front_url" 2>/dev/null || echo "")
if echo "$front_body" | grep -qi "<!DOCTYPE html>"; then
    check_pass "GET $front_url -> 包含 <!DOCTYPE html>（前端静态文件服务正常）"
else
    check_fail "GET $front_url" "响应不含 <!DOCTYPE html>，前端静态文件可能未构建或 Nginx 配置错误"
fi

# ── 测试 3: Celery Worker 活跃检查 ────────────────────────────────────────────
log_info "--- 测试 3/4: Celery Worker 活跃检查 ---"
if [[ "$DEPLOY_MODE" == "physical" ]]; then
    if systemctl is-active --quiet genplatform-celery 2>/dev/null; then
        check_pass "systemctl genplatform-celery -> active"
    else
        svc_status=$(systemctl is-active genplatform-celery 2>/dev/null || echo "unknown")
        check_fail "genplatform-celery 服务状态: $svc_status（期望 active）"
    fi
else
    # Docker 模式
    if docker compose -f "${COMPOSE_FILE:-$PROJECT_ROOT/project_workspace/content_gen_platform/src/docker-compose.yml}" \
            exec -T celery_worker celery -A config inspect active --timeout 10 &>/dev/null; then
        check_pass "docker celery_worker -> Celery inspect active 成功"
    else
        check_fail "Celery Worker（Docker）未响应 inspect active"
    fi
fi

# ── 测试 4: 数据库连接检查 ────────────────────────────────────────────────────
log_info "--- 测试 4/4: 数据库连接检查 ---"
if [[ "$DEPLOY_MODE" == "physical" ]]; then
    VENV_PYTHON="$APP_DIR/venv/bin/python"
    BACKEND_DIR="$APP_DIR/app/project_workspace/content_gen_platform/src/backend"
    if [[ -x "$VENV_PYTHON" ]]; then
        if (cd "$BACKEND_DIR" && "$VENV_PYTHON" manage.py check --database default 2>&1 | grep -q "System check identified no issues"); then
            check_pass "manage.py check --database default -> 无问题"
        else
            db_output=$(cd "$BACKEND_DIR" && "$VENV_PYTHON" manage.py check --database default 2>&1 || true)
            check_fail "manage.py check --database default 失败" "$db_output"
        fi
    else
        check_fail "venv Python 不存在: $VENV_PYTHON（请先运行 make deploy-physical）"
    fi
else
    log_info "[SKIP] Docker 模式下跳过物理机数据库检查（依赖 healthcheck）"
    (( pass_count++ )) || true
fi

# ── 汇总 ──────────────────────────────────────────────────────────────────────
echo ""
log_info "===== 冒烟测试结果: ${pass_count} PASS / ${fail_count} FAIL ====="
if (( fail_count > 0 )); then
    log_error "冒烟测试未通过，请检查以上 FAIL 项后执行: make rollback-physical"
    exit 1
else
    log_info "[OK] 所有冒烟测试通过，部署成功！"
fi
