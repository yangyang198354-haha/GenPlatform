# 生产部署计划 — GenPlatform KB Extension
<!--
  file: deployment_plan.md
  author_agent: main_agent_pm
  project: genplatform_kb_extension
  phase: GROUP_E / PHASE_11
  created_at: 2026-04-16T11:00:00Z
  status: APPROVED
-->

---

## 1. 部署范围

本次部署包含 KB 功能扩展的三项新功能：
- **F-01**：批量上传（`POST /api/v1/knowledge/documents/batch-upload/`）
- **F-02**：用户隔离（ORM 层，无 Schema 变更）
- **F-03**：默认文件名 + 重命名（`PATCH /api/v1/knowledge/documents/{pk}/`，无 Schema 变更）

**无数据库 Schema 变更**（无新 migration），本次部署为零停机热更新。

---

## 2. 部署前提条件（Pre-flight Checklist）

部署负责人在执行生产部署前必须逐项确认：

| 编号 | 检查项 | 验证方式 | 状态 |
|-----|-------|---------|------|
| PRE-01 | CI 流水线 Stage 1-6 全部通过（绿色） | GitHub Actions 页面确认 | [ ] |
| PRE-02 | `main` 分支 HEAD SHA 与待部署镜像 tag 一致 | GHCR 镜像页面 | [ ] |
| PRE-03 | 数据库备份已完成（部署前 ≤1h） | 备份存储确认 | [ ] |
| PRE-04 | 生产服务器磁盘空间 ≥ 5GB（后端镜像含 PyTorch ~2GB） | `df -h /` | [ ] |
| PRE-05 | 当前生产版本 image tag 已记录（用于回滚） | 见第4节 | [ ] |
| PRE-06 | 告知相关团队维护窗口（如有） | 通知记录 | [ ] |

---

## 3. 数据库迁移步骤

> **本次部署无新 migration**（KB 三项新功能均在现有 Schema 基础上实现）。
>
> `migrate` 命令仍在 backend 容器 CMD 中自动执行（`manage.py migrate && gunicorn ...`），这一步会检查所有 migration 状态并在 `django_migrations` 表确认无待执行项，属于安全空操作。

### 如后续迭代存在 migration 时的标准步骤

