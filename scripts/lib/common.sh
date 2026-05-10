#!/usr/bin/env bash
# scripts/lib/common.sh — 公共函数库 (MOD-DEPLOY-010)
# 使用方式: source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/lib/common.sh"
# 本文件不可直接执行。

# ── 颜色常量 ──────────────────────────────────────────────────────────────────
readonly COLOR_RED='\033[0;31m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_RESET='\033[0m'

# ── log_info <message> ────────────────────────────────────────────────────────
# 输出带时间戳的信息行（白色）
log_info() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO]  $*"
}

# ── log_warn <message> ────────────────────────────────────────────────────────
# 输出带时间戳的警告行（黄色）
log_warn() {
    echo -e "${COLOR_YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]  $*${COLOR_RESET}" >&2
}

# ── log_error <message> ───────────────────────────────────────────────────────
# 输出带时间戳的错误行（红色）
log_error() {
    echo -e "${COLOR_RED}[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*${COLOR_RESET}" >&2
}

# ── check_command <cmd> ───────────────────────────────────────────────────────
# 检查命令是否存在；不存在则 log_error 并 exit 1
check_command() {
    local cmd="$1"
    if ! command -v "$cmd" &>/dev/null; then
        log_error "必要命令未找到: $cmd。请先运行 'make setup-physical' 安装系统依赖。"
        exit 1
    fi
}

# ── load_env <path> ───────────────────────────────────────────────────────────
# 加载 .env 文件并 export 所有变量（忽略注释行和空行）
load_env() {
    local env_file="${1:-.env}"
    if [[ ! -f "$env_file" ]]; then
        log_error ".env 文件不存在: $env_file"
        log_error "请复制 .env.example 并填写真实配置: cp .env.example .env"
        exit 1
    fi
    # export 非注释、非空行的变量（兼容带引号和不带引号的值）
    set -a
    # shellcheck disable=SC1090
    source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$env_file" | grep -v '^#')
    set +a
    log_info "已加载环境变量: $env_file"
}

# ── wait_for_port <host> <port> <timeout_seconds> ─────────────────────────────
# 等待指定端口可用；超时后返回 1
wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="${3:-30}"
    local elapsed=0

    log_info "等待 $host:$port 可用 (超时 ${timeout}s)..."
    while ! bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null; do
        if (( elapsed >= timeout )); then
            log_error "超时: $host:$port 在 ${timeout}s 内未就绪"
            return 1
        fi
        sleep 2
        (( elapsed += 2 ))
    done
    log_info "[OK] $host:$port 已就绪 (${elapsed}s)"
    return 0
}

# ── get_git_commit ────────────────────────────────────────────────────────────
# 返回当前 git commit 短 hash（7位）
get_git_commit() {
    git rev-parse --short HEAD 2>/dev/null || echo "unknown"
}

# ── confirm_action <message> ──────────────────────────────────────────────────
# 显示确认提示，等待用户输入 yes/no；输入 no 则 exit 0
confirm_action() {
    local message="$1"
    local response
    echo -e "${COLOR_YELLOW}[确认] $message${COLOR_RESET}"
    read -rp "请输入 yes 继续，或 no 取消: " response
    case "$response" in
        yes|YES|y|Y)
            return 0
            ;;
        *)
            log_info "操作已取消。"
            exit 0
            ;;
    esac
}

# ── find_project_root ─────────────────────────────────────────────────────────
# 从当前脚本路径向上找到包含 Makefile 的项目根目录
find_project_root() {
    local dir
    dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/Makefile" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    log_error "找不到项目根目录（无 Makefile 标记）"
    exit 1
}
