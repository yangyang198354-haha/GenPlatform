#!/usr/bin/env bash
# scripts/deploy/rollback_docker.sh — Docker 镜像版本回滚 (MOD-DEPLOY-007)
# 用法:
#   bash scripts/deploy/rollback_docker.sh <tag>
#   make rollback-docker TAG=sha-abc1234
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_ROOT/project_workspace/content_gen_platform/src/docker-compose.yml}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

# ── 确定目标 TAG ──────────────────────────────────────────────────────────────
TARGET_TAG="${1:-${TAG:-}}"

if [[ -z "$TARGET_TAG" ]]; then
    log_error "必须指定回滚目标镜像 TAG"
    log_error "用法: make rollback-docker TAG=<image-tag>"
    log_error "      TAG 示例: sha-abc1234, v1.2.0, 20260510"
    exit 1
fi

log_info "===== GenPlatform Docker 回滚 ====="
log_info "目标镜像 TAG: $TARGET_TAG"
log_info "Compose 文件: $COMPOSE_FILE"

check_command docker
if ! docker compose version &>/dev/null; then
    log_error "Docker Compose V2 未安装"
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "Compose 文件不存在: $COMPOSE_FILE"
    exit 1
fi

confirm_action "即将将所有服务镜像回滚到 TAG=$TARGET_TAG，继续？"

# ── 步骤 1: 设置目标 TAG 并拉取镜像 ─────────────────────────────────────────
log_info "--- 步骤 1/5: 拉取目标版本镜像 (TAG=$TARGET_TAG) ---"
# 通过临时覆盖环境变量指定镜像 tag
BACKEND_IMAGE_TAG="$TARGET_TAG" \
FRONTEND_IMAGE_TAG="$TARGET_TAG" \
    docker compose -f "$COMPOSE_FILE" pull
log_info "[OK] 目标版本镜像拉取完成"

# ── 步骤 2: 重启服务（使用目标版本镜像）─────────────────────────────────────
log_info "--- 步骤 2/5: 重启服务（使用回滚版本镜像）---"
BACKEND_IMAGE_TAG="$TARGET_TAG" \
FRONTEND_IMAGE_TAG="$TARGET_TAG" \
    docker compose -f "$COMPOSE_FILE" up -d
log_info "[OK] 服务已使用回滚版本重启"
log_warn "注意: 数据库 migration 回滚（down migration）不会自动执行"
log_warn "      若回滚版本与当前 DB schema 不兼容，请人工执行降级迁移"

# ── 步骤 3: 等待 healthcheck ──────────────────────────────────────────────────
log_info "--- 步骤 3/5: 等待容器健康检查（最多 ${HEALTH_TIMEOUT}s）---"
elapsed=0
while (( elapsed < HEALTH_TIMEOUT )); do
    unhealthy=$(BACKEND_IMAGE_TAG="$TARGET_TAG" FRONTEND_IMAGE_TAG="$TARGET_TAG" \
        docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null \
        | python3 -c "
import sys, json
data = sys.stdin.read().strip()
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
        log_info "[OK] 所有容器健康检查通过"
        break
    fi
    sleep 5
    (( elapsed += 5 )) || true
done

if (( elapsed >= HEALTH_TIMEOUT )); then
    log_warn "[WARN] 超时 ${HEALTH_TIMEOUT}s，部分容器未就绪: $unhealthy"
fi

# ── 步骤 4: 冒烟测试 ─────────────────────────────────────────────────────────
log_info "--- 步骤 4/5: 执行冒烟测试 ---"
DEPLOY_MODE=docker COMPOSE_FILE="$COMPOSE_FILE" bash "$SCRIPT_DIR/smoke_test.sh"

# ── 步骤 5: 记录回滚信息 ──────────────────────────────────────────────────────
log_info "--- 步骤 5/5: 记录回滚信息 ---"
echo "docker-rollback:$TARGET_TAG:$(date '+%Y-%m-%d %H:%M:%S')" \
    >> "$PROJECT_ROOT/.docker_rollback_history"

log_info "===== Docker 回滚完成 ====="
log_info "已回滚到: TAG=$TARGET_TAG"
log_info "查看日志: make logs"