1. **迁移前备份**（必须）：
   ```bash
   # 在生产服务器执行
   docker exec $(docker compose ps -q db) \
     pg_dump -U postgres content_gen_platform \
     > /opt/backups/pre_migration_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **单独运行 migration**（可选，用于验证）：
   ```bash
   docker run --rm \
     --network content-gen-platform_default \
     -e DJANGO_SETTINGS_MODULE=config.settings.production \
     -e DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY} \
     -e ENCRYPTION_KEY=${ENCRYPTION_KEY} \
     -e POSTGRES_HOST=db \
     -e POSTGRES_DB=content_gen_platform \
     -e POSTGRES_USER=postgres \
     -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} \
     ghcr.io/{owner}/{repo}/backend:{sha} \
     python manage.py migrate --plan
   ```

3. **确认无破坏性变更**：检查 migration plan 中无 `DeleteModel`、无 `RemoveField`（非空列）。

4. **执行迁移**（容器启动时自动执行，或手动）。

5. **验证迁移完成**：
   ```bash
   docker exec $(docker compose ps -q backend) \
     python manage.py showmigrations | grep -v "\[X\]" | grep -v "^$"
   # 预期：空输出（所有 migration 均已应用）
   ```

---

## 4. 部署执行步骤

### Step 1：记录当前生产版本（用于回滚）

```bash
# 在生产服务器执行
cd /opt/content-gen-platform
ROLLBACK_TAG=$(docker compose images backend --format json | python3 -c "
import json,sys
data=json.load(sys.stdin)
print(data[0]['Tag'] if data else 'unknown')
")
echo "ROLLBACK_TAG=$ROLLBACK_TAG" | tee /opt/backups/rollback_$(date +%Y%m%d_%H%M%S).env
```

### Step 2：通过 GitHub Actions 触发部署

1. 登录 GitHub → Actions 页面
2. 找到最新 `main` 分支的 CI/CD Pipeline 运行记录
3. 确认 Stage 1-6 全部通过（绿色）
4. 点击 **Stage 7: Deploy to Production** 的 "Review deployments" 按钮
5. 选择 `production` environment，点击 **Approve and deploy**

GitHub Actions 将自动执行：
- SCP 上传 `docker-compose.yml` + nginx 配置
- `docker compose pull` 拉取新镜像
- `docker compose up -d --remove-orphans`
- 等待 gunicorn 就绪（最长 300s）

### Step 3：等待并观察部署进度

在 GitHub Actions 日志中观察以下关键日志行：

```
# 容器就绪
container running at step N

# gunicorn 就绪（任意 HTTP 码）
gunicorn ready — HTTP 200   (或 400/401/422)

# 生产部署成功
Production deploy OK

# celery worker 模型加载（最后一行）
--- Celery worker startup logs ---
```

预期总耗时：首次部署 5-8 分钟（含 migrate + 模型加载），更新部署 2-4 分钟。

---

## 5. 部署后健康检查

部署流水线完成后（Stage 8 + Stage 9），手动执行以下验证：

### 5.1 自动健康检查（流水线内）

| 检查 | 执行阶段 | 预期结果 |
|-----|---------|---------|
| `POST /api/v1/auth/login/` gunicorn 响应 | Stage 7 内嵌 | HTTP 200/400/401/422 |
| `POST /api/v1/knowledge/documents/batch-upload/` 端点可路由 | Stage 8 smoke_test | HTTP 401（需认证） |
| `GET /api/v1/knowledge/documents/` 端点可路由 | Stage 8 smoke_test | HTTP 401（需认证） |
| E2E: 目录上传完整流程 | Stage 9 Playwright | 通过 |
| E2E: 重命名流程 | Stage 9 Playwright | 通过 |
| E2E: 用户隔离 | Stage 9 Playwright | 通过 |

### 5.2 手动验证清单（部署负责人执行）

```bash
# 1. 确认所有容器运行中
cd /opt/content-gen-platform
docker compose ps
# 预期：backend, db, redis, celery_worker, celery_beat, frontend, nginx 均为 Up

# 2. 确认无 migration 待执行
docker compose exec backend python manage.py showmigrations | grep -v "\[X\]"
# 预期：空输出

# 3. 测试批量上传端点（需要有效 JWT，此处仅验证路由）
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost/api/v1/knowledge/documents/batch-upload/
# 预期：401

# 4. 确认 celery worker 已连接
docker compose exec backend \
  celery -A config inspect active --timeout 5
# 预期：返回 worker 列表（非空）

# 5. 确认嵌入模型已加载（查看 worker 日志）
docker compose logs celery_worker | grep "SentenceTransformer\|bge-small"
# 预期：包含模型加载成功日志
```

---

## 6. 回滚方案

### 6.1 触发回滚的条件

以下任一情况发生时立即启动回滚：
- Stage 7（部署）失败（GitHub Actions 标红）
- Stage 8（Smoke Tests）失败
- Stage 9（E2E）失败且判断为生产代码引入的 regression
- 生产监控发现错误率 > 5%（部署后 30 分钟内）
- 生产 HTTP 5xx 率显著上升

### 6.2 快速回滚步骤（目标：5 分钟内完成）

```bash
# 在生产服务器执行
cd /opt/content-gen-platform

# ── Step 1: 找到上一个版本的 tag ──
# 方式A：从回滚记录文件读取
ROLLBACK_TAG=$(cat /opt/backups/rollback_latest.env | grep ROLLBACK_TAG | cut -d= -f2)

# 方式B：从 GHCR 镜像历史中找 SHA
# 在本地执行：git log --oneline -5 可找到上一个 commit SHA

# ── Step 2: 修改 docker-compose.yml 或用环境变量覆盖镜像 tag ──
# 快速方式：直接拉取并重新启动上一版本

# ── Step 3: 更新镜像 tag 并重启 ──
export BACKEND_TAG=${ROLLBACK_TAG}
export FRONTEND_TAG=${ROLLBACK_TAG}

# 拉取旧版本镜像（应已存在本地 cache）
docker pull ghcr.io/yangyang198354-haha/genplatform/backend:${ROLLBACK_TAG} || \
  echo "WARNING: old image not in cache, pulling from GHCR"

# 修改 compose 文件中的 image tag（用 sed 快速替换）
sed -i "s|/backend:latest|/backend:${ROLLBACK_TAG}|g" docker-compose.yml
sed -i "s|/frontend:latest|/frontend:${ROLLBACK_TAG}|g" docker-compose.yml

# 重启服务
docker compose up -d --remove-orphans

# ── Step 4: 验证回滚成功 ──
for i in $(seq 1 12); do
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" -d '{}' \
    http://localhost/api/v1/auth/login/ 2>/dev/null || echo "000")
  case "$HTTP" in
    200|400|401|422)
      echo "Rollback OK — HTTP $HTTP"
      break
      ;;
  esac
  echo "Waiting... ($i/12) HTTP=$HTTP"
  sleep 5
done
```

### 6.3 无需回滚的场景

- `.env` 配置问题（修改 `.env` 后 `docker compose restart backend` 即可）
- Celery worker 崩溃（`docker compose restart celery_worker`）
- Nginx 配置问题（`docker compose restart nginx`）

### 6.4 数据库回滚（仅含 migration 的部署）

> **本次部署无 migration，此节仅供后续参考。**

若新版本包含破坏性 migration 且必须回滚：
```bash
# 将 migration 回退到上一个版本
docker compose exec backend \
  python manage.py migrate knowledge_base <上一个 migration 编号>

# 确认回退成功
docker compose exec backend \
  python manage.py showmigrations knowledge_base
```

**注意**：含数据删除的 migration 一旦执行，数据层面无法自动回滚，只能从备份恢复。

---

## 7. 紧急联系

| 角色 | 责任 | 联系方式 |
|-----|-----|---------|
| 部署负责人 | 执行部署、确认健康检查 | 项目内部通讯 |
| 后端负责人 | 判断是否回滚、排查服务异常 | 项目内部通讯 |
| 基础设施 | ECS 服务器访问、网络问题 | 阿里云控制台 |

---

## 8. 部署记录模板

每次生产部署完成后填写：

```
部署日期：____________________
部署人员：____________________
部署 SHA：____________________
部署镜像 Tag：________________
Pre-flight 通过：[ ] 是  [ ] 否
部署结果：   [ ] 成功  [ ] 回滚
Smoke Test：[ ] 通过  [ ] 失败
E2E Test：  [ ] 通过  [ ] 失败  [ ] 跳过
备注：____________________
```
