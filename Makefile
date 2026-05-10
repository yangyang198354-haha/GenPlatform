# Makefile — GenPlatform 统一操作入口 (MOD-DEPLOY-001)
# 用法: make help
#
# 支持的部署模式:
#   物理机部署 (默认): make deploy-physical
#   Docker 部署 (显式): make deploy-docker
#
# 要求: GNU Make 4.x，Bash 5.x

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

# ── 可配置变量（make target VAR=value 覆盖）──────────────────────────────────
APP_DIR        ?= /opt/genplatform
BRANCH         ?= main
VERSION        ?=
TAG            ?=
SERVICE        ?= backend
COMPOSE_FILE   ?= project_workspace/content_gen_platform/src/docker-compose.yml

# 脚本目录（相对于 Makefile 所在位置）
DEPLOY_SCRIPTS := scripts/deploy
LIB_SCRIPTS    := scripts/lib

# 导出给子脚本的变量
export APP_DIR BRANCH VERSION TAG COMPOSE_FILE

# ── PHONY 声明 ────────────────────────────────────────────────────────────────
.PHONY: help \
        setup-physical validate-config \
        deploy-physical update-physical rollback-physical \
        deploy-docker rollback-docker \
        start-physical stop-physical restart-physical status \
        logs logs-follow \
        smoke-test

# ─────────────────────────────────────────────────────────────────────────────
# help: 输出所有可用 target 说明（自动从注释生成）
# ─────────────────────────────────────────────────────────────────────────────
## 显示帮助信息
help:
	@echo ""
	@echo "GenPlatform 部署工具链"
	@echo "══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "初始化与配置:"
	@echo "  make setup-physical          安装系统依赖（首次使用，需要 sudo）"
	@echo "  make validate-config         校验 .env 配置完整性"
	@echo ""
	@echo "物理机部署（默认）:"
	@echo "  make deploy-physical         首次完整物理机部署"
	@echo "  make update-physical         增量热更新（代码已存在时）"
	@echo "  make rollback-physical       回滚到上次稳定版本"
	@echo "  make rollback-physical VERSION=<commit>  回滚到指定 commit"
	@echo ""
	@echo "Docker 部署（显式指定）:"
	@echo "  make deploy-docker           Docker Compose 方式部署"
	@echo "  make rollback-docker TAG=<tag>  回滚到指定镜像 tag"
	@echo ""
	@echo "服务管理（物理机）:"
	@echo "  make start-physical          启动所有物理机服务"
	@echo "  make stop-physical           停止所有物理机服务"
	@echo "  make restart-physical        重启所有物理机服务"
	@echo "  make status                  查看所有服务运行状态"
	@echo ""
	@echo "日志:"
	@echo "  make logs                    查看所有服务最近日志（100 行）"
	@echo "  make logs SERVICE=<name>     查看指定服务日志（backend/celery/celery-beat）"
	@echo "  make logs-follow SERVICE=<name>  实时跟踪指定服务日志"
	@echo ""
	@echo "测试:"
	@echo "  make smoke-test              执行部署后冒烟测试"
	@echo ""
	@echo "可配置变量（make target VAR=value）:"
	@echo "  APP_DIR      部署目录（默认: /opt/genplatform）"
	@echo "  BRANCH       代码分支（默认: main）"
	@echo "  VERSION      回滚目标 commit（rollback-physical 使用）"
	@echo "  TAG          回滚目标镜像 tag（rollback-docker 使用）"
	@echo "  SERVICE      日志服务名（logs/logs-follow 使用）"
	@echo ""
	@echo "══════════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────────────────────────────────────
# 初始化与配置
# ─────────────────────────────────────────────────────────────────────────────

## 安装系统依赖（首次使用，需要 sudo/root 权限）
setup-physical:
	@echo ">>> 安装系统依赖（需要 root 权限）..."
	sudo bash $(DEPLOY_SCRIPTS)/setup_system.sh

## 校验 .env 配置完整性
validate-config:
	@echo ">>> 校验 .env 配置..."
	bash $(DEPLOY_SCRIPTS)/validate_config.sh

# ─────────────────────────────────────────────────────────────────────────────
# 物理机部署
# ─────────────────────────────────────────────────────────────────────────────

## 首次完整物理机部署（含依赖安装、构建、数据库初始化、服务启动）
deploy-physical:
	@echo ">>> 启动物理机完整部署..."
	bash $(DEPLOY_SCRIPTS)/deploy_physical.sh

## 增量热更新（git pull + 最小化重启）
update-physical:
	@echo ">>> 启动物理机增量热更新..."
	bash $(DEPLOY_SCRIPTS)/update_physical.sh

