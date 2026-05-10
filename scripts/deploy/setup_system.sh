#!/usr/bin/env bash
# scripts/deploy/setup_system.sh — 系统依赖安装（幂等）(MOD-DEPLOY-002)
# 用法: sudo bash scripts/deploy/setup_system.sh
# 支持 OS: Ubuntu 22.04 / Debian 12（完全支持）; CentOS Stream 9（部分支持）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

APP_DIR="${APP_DIR:-/opt/genplatform}"
APP_USER="genplatform"

# ── 必须以 root 运行 ─────────────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
    log_error "本脚本需要以 root 权限运行: sudo bash $0"
    exit 1
fi

log_info "===== GenPlatform 系统依赖安装 ====="
log_info "项目根目录: $PROJECT_ROOT"
log_info "部署目录:   $APP_DIR"

# ── 1. 检测 OS 类型 ───────────────────────────────────────────────────────────
detect_os() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        source /etc/os-release
        OS_ID="$ID"
        OS_VERSION_ID="$VERSION_ID"
        OS_CODENAME="${VERSION_CODENAME:-}"
    else
        log_error "无法检测 OS 类型（/etc/os-release 不存在）"
        exit 1
    fi

    case "$OS_ID" in
        ubuntu|debian)
            log_info "[OK] 检测到 OS: $ID $VERSION_ID ($OS_CODENAME)"
            PKG_MANAGER="apt"
            ;;
        centos|rhel|rocky|almalinux)
            log_warn "[WARN] 检测到 CentOS/RHEL 系列: $ID $VERSION_ID"
            log_warn "       CentOS 模式为部分支持，建议使用 Ubuntu 22.04。"
            PKG_MANAGER="dnf"
            ;;
        alinux)
            log_info "[OK] 检测到阿里云 Linux (Alibaba Cloud Linux): $ID $VERSION_ID"
            # alinux2 用 yum，alinux3 用 dnf；优先使用 dnf，否则回退到 yum
            if command -v dnf &>/dev/null; then
                PKG_MANAGER="dnf"
            else
                PKG_MANAGER="yum"
            fi
            ;;
        *)
            log_error "不支持的 OS: $ID。本脚本仅支持 Ubuntu/Debian/CentOS/Alibaba Cloud Linux。"
            exit 1
            ;;
    esac
}

detect_os

# ── 2. apt 方式安装（Ubuntu / Debian）────────────────────────────────────────
install_apt() {
    log_info "--- 步骤 1/8: 更新 apt 包列表 ---"
    apt-get update -qq

    log_info "--- 步骤 2/8: 安装基础工具 ---"
    apt-get install -y --no-install-recommends \
        curl wget gnupg lsb-release ca-certificates \
        git build-essential
    log_info "[OK] 基础工具安装完成"

    log_info "--- 步骤 3/8: 添加 PostgreSQL 官方 PGDG apt 源 ---"
    PGDG_KEY="/etc/apt/trusted.gpg.d/postgresql.gpg"
    PGDG_LIST="/etc/apt/sources.list.d/pgdg.list"
    if [[ ! -f "$PGDG_LIST" ]]; then
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
            | gpg --dearmor -o "$PGDG_KEY"
        echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
            > "$PGDG_LIST"
        apt-get update -qq
        log_info "[OK] PGDG apt 源已添加"
    else
        log_info "[SKIP] PGDG apt 源已存在"
    fi

    log_info "--- 步骤 4/8: 安装 PostgreSQL 15 + pgvector ---"
    apt-get install -y --no-install-recommends \
        postgresql-15 \
        postgresql-15-pgvector \
        libpq-dev
    log_info "[OK] PostgreSQL 15 + pgvector 安装完成"

    log_info "--- 步骤 5/8: 安装 Python 3.12 ---"
    # Ubuntu 22.04 默认仓库包含 python3.12（从 22.10 起默认，22.04 需 universe 仓库或 deadsnakes PPA）
    if ! command -v python3.12 &>/dev/null; then
        # 尝试 deadsnakes PPA（Ubuntu 22.04 兼容）
        if [[ "$OS_ID" == "ubuntu" ]]; then
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update -qq
        fi
        apt-get install -y --no-install-recommends \
            python3.12 python3.12-venv python3.12-dev
        log_info "[OK] Python 3.12 安装完成"
    else
        log_info "[SKIP] Python 3.12 已安装: $(python3.12 --version)"
    fi

    log_info "--- 步骤 6/8: 安装 Redis、Nginx、系统工具 ---"
    apt-get install -y --no-install-recommends \
        redis-server \
        nginx \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng \
        poppler-utils
    log_info "[OK] Redis / Nginx / FFmpeg / Tesseract / Poppler 安装完成"

    log_info "--- 步骤 7/8: 安装 Node.js 20 LTS ---"
    if ! command -v node &>/dev/null || [[ "$(node --version | cut -d. -f1 | tr -d 'v')" -lt 20 ]]; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y --no-install-recommends nodejs
        log_info "[OK] Node.js $(node --version) 安装完成"
    else
        log_info "[SKIP] Node.js 已满足版本要求: $(node --version)"
    fi
}

