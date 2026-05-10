# 部署计划 — GenPlatform 物理机部署工具链

**文档版本**: v1.0.0
**编制时间**: 2026-05-10
**项目**: GenPlatform（内容生成平台）
**本次目标**: 提交物理机部署工具链到 GitHub，并在生产服务器执行物理机部署

---

## 1. 本次变更范围

### 1.1 新增文件清单

| 文件路径 | 说明 |
|---------|------|
| `Makefile` | 统一操作入口，封装所有部署、管理、测试命令 |
| `scripts/lib/common.sh` | 公共函数库（日志、颜色、工具函数） |
| `scripts/deploy/setup_system.sh` | 首次系统依赖安装脚本 |
| `scripts/deploy/deploy_physical.sh` | 物理机首次完整部署脚本 |
| `scripts/deploy/update_physical.sh` | 物理机增量热更新脚本 |
| `scripts/deploy/rollback_physical.sh` | 物理机版本回滚脚本 |
| `scripts/deploy/deploy_docker.sh` | Docker Compose 部署脚本 |
| `scripts/deploy/rollback_docker.sh` | Docker 镜像版本回滚脚本 |
| `scripts/deploy/validate_config.sh` | .env 配置完整性校验脚本 |
| `scripts/deploy/smoke_test.sh` | 部署后冒烟测试脚本（4 项检查） |
| `deploy/systemd/genplatform-backend.service` | Django/Gunicorn systemd 服务单元 |
| `deploy/systemd/genplatform-celery.service` | Celery Worker systemd 服务单元 |
| `deploy/systemd/genplatform-celery-beat.service` | Celery Beat systemd 服务单元 |
| `deploy/nginx/genplatform-physical.conf` | Nginx 反向代理配置（物理机） |
| `.env.example` | 环境变量模板 |
| `project_workspace/.../docs/deployment/requirements_spec.md` | 部署需求规格说明 |
| `project_workspace/.../docs/deployment/user_stories.md` | 用户故事 |
| `project_workspace/.../docs/deployment/architecture_design.md` | 架构设计 |
| `project_workspace/.../docs/deployment/module_design.md` | 模块设计 |
| `project_workspace/.../docs/deployment/tech_stack.md` | 技术栈说明 |

### 1.2 变更影响评估

- **影响范围**: 仅新增文件，不修改任何现有代码、配置或测试
- **向后兼容**: 完全兼容，Docker 部署路径不受影响
- **风险级别**: 低（本次 commit 为纯工具链新增）

---

## 2. GROUP_D-1：Git 提交推送计划

### 2.1 执行步骤

1. 运行 `git status`，确认 20 个目标文件均在 Untracked 列表中
2. 精确 `git add` 上述文件（不使用 `git add -A` 以避免误加入非目标文件）
3. `git commit`（pre-commit hook 将自动执行 `pytest apps/ tests/ -m "not integration and not django_db"`）
4. 确认测试全部通过后，`git push origin main`

### 2.2 Commit Message

```
feat(deploy): add physical deployment toolchain alongside Docker
```

### 2.3 Pre-commit Hook 说明

- Hook 路径: `.git/hooks/pre-commit`
- 执行命令: `python -m pytest apps/ tests/ -m "not integration and not django_db"`
- 工作目录: `project_workspace/content_gen_platform/src/backend`
- 本次新增文件全为 shell 脚本 / Makefile / Markdown / systemd / nginx 配置，pytest 不会扫描，hook 应正常通过
- **约束**: 如 hook 失败，必须报告错误，禁止使用 `--no-verify` 跳过

---

## 3. GROUP_D-2：生产环境物理机部署计划

### 3.1 前置条件确认（执行前必须核查）

| 检查项 | 状态 |
|--------|------|
| 生产服务器 SSH 连接信息已知 | 待用户确认 |
| 生产服务器 `/opt/genplatform/.env` 已配置 | 待用户确认 |
| 是否为首次物理机部署（需要 setup_system.sh）| 待用户确认 |
| 生产服务器已安装 git、make、bash 5.x | 待用户确认 |

### 3.2 部署执行顺序

**场景 A：首次物理机部署**

```bash
# Step 1: 拉取最新代码
cd /opt/genplatform
git pull origin main

# Step 2: 校验 .env 配置
make validate-config

# Step 3: 安装系统依赖（需要 root）
sudo bash scripts/deploy/setup_system.sh

# Step 4: 执行完整部署
make deploy-physical

# Step 5: 冒烟测试验证
make smoke-test
```

**场景 B：已有物理机部署环境（增量热更新）**

```bash
# Step 1: 拉取最新代码
cd /opt/genplatform
git pull origin main

# Step 2: 校验 .env 配置
make validate-config

# Step 3: 增量热更新
make update-physical

# Step 4: 冒烟测试验证
make smoke-test
```

### 3.3 回滚预案

| 场景 | 回滚命令 |
|------|---------|
| 物理机部署失败，回滚到上次稳定版本 | `make rollback-physical` |
| 物理机部署失败，回滚到指定 commit | `make rollback-physical VERSION=<commit-hash>` |
| Docker 部署回滚 | `make rollback-docker TAG=<image-tag>` |

### 3.4 冒烟测试覆盖项

| 测试项 | 验证内容 | 通过标准 |
|--------|---------|---------|
| 测试 1/4 | Django API 健康检查 | `GET /api/v1/auth/login/` 返回非 5xx |
| 测试 2/4 | 前端静态文件服务 | `GET /` 响应含 `<!DOCTYPE html>` |
| 测试 3/4 | Celery Worker 活跃 | `systemctl genplatform-celery` 状态为 active |
| 测试 4/4 | 数据库连接检查 | `manage.py check --database default` 无报错 |

---

## 4. 风险控制

| 风险 | 缓解措施 |
|------|---------|
| Push 到 GitHub 影响共享仓库 | 精确 add 目标文件，提交前确认 git status |
| Pre-commit hook 失败 | 报告错误信息，禁止 --no-verify |
| 生产服务器 .env 未配置 | validate-config 失败会中止部署，优先配置 .env |
| 物理机部署失败 | 每个关键步骤有回滚预案，smoke-test 失败自动提示回滚命令 |
| 生产部署属于高风险操作 | 必须收到用户明确 CONFIRM 信号后才执行 SSH 远程命令 |

---

## 5. 授权要求

- **GROUP_D-1（git commit + push）**: 无需额外授权，可立即执行
- **GROUP_D-2（生产服务器部署）**: 必须由用户提供以下信息并明确 CONFIRM 后执行：
  - 生产服务器 SSH 用户、IP、端口
  - 确认 .env 已配置
  - 确认是首次部署还是增量更新
  - 明确输入 `CONFIRM` 授权生产部署