## 代码回滚（VERSION 未指定时回滚到上次稳定版本）
rollback-physical:
	@echo ">>> 启动物理机回滚 (VERSION=$(VERSION))..."
	bash $(DEPLOY_SCRIPTS)/rollback_physical.sh $(VERSION)

# ─────────────────────────────────────────────────────────────────────────────
# Docker 部署
# ─────────────────────────────────────────────────────────────────────────────

## Docker Compose 方式部署（显式指定）
deploy-docker:
	@echo ">>> 启动 Docker 部署..."
	bash $(DEPLOY_SCRIPTS)/deploy_docker.sh

## Docker 镜像版本回滚（必须指定 TAG）
rollback-docker:
	@if [ -z "$(TAG)" ]; then \
		echo "[ERROR] 必须指定 TAG: make rollback-docker TAG=<image-tag>"; \
		exit 1; \
	fi
	@echo ">>> 启动 Docker 回滚 (TAG=$(TAG))..."
	bash $(DEPLOY_SCRIPTS)/rollback_docker.sh $(TAG)

# ─────────────────────────────────────────────────────────────────────────────
# 服务管理（物理机）
# ─────────────────────────────────────────────────────────────────────────────

## 启动所有物理机服务
start-physical:
	@echo ">>> 启动 GenPlatform 服务..."
	sudo systemctl start genplatform-backend genplatform-celery genplatform-celery-beat
	sudo systemctl reload nginx
	@echo "[OK] 服务已启动"

## 停止所有物理机服务
stop-physical:
	@echo ">>> 停止 GenPlatform 服务..."
	sudo systemctl stop genplatform-backend genplatform-celery genplatform-celery-beat
	@echo "[OK] 服务已停止"

## 重启所有物理机服务
restart-physical:
	@echo ">>> 重启 GenPlatform 服务..."
	sudo systemctl restart genplatform-backend
	sudo systemctl stop genplatform-celery && sudo systemctl start genplatform-celery
	sudo systemctl restart genplatform-celery-beat
	sudo systemctl reload nginx
	@echo "[OK] 服务已重启"

## 查看所有服务运行状态
status:
	@echo "=== GenPlatform 服务状态 ==="
	@echo "--- genplatform-backend ---"
	@systemctl is-active genplatform-backend 2>/dev/null \
		&& systemctl status genplatform-backend --no-pager -n 5 \
		|| echo "(systemd 服务未找到，可能为 Docker 部署)"
	@echo ""
	@echo "--- genplatform-celery ---"
	@systemctl is-active genplatform-celery 2>/dev/null \
		&& systemctl status genplatform-celery --no-pager -n 5 \
		|| echo "(systemd 服务未找到)"
	@echo ""
	@echo "--- genplatform-celery-beat ---"
	@systemctl is-active genplatform-celery-beat 2>/dev/null \
		&& systemctl status genplatform-celery-beat --no-pager -n 5 \
		|| echo "(systemd 服务未找到)"
	@echo ""
	@echo "--- nginx ---"
	@systemctl is-active nginx 2>/dev/null \
		&& systemctl status nginx --no-pager -n 3 \
		|| echo "(nginx 未运行)"

# ─────────────────────────────────────────────────────────────────────────────
# 日志查看
# ─────────────────────────────────────────────────────────────────────────────

# 服务名到 systemd unit 的映射
_svc_unit = $(shell \
	case "$(SERVICE)" in \
		backend)    echo genplatform-backend ;; \
		celery|celery_worker) echo genplatform-celery ;; \
		celery-beat|celery_beat) echo genplatform-celery-beat ;; \
		nginx)      echo nginx ;; \
		*)          echo genplatform-backend ;; \
	esac)

## 查看服务最近日志（100 行）
logs:
	@echo ">>> 查看服务日志: $(SERVICE) (unit: $(_svc_unit))"
	@journalctl -u $(_svc_unit) -n 100 --no-pager 2>/dev/null \
		|| (echo "journald 不可用，尝试读取文件日志..."; \
		    tail -n 100 $(APP_DIR)/logs/*.log 2>/dev/null || echo "日志文件不存在")

## 实时跟踪服务日志
logs-follow:
	@echo ">>> 实时跟踪服务日志: $(SERVICE) (unit: $(_svc_unit))  Ctrl+C 退出"
	@journalctl -u $(_svc_unit) -f 2>/dev/null \
		|| tail -f $(APP_DIR)/logs/gunicorn.log 2>/dev/null \
		|| echo "journald 不可用且文件日志不存在"

# ─────────────────────────────────────────────────────────────────────────────
# 测试
# ─────────────────────────────────────────────────────────────────────────────

## 执行部署后冒烟测试
smoke-test:
	@echo ">>> 执行冒烟测试..."
	bash $(DEPLOY_SCRIPTS)/smoke_test.sh
