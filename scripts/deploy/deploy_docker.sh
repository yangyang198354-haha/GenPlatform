#!/usr/bin/env bash
# scripts/deploy/deploy_docker.sh — Docker 部署入口 (MOD-DEPLOY-004)
# 用法: bash scripts/deploy/deploy_docker.sh
# 前置条件: Docker Engine 和 Docker Compose V2 已安装
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_ROOT/project_workspace/content_gen_platform/src/docker-compose.yml}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

log_info "===== GenPlatform Docker 部署 ====="
log_info "Compose 文件: $COMPOSE_FILE"

# ── 步骤 1: 检查 Docker 和 Docker Compose V2 ─────────────────────────────────
log_info "--- 步骤 1/7: 检查 Docker 环境 ---"
check_command docker

if ! docker compose version &>/dev/null; then
    log_error "Docker Compose V2 未安装。"
    log_error "请安装: https://docs.docker.com/compose/install/"
    exit 1
fi
log_info "[OK] Docker: $(docker --version)"
log_info "[OK] Docker Compose: $(docker compose version --short)"

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "Compose 文件不存在: $COMPOSE_FILE"
    exit 1
fi

# ── 步骤 2: 检测端口 80 冲突 ─────────────────────────────────────────────────
log_info "--- 步骤 2/7: 检测端口 80 冲突 ---"
if ss -tlnp 2>/dev/null | grep -q ':80 '; then
    # 检查占用端口 80 的是否为 Docker 管理的进程
    PORT80_PROC=$(ss -tlnp | grep ':80 ' | awk '{print $NF}' || true)
    if echo "$PORT80_PROC" | grep -qi "docker\|nginx.*docker\|proxy"; then
        log_info "[OK] 端口 80 由 Docker 管理（可能为已有容器），继续..."
    else
        log_warn "[WARN] 端口 80 被非 Docker 进程占用: $PORT80_PROC"
        log_warn "       物理机 Nginx 可能正在运行。请先停止: sudo systemctl stop nginx"
        confirm_action "端口 80 可能被占用，是否强制继续？（可能导致容器启动失败）"
    fi
else
    log_info "[OK] 端口 80 未被占用"
fi

# ── 步骤 3: 配置校验 ──────────────────────────────────────────────────────────
log_info "--- 步骤 3/7: 校验 .env 配置 ---"
bash "$SCRIPT_DIR/validate_config.sh" "$PROJECT_ROOT/.env"

# ── 步骤 4: 拉取最新镜像 ──────────────────────────────────────────────────────
log_info "--- 步骤 4/7: 拉取最新镜像 ---"
docker compose -f "$COMPOSE_FILE" pull
log_info "[OK] 镜像拉取完成"

# ── 步骤 5: 启动所有容器 ──────────────────────────────────────────────────────
log_info "--- 步骤 5/7: 启动所有容器 ---"
docker compose -f "$COMPOSE_FILE" up -d
log_info "[OK] 容器已启动"

# ── 步骤 6: 等待 healthcheck 全部 healthy ─────────────────────────────────────
log_info "--- 步骤 6/7: 等待容器健康检查通过（最多 ${HEALTH_TIMEOUT}s）---"
elapsed=0
all_healthy=false
while (( elapsed < HEALTH_TIMEOUT )); do
    # 检查所有有 healthcheck 的容器是否均 healthy
    unhealthy=$(docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null \
        | python3 -c "
import sys, json
data = sys.stdin.read().strip()
# docker compose ps --format json 可能是多行 JSON 对象或 JSON 数组
lines = [l for l in data.split('\n') if l.strip()]
containers = []
for line in lines:
    try:
        containers.append(json.loads(line))
    except Exception:
        pass
unhealthy = [c.get('Name','?') for c in containers
             if c.get('Health','') not in ('healthy', '')]
print('\n'.join(unhealthy))
" 2>/dev/null || true)

    if [[ -z "$unhealthy" ]]; then
        all_healthy=true
        break
    fi
    log_info "等待容器就绪: $unhealthy (${elapsed}s)"
    sleep 5
    (( elapsed += 5 )) || true
done

if $all_healthy; then
    log_info "[OK] 所有容器健康检查通过"
else
    log_warn "[WARN] 超时 ${HEALTH_TIMEOUT}s，以下容器未就绪: $unhealthy"
    log_warn "       继续执行冒烟测试，请手动检查容器状态: docker compose ps"
fi

# ── 步骤 7: 冒烟测试 ─────────────────────────────────────────────────────────
log_info "--- 步骤 7/7: 执行冒烟测试 ---"
DEPLOY_MODE=docker COMPOSE_FILE="$COMPOSE_FILE" bash "$SCRIPT_DIR/smoke_test.sh"

log_info "===== Docker 部署完成 ====="
log_info "查看日志: make logs"
log_info "如需回滚: make rollback-docker TAG=<image-tag>"
