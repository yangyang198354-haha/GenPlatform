<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-04-06T01:41:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <phase>PHASE_11</phase>
  <status>APPROVED</status>
</file_header>

# 部署计划 — 内容生成平台

> ⚠️ **生产部署须由 PM 获得用户明确授权（PRODUCTION_DEPLOY_CONFIRM=true）后方可执行。**

---

## DEPLOY-001：初始化服务器环境
**描述**：在目标服务器上安装 Docker、Docker Compose、FFmpeg，创建部署目录。  
**执行命令**：
```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 ffmpeg
sudo mkdir -p /opt/content-gen-platform
sudo chown deploy:deploy /opt/content-gen-platform
```
**验收标准**：`docker --version` 和 `ffmpeg -version` 均返回版本号。  
**ROLLBACK-001**：无需回滚（安装操作可幂等重执行）。

---

## DEPLOY-002：配置环境变量文件
**描述**：创建 `/opt/content-gen-platform/.env` 文件，填入所有必需环境变量。  
**必填变量清单**：
```
DJANGO_SECRET_KEY=<强随机字符串，≥50字符>
ENCRYPTION_KEY=<32字节 AES 密钥，base64编码>
POSTGRES_PASSWORD=<强密码>
ALLOWED_HOSTS=<服务器域名/IP>
CORS_ALLOWED_ORIGINS=https://<前端域名>
```
**验收标准**：`.env` 文件存在，权限为 600（仅 deploy 用户可读）。  
**ROLLBACK-002**：删除 `.env` 文件，服务不可启动（阻止意外部署）。

---

## DEPLOY-003：部署数据库（PostgreSQL + pgvector）
**描述**：启动 PostgreSQL 容器并验证 pgvector 扩展可用。  
**执行命令**：
```bash
cd /opt/content-gen-platform
docker compose up -d db
docker compose exec db psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec db psql -U postgres -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```
**验收标准**：psql 查询返回 `vector` 行。  
**ROLLBACK-003**：
```bash
docker compose stop db
docker volume rm content-gen-platform_pgdata
```
⚠️ 注意：回滚会删除所有数据，仅在 DEPLOY-003 阶段失败时执行（无业务数据时安全）。

---

## DEPLOY-004：执行数据库迁移
**描述**：运行 Django migrations，创建所有表结构和索引。  
**执行命令**：
```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py migrate --check  # 验证无待执行 migration
```
**验收标准**：`migrate --check` 返回 0 exit code。  
**ROLLBACK-004**：
```bash
docker compose run --rm backend python manage.py migrate <app_name> <previous_migration>
```

---

## DEPLOY-005：启动全栈服务
**描述**：启动所有服务容器（backend、celery、frontend、nginx）。  
**执行命令**：
```bash
docker compose up -d
docker compose ps  # 验证所有服务 running
```
**验收标准**：所有容器状态为 `running`，健康检查通过。  
**ROLLBACK-005**：
```bash
docker compose down
# 恢复到上一版本镜像
docker compose up -d --scale backend=0 && docker pull <previous_tag> && docker compose up -d
```

---

## DEPLOY-006：验证部署（Post-Deploy Verification）
**描述**：对关键接口执行烟雾测试，验证服务正常响应。  
**验收脚本**：
```bash
# Health check
curl -f http://localhost/api/v1/auth/login/ -X POST -d '{}' | grep -v "500"

# Verify static files
curl -f http://localhost/ | grep -q "Content Gen Platform"

# Verify WebSocket endpoint
wscat -c ws://localhost/ws/notifications/ && echo "WS OK"

# Verify Celery worker
docker compose exec celery_worker celery -A config inspect active
```
**验收标准**：所有 curl 命令返回非 500 状态，WebSocket 连接建立，Celery worker 活跃。  
**ROLLBACK-006**：触发 ROLLBACK-005（停止服务，回滚镜像）。

---

## 回滚总结

| 步骤 | 可回滚 | 数据影响 |
|------|--------|---------|
| DEPLOY-001 | ✅ 幂等 | 无 |
| DEPLOY-002 | ✅ 删除文件 | 无 |
| DEPLOY-003 | ✅ 删除卷（仅初始化时安全） | 无（初始状态） |
| DEPLOY-004 | ✅ 指定迁移回滚 | 低风险 |
| DEPLOY-005 | ✅ 回滚镜像版本 | 无（数据在 DB/Volume 中持久） |
| DEPLOY-006 | ✅ 触发 ROLLBACK-005 | 无 |
