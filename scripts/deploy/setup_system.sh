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

    # ── 预修复：之前残留的 PGDG 仓库在 alinux3 上路径错误 ─────────────────────
    # alinux3 的 $releasever=3，但 PGDG 镜像路径是 rhel-8/，导致 404
    # 任何旧的 pgdg-*.repo 都会让 dnf 在 metadata refresh 阶段失败，阻塞所有安装
    log_info "检查并修复残留的 PGDG 仓库（alinux3 路径兼容性）..."
    for repo_file in /etc/yum.repos.d/pgdg-*.repo; do
        [[ ! -f "$repo_file" ]] && continue
        # 把 $releasever 和数字版本（如 rhel-3-）替换为 rhel-8
        sed -i \
            -e 's|/redhat/rhel-\$releasever-|/redhat/rhel-8-|g' \
            -e 's|/redhat/rhel-[0-9]\+-|/redhat/rhel-8-|g' \
            "$repo_file" 2>/dev/null || true
        log_info "[OK] 已修复仓库路径: $repo_file"
    done
    # 清理 dnf 缓存以丢弃 404 缓存的 metadata
    $PM clean all 2>/dev/null || true

    $PM install -y epel-release 2>/dev/null || true
    $PM install -y \
        python3 python3-devel \
        redis \
        nginx \
        git curl wget make gcc || {
        log_warn "[WARN] 包安装被中断（可能内存不足），尝试逐个安装..."
        for pkg in python3 python3-devel redis nginx git curl wget make gcc; do
            $PM install -y "$pkg" 2>/dev/null || log_warn "[WARN] 安装失败（跳过）: $pkg"
        done
    }
    log_info "[OK] 基础包安装完成"

    # Python 3.9+（PyTorch 2.x 最低要求）
    # alinux3/RHEL8: python3.9 通过 AppStream 模块流提供，python3.11+ 可能不直接可用
    _install_python_rhel() {
        local PM="$1"
        # 尝试直接安装各版本（含 pip 子包，alinux3 上 python3.x-pip 是单独分包）
        for pkg in python3.12 python3.11 python39 python3.9; do
            if $PM install -y "$pkg" "${pkg}-devel" 2>/dev/null; then
                # 顺带装 pip 子包（如不存在会失败但不影响主流程，源码编译版自带 pip）
                $PM install -y "${pkg}-pip" "${pkg}-setuptools" 2>/dev/null || true
                return 0
            fi
        done
        # 尝试通过 AppStream 模块流启用 Python 3.9
        if $PM module enable -y python39 2>/dev/null; then
            if $PM install -y python39 python39-devel 2>/dev/null; then
                $PM install -y python39-pip python39-setuptools 2>/dev/null || true
                return 0
            fi
        fi
        # 最后手段：从 python.org 编译安装 Python 3.11
        log_warn "[WARN] 包管理器无法提供 Python 3.9+，从源码编译 Python 3.11（约 5-10 分钟）..."
        # 安装编译依赖（不静默错误，便于诊断）
        log_info "安装 Python 编译依赖（zlib-devel/openssl-devel 是必需）..."
        # OpenSSL（多种包名可能）
        local OPENSSL_INSTALLED=false
        for ossl_pkg in openssl-devel openssl11-devel; do
            if $PM install -y "$ossl_pkg"; then
                OPENSSL_INSTALLED=true
                log_info "[OK] OpenSSL dev 已安装: $ossl_pkg"
                break
            fi
        done
        # 关键编译依赖（任何一个失败都会导致 Python 模块缺失）
        # zlib-devel: ensurepip 解压 wheel 必需
        # libffi-devel: ctypes 模块必需（Django/torch 依赖）
        $PM install -y zlib-devel bzip2-devel libffi-devel xz-devel \
            readline-devel sqlite-devel ncurses-devel || {
            log_error "Python 编译依赖安装失败（zlib-devel/libffi-devel 等）"
            return 1
        }
        # 验证关键头文件
        if [[ ! -f /usr/include/zlib.h ]]; then
            log_error "zlib.h 未找到！Python 编译会失败（ensurepip 依赖 zlib 解压 wheel）"
            log_error "请手动: $PM install -y zlib-devel"
            return 1
        fi
        if [[ "$OPENSSL_INSTALLED" != "true" ]] && ! ls /usr/include/openssl/ssl.h 2>/dev/null; then
            log_error "openssl/ssl.h 未找到！Python 将无 SSL 支持，pip 无法访问 HTTPS PyPI"
            return 1
        fi
        log_info "[OK] zlib.h 和 openssl/ssl.h 头文件已就位"
        # 清理任何旧的不完整 Python 安装（避免半装的 binary 被误认为成功）
        rm -f /usr/local/bin/python3.11 /usr/local/bin/pip3.11 \
              /usr/local/bin/idle3.11 /usr/local/bin/2to3-3.11 \
              /usr/local/bin/pydoc3.11 /usr/local/bin/python3.11-config 2>/dev/null || true
        local PY_VER="3.11.9"
        local PY_SRC="/tmp/Python-${PY_VER}"
        curl -fsSL "https://www.python.org/ftp/python/${PY_VER}/Python-${PY_VER}.tar.xz" \
            -o "/tmp/Python-${PY_VER}.tar.xz" || return 1
        tar xf "/tmp/Python-${PY_VER}.tar.xz" -C /tmp/
        cd "$PY_SRC"
        # 不静默 configure/make（让缺模块问题暴露）；altinstall 失败 → set -e 退出
        ./configure --enable-optimizations --prefix=/usr/local --with-ensurepip=install
        make -j"$(nproc)"
        make altinstall
        cd /tmp
        rm -rf "$PY_SRC" "/tmp/Python-${PY_VER}.tar.xz"
        # 验证关键模块（ssl/zlib/hashlib/ctypes 缺一不可）
        if ! command -v python3.11 &>/dev/null; then
            log_error "python3.11 编译失败，未生成 binary"
            return 1
        fi
        if ! python3.11 -c "import ssl, zlib, hashlib, ctypes; print('[OK] SSL:', ssl.OPENSSL_VERSION)"; then
            log_error "Python 3.11 关键模块缺失（ssl/zlib/hashlib/ctypes 之一）"
            return 1
        fi
        log_info "[OK] Python 3.11 编译成功，所有关键模块就绪"
        return 0
    }
    # 检测已有 Python 是否完整（同时校验 ssl + zlib，缺一即重编译）
    NEED_PY=true
    for pv in python3.12 python3.11 python3.10 python3.9; do
        if command -v "$pv" &>/dev/null; then
            if "$pv" -c "import ssl, zlib" 2>/dev/null; then
                NEED_PY=false
                break
            else
                log_warn "[WARN] $pv 缺少 ssl 或 zlib 模块（编译依赖未装全），将清理并重新编译..."
                PY_MINOR="${pv##python}"
                rm -f "/usr/local/bin/${pv}" "/usr/local/bin/pip${PY_MINOR}" \
                       "/usr/local/bin/idle${PY_MINOR}" "/usr/local/bin/2to3-${PY_MINOR}" \
                       "/usr/local/bin/pydoc${PY_MINOR}" "/usr/local/bin/${pv}-config" \
                       "/usr/local/bin/python3" "/usr/local/bin/pip3" 2>/dev/null || true
                break
            fi
        fi
    done
    if [[ "$NEED_PY" == "true" ]]; then
        # 不能用 || log_warn —— 那会让 set -e 失效，错误被吞
        if ! _install_python_rhel "$PM"; then
            log_error "Python 3.9+ 安装失败，部署无法继续"
            log_error "请检查上方日志中的依赖安装错误（zlib-devel / openssl-devel）"
            exit 1
        fi
    fi
    # 汇报实际可用版本
    for pv in python3.12 python3.11 python3.10 python3.9; do
        if command -v "$pv" &>/dev/null; then
            log_info "[OK] Python 可用: $pv ($($pv --version 2>&1))"
            break
        fi
    done

    # PostgreSQL 15 + pgvector（PGDG rpm 官方源；中国服务器降级到 Aliyun 镜像）
    log_info "--- 安装 PostgreSQL 15 + pgvector（PGDG 源）---"
    # RHEL 8 / alinux3 / CentOS Stream 8 均兼容 EL-8 包
    # 中国境内 download.postgresql.org 不稳定，先尝试官方，失败后用 Aliyun 镜像
    local PGDG_OFFICIAL="https://download.postgresql.org/pub/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm"
    local PGDG_ALIYUN="https://mirrors.aliyun.com/postgresql/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm"
    if ! $PM install -y "$PGDG_OFFICIAL" 2>/dev/null; then
        log_warn "[WARN] 官方 PGDG 仓库不可达，使用 Aliyun 镜像..."
        $PM install -y "$PGDG_ALIYUN" || {
            log_error "PGDG 仓库安装失败（官方+Aliyun 都失败），无法安装 PostgreSQL 15"
            return 1
        }
        # 把 baseurl 改为 Aliyun 镜像（仓库 metadata 仍指向官方）
        if [[ -d /etc/yum.repos.d ]]; then
            sed -i 's|https://download.postgresql.org/pub/repos/yum|https://mirrors.aliyun.com/postgresql/repos/yum|g' \
                /etc/yum.repos.d/pgdg-redhat-all.repo 2>/dev/null || true
        fi
    fi
    # 立刻修复 alinux3 路径问题（$releasever=3，但 PGDG 实际路径是 rhel-8）
    for repo_file in /etc/yum.repos.d/pgdg-*.repo; do
        [[ ! -f "$repo_file" ]] && continue
        sed -i \
            -e 's|/redhat/rhel-\$releasever-|/redhat/rhel-8-|g' \
            -e 's|/redhat/rhel-[0-9]\+-|/redhat/rhel-8-|g' \
            "$repo_file" 2>/dev/null || true
    done
    $PM clean all 2>/dev/null || true
    # 禁用系统内置的 postgresql 模块，避免版本冲突
    $PM -qy module disable postgresql 2>/dev/null || true
    if ! $PM install -y postgresql15-server postgresql15-contrib; then
        log_error "PostgreSQL 15 安装失败，部署无法继续（deploy_physical.sh step 7 需要 DB 连接）"
        return 1
    fi
    log_info "[OK] PostgreSQL 15 安装完成"
    if command -v pg_config &>/dev/null || [ -f /usr/pgsql-15/bin/pg_config ]; then
        # pgvector（依赖 postgresql15-devel）
        $PM install -y postgresql15-devel 2>/dev/null || true
        $PM install -y pgvector_15 2>/dev/null || \
            log_warn "[WARN] pgvector_15 安装失败（可能 PGDG 尚未提供），向量检索功能需手动安装"
        # 初始化 PostgreSQL 数据目录（首次必须）
        if [ ! -f /var/lib/pgsql/15/data/PG_VERSION ]; then
            /usr/pgsql-15/bin/postgresql-15-setup initdb 2>/dev/null || true
        fi
    fi

    # 启动 PostgreSQL 15（initdb 后必须先启动才能接受连接）
    if command -v pg_config &>/dev/null || [ -f /usr/pgsql-15/bin/pg_config ]; then
        systemctl enable postgresql-15 2>/dev/null || true
        systemctl start postgresql-15 2>/dev/null || \
            log_warn "[WARN] PostgreSQL 15 启动失败，deploy_physical.sh 将尝试重新启动"
        log_info "[OK] PostgreSQL 15 已启动"
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

    # 启动 Redis（deploy_physical.sh 步骤 10 需要 Redis 运行）
    systemctl enable redis 2>/dev/null || systemctl enable redis-server 2>/dev/null || true
    systemctl start redis 2>/dev/null || systemctl start redis-server 2>/dev/null || \
        log_warn "[WARN] Redis 启动失败，请手动检查"

    # 启动 Nginx（配置文件安装后需要先验证再启动）
    systemctl enable nginx 2>/dev/null || true
    # Nginx 实际启动延迟到配置安装后（见下方步骤 8）

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
# postgresql 在 alinux 上服务名可能为 postgresql-15
systemctl enable postgresql-15 2>/dev/null || systemctl enable postgresql 2>/dev/null || \
    log_warn "[WARN] postgresql 服务未找到，请确认 PostgreSQL 安装是否成功"
systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true
systemctl enable nginx 2>/dev/null || true
log_info "[OK] 服务开机自启已配置（失败项见上方警告）"

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
        # 启动/重载 Nginx（配置验证通过后才启动，避免配置错误导致 Nginx 拒绝启动）
        systemctl start nginx 2>/dev/null || systemctl reload nginx 2>/dev/null || \
            log_warn "[WARN] Nginx 启动失败，请检查 systemd 日志"
    else
        log_warn "[WARN] Nginx 配置语法检查失败（可能 upstream 服务未启动），跳过 Nginx 启动"
        log_warn "       部署完成后手动执行: nginx -t && systemctl start nginx"
    fi
else
    log_warn "[WARN] Nginx 配置文件不存在: $NGINX_SRC（跳过 Nginx 配置）"
fi

log_info "===== 系统依赖安装完成 ====="
log_info "下一步: 复制 .env.example 为 .env 并填写配置，然后运行 'make deploy-physical'"