# ── 3. dnf/yum 方式安装（CentOS / RHEL / Alibaba Cloud Linux）──────────────
install_dnf() {
    # 统一使用 PKG_MANAGER（dnf 或 yum，由 detect_os 设置）
    local PM="${PKG_MANAGER:-dnf}"
    log_warn "$PM 安装模式（CentOS/RHEL/alinux）— 部分功能需手动验证"

    $PM install -y epel-release 2>/dev/null || true
    $PM install -y \
        python3 python3-devel \
        redis \
        nginx \
        git curl wget make gcc
    log_info "[OK] 基础包安装完成"

    # Python 3.12：alinux/CentOS 仓库可能只有 python3.11/3.9，尝试安装 3.12
    if ! command -v python3.12 &>/dev/null; then
        log_warn "[WARN] python3.12 未找到，尝试从 SCL/IUS 安装（可能失败，请手动安装）"
        $PM install -y python3.12 python3.12-devel 2>/dev/null || true
    fi

    # ffmpeg / tesseract / poppler（EPEL 提供，可能不完整）
    $PM install -y ffmpeg tesseract poppler-utils 2>/dev/null || \
        log_warn "[WARN] ffmpeg/tesseract/poppler 安装失败，如需 OCR/视频功能请手动安装"

    # Node.js 20（NodeSource RPM 脚本，支持 RHEL/CentOS/alinux）
    if ! command -v node &>/dev/null || [[ "$(node --version 2>/dev/null | cut -d. -f1 | tr -d 'v')" -lt 20 ]]; then
        if curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - 2>/dev/null; then
            $PM install -y nodejs
            log_info "[OK] Node.js $(node --version) 安装完成"
        else
            log_warn "[WARN] NodeSource 脚本失败，尝试系统仓库 Node.js（版本可能较旧）"
            $PM install -y nodejs npm 2>/dev/null || true
        fi
    else
        log_info "[SKIP] Node.js 已满足版本要求: $(node --version)"
    fi

    log_info "[OK] $PM 安装阶段完成"
    log_warn "PostgreSQL 15 需单独通过 PGDG rpm 安装: https://www.postgresql.org/download/linux/redhat/"
}

# ── 执行包安装 ────────────────────────────────────────────────────────────────
if [[ "$PKG_MANAGER" == "apt" ]]; then
    install_apt
else
    install_dnf
fi

# ── 4. 启用服务开机自启 ───────────────────────────────────────────────────────
log_info "--- 步骤 8/8: 启用服务开机自启 ---"
systemctl enable postgresql
systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true
systemctl enable nginx
log_info "[OK] 服务开机自启已配置"

# ── 5. 创建部署目录 ───────────────────────────────────────────────────────────
log_info "--- 创建部署目录: $APP_DIR ---"
for subdir in app venv staticfiles media logs; do
    mkdir -p "$APP_DIR/$subdir"
done
# /run/genplatform 用于 Celery PID 文件
mkdir -p /run/genplatform

# ── 6. 创建系统用户 ───────────────────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    log_info "[OK] 系统用户 $APP_USER 创建完成"
else
    log_info "[SKIP] 系统用户 $APP_USER 已存在"
fi

# 设置目录所有者
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chown "$APP_USER:$APP_USER" /run/genplatform
log_info "[OK] 目录所有者设置完成: $APP_DIR -> $APP_USER"

# ── 7. 安装 systemd 服务单元文件 ──────────────────────────────────────────────
SYSTEMD_SRC="$PROJECT_ROOT/deploy/systemd"
SYSTEMD_DEST="/etc/systemd/system"

if [[ -d "$SYSTEMD_SRC" ]]; then
    changed=0
    for svc_file in "$SYSTEMD_SRC"/*.service; do
        svc_name="$(basename "$svc_file")"
        dest_file="$SYSTEMD_DEST/$svc_name"
        if [[ -f "$dest_file" ]] && diff -q "$svc_file" "$dest_file" &>/dev/null; then
            log_info "[SKIP] systemd 服务无变更: $svc_name"
        else
            cp "$svc_file" "$dest_file"
            log_info "[OK]   systemd 服务已更新: $svc_name"
            (( changed++ )) || true
        fi
    done
    if (( changed > 0 )); then
        systemctl daemon-reload
        log_info "[OK] systemctl daemon-reload 完成"
    fi
    systemctl enable genplatform-backend genplatform-celery genplatform-celery-beat
    log_info "[OK] GenPlatform 服务已设置开机自启"
else
    log_warn "[WARN] systemd 服务目录不存在: $SYSTEMD_SRC（跳过服务安装）"
fi

# ── 8. 安装 Nginx 配置 ────────────────────────────────────────────────────────
NGINX_SRC="$PROJECT_ROOT/deploy/nginx/genplatform-physical.conf"

# Ubuntu/Debian 用 sites-available/sites-enabled；CentOS/alinux 用 conf.d
if [[ -d "/etc/nginx/sites-available" ]]; then
    NGINX_CONF_DEST="/etc/nginx/sites-available/genplatform"
    NGINX_ENABLE_DEST="/etc/nginx/sites-enabled/genplatform"
    NGINX_USE_SYMLINK=true
else
    # CentOS / alinux：直接放到 conf.d
    NGINX_CONF_DEST="/etc/nginx/conf.d/genplatform.conf"
    NGINX_ENABLE_DEST=""
    NGINX_USE_SYMLINK=false
    # 删除可能冲突的默认配置
    rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true
fi

if [[ -f "$NGINX_SRC" ]]; then
    cp "$NGINX_SRC" "$NGINX_CONF_DEST"
    if [[ "$NGINX_USE_SYMLINK" == "true" ]]; then
        rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
        ln -sf "$NGINX_CONF_DEST" "$NGINX_ENABLE_DEST"
    fi

    if nginx -t 2>/dev/null; then
        log_info "[OK] Nginx 配置语法检查通过（${NGINX_CONF_DEST}）"
    else
        log_warn "[WARN] Nginx 配置语法检查失败（可能 upstream 服务未启动），继续部署"
    fi
else
    log_warn "[WARN] Nginx 配置文件不存在: $NGINX_SRC（跳过 Nginx 配置）"
fi

log_info "===== 系统依赖安装完成 ====="
log_info "下一步: 复制 .env.example 为 .env 并填写配置，然后运行 'make deploy-physical'"
