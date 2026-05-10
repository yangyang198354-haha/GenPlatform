#!/usr/bin/env bash
# scripts/deploy/validate_config.sh — .env 完整性校验 (MOD-DEPLOY-008)
# 用法: bash scripts/deploy/validate_config.sh [.env路径]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

ENV_FILE="${1:-$PROJECT_ROOT/.env}"

# ── 必填变量清单 ──────────────────────────────────────────────────────────────
REQUIRED_VARS=(
    DJANGO_SECRET_KEY
    ENCRYPTION_KEY
    POSTGRES_PASSWORD
    POSTGRES_DB
    ALLOWED_HOSTS
    CORS_ALLOWED_ORIGINS
    REDIS_URL
)

# 需掩码显示的敏感变量
SENSITIVE_VARS=(DJANGO_SECRET_KEY ENCRYPTION_KEY POSTGRES_PASSWORD)

# ── 辅助函数 ──────────────────────────────────────────────────────────────────
is_sensitive() {
    local var="$1"
    for sv in "${SENSITIVE_VARS[@]}"; do
        [[ "$sv" == "$var" ]] && return 0
    done
    return 1
}

mask_value() {
    echo "****"
}

# ── 主逻辑 ───────────────────────────────────────────────────────────────────
log_info "===== 配置校验开始: $ENV_FILE ====="

if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env 文件不存在: $ENV_FILE"
    log_error "请复制模板并填写: cp .env.example .env"
    exit 1
fi

# 将 .env 载入当前 shell（仅用于校验，不 export 到外部）
declare -A env_map
while IFS='=' read -r key val; do
    # 跳过注释行和空行
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$key" ]] && continue
    # 去掉 key 和 val 两端空白
    key="${key// /}"
    # 去掉 val 两端引号
    val="${val%\"}"
    val="${val#\"}"
    val="${val%\'}"
    val="${val#\'}"
    env_map["$key"]="$val"
done < "$ENV_FILE"

error_count=0
warn_count=0
check_count=0

# ── 1. 变量存在性检查 ─────────────────────────────────────────────────────────
for var in "${REQUIRED_VARS[@]}"; do
    (( check_count++ )) || true
    val="${env_map[$var]:-}"
    display_val="$(is_sensitive "$var" && mask_value || echo "${val:-(空)}")"

    if [[ -z "$val" ]]; then
        log_error "[ERROR] 缺少必填变量或值为空: $var"
        (( error_count++ )) || true
    else
        echo "  [OK]   $var = $display_val"
    fi
done

# ── 2. DJANGO_SECRET_KEY 长度检查（>= 50 字符）─────────────────────────────
secret_key="${env_map[DJANGO_SECRET_KEY]:-}"
if [[ -n "$secret_key" ]]; then
    key_len="${#secret_key}"
    if (( key_len < 50 )); then
        log_error "[ERROR] DJANGO_SECRET_KEY 长度不足 50 字符（当前 ${key_len} 字符）"
        (( error_count++ )) || true
    fi

    # 检测默认示例值
    if [[ "$secret_key" == *"change-me"* ]] || [[ "$secret_key" == "change-me-to-a-random-50-char-string" ]]; then
        log_error "[ERROR] DJANGO_SECRET_KEY 仍为默认示例值，请生成随机密钥:"
        log_error "        python3 -c \"import secrets; print(secrets.token_urlsafe(50))\""
        (( error_count++ )) || true
    fi
fi

# ── 3. ENCRYPTION_KEY 默认值检查 ─────────────────────────────────────────────
enc_key="${env_map[ENCRYPTION_KEY]:-}"
if [[ "$enc_key" == *"change-me"* ]]; then
    log_error "[ERROR] ENCRYPTION_KEY 仍为默认示例值，请生成随机 32 字节 base64 密钥:"
    log_error "        python3 -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
    (( error_count++ )) || true
fi

# ── 4. Docker 服务名警告（物理机部署时应改为 localhost）──────────────────────
db_url="${env_map[DATABASE_URL]:-}"
redis_url="${env_map[REDIS_URL]:-}"

if [[ "$db_url" =~ @db: ]]; then
    log_warn "[WARN] DATABASE_URL 中检测到 Docker 服务名 (@db:)，物理机部署时请修改为 localhost 或实际 IP"
    log_warn "       示例: DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/content_gen_platform"
    (( warn_count++ )) || true
fi

if [[ "$redis_url" =~ redis://redis: ]]; then
    log_warn "[WARN] REDIS_URL 中检测到 Docker 服务名 (redis://redis:)，物理机部署时请修改为 localhost"
    log_warn "       示例: REDIS_URL=redis://localhost:6379/0"
    (( warn_count++ )) || true
fi

# ── 汇总输出 ──────────────────────────────────────────────────────────────────
echo ""
if (( error_count > 0 )); then
    log_error "配置校验失败: 发现 ${error_count} 个错误，${warn_count} 个警告，共检查 ${check_count} 个变量"
    exit 1
else
    if (( warn_count > 0 )); then
        log_warn "[WARN] 配置校验通过（含 ${warn_count} 个警告），共检查 ${check_count} 个变量"
    else
        log_info "[OK] 配置校验通过，共检查 ${check_count} 个变量"
    fi
fi
