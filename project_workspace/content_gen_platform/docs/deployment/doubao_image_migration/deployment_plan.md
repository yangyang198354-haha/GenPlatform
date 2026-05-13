# 生产部署计划 — 豆包 Seedream 图片生成接入

**文档版本**：v1.0 DRAFT
**所属迁移**：doubao_image_migration
**编写日期**：2026-05-13
**目标环境**：阿里云 ECS，Alibaba Cloud Linux 3（alinux3）
**部署管理**：systemd（gunicorn + celery-worker）
**状态**：DRAFT（待 PM 门控评审）

> **重要**：本文档描述部署计划，**不执行**任何实际部署动作。真实部署前，必须收到项目经理和用户对本文档的明确 CONFIRM 授权信号。

---

## 目录

1. [前置检查清单](#1-前置检查清单)
2. [部署步骤](#2-部署步骤)
3. [回滚剧本](#3-回滚剧本)
4. [监控指标（24 小时观察窗）](#4-监控指标24-小时观察窗)
5. [故障切换策略](#5-故障切换策略)
6. [应急联系与值班](#6-应急联系与值班)

---

## 1. 前置检查清单

**说明**：以下每项均须在开始部署前**人工确认并打勾**。任何一项未就绪，暂停部署，待解决后重新评估。

### 1.1 数据安全与备份

- [ ] **PG 数据库已完整备份**：执行以下命令，确认备份文件存在且大小非零，记录备份时间戳和文件路径：

  ```bash
  # 在 ECS 上执行（SSH 到服务器后）
  BACKUP_FILE="/opt/genplatform/backups/db_before_doubao_$(date +%Y%m%d_%H%M%S).sql.gz"
  mkdir -p /opt/genplatform/backups
  sudo -u postgres pg_dump content_gen_platform | gzip > "$BACKUP_FILE"
  ls -lh "$BACKUP_FILE"   # 确认文件非空
  echo "备份路径：$BACKUP_FILE"
  ```

  **记录备份信息**（填写后勾选）：
  - 备份时间戳：_______________
  - 备份文件路径：_______________
  - 文件大小：_______________

- [ ] **备份文件可恢复验证**（可选，但强烈建议）：

  ```bash
  # 仅验证 gzip 完整性，不实际恢复
  gunzip -t "$BACKUP_FILE" && echo "[OK] 备份文件 gzip 完整性验证通过"
  ```

### 1.2 当前服务健康状态

- [ ] **gunicorn 进程当前健康**：

  ```bash
  # 在 ECS 上执行
  systemctl status genplatform-backend | grep -E "active|running"
  curl -sf -o /dev/null -w "HTTP %{http_code}\n" \
    -X POST -H "Content-Type: application/json" -d '{}' \
    http://localhost:8000/api/v1/auth/login/
  # 期望：HTTP 400 或 HTTP 401（非 500、非 000）
  ```

- [ ] **celery worker 当前健康**：

  ```bash
  systemctl status genplatform-celery | grep -E "active|running"
  # 期望输出中包含 "active (running)"
  # 注意：参考 lessons_learned.md 修复 9 — Celery 启动慢，若 inactive 但无错误日志，等待 5 分钟再确认
  ```

- [ ] **PostgreSQL 服务健康**：

  ```bash
  # alinux3 上服务名为 postgresql-15（参考 alinux3_compatibility.md 第 2.2 节）
  systemctl status postgresql-15 | grep -E "active|running"
  sudo -u postgres pg_isready -h localhost -p 5432
  ```

- [ ] **Redis 服务健康**：

  ```bash
  systemctl status redis | grep -E "active|running"
  redis-cli ping
  # 期望返回 PONG
  ```

### 1.3 业务侧沟通

- [ ] **即梦旧素材用户通知评估完成**：
  - 本次迁移按 OQ-5=A 决策：`provider=null` 的旧素材数据保留原样，不做数据迁移。
  - 前端 UI 切换为 Doubao 模型选择器后，旧素材仍可在历史记录中查看，但生成界面不再显示即梦入口。
  - **需确认**：是否需要在部署前通过站内消息/邮件通知用户"图片生成服务已升级为豆包 Seedream"？（建议：是，发送一次站内通知）
  - 确认结论：_______________

- [ ] **至少一个 Ark API Key 已就位**：以下两种方式满足其一即可：

  **方式 A**（推荐）：用户级 settings_vault 配置 — 登录系统，在"服务配置"页面为 `doubao_image` service_type 配置 API Key，验证可保存成功：

  ```bash
  # 验证 settings_vault 中有 doubao_image 条目
  sudo -u genplatform /opt/genplatform/venv/bin/python \
    /opt/genplatform/app/project_workspace/content_gen_platform/src/backend/manage.py \
    shell -c "
  from apps.settings_vault.models import ServiceConfig
  qs = ServiceConfig.objects.filter(service_type='doubao_image')
  print(f'doubao_image 配置数量: {qs.count()}')
  "
  ```

  **方式 B**（全局回退）：`.env` 文件中包含 `ARK_API_KEY` 占位值：

  ```bash
  grep "ARK_API_KEY" /opt/genplatform/.env
  # 期望：ARK_API_KEY=<非空值>
  # 注意：.env 中不允许出现真实 Key 的明文，建议通过 secrets manager 注入
  ```

### 1.4 磁盘与内存

- [ ] **磁盘空间充足**（≥ 10 GB 可用）：

  ```bash
  df -h /opt/genplatform
  # 图片文件预估：按每张生成图约 1-3 MB、初期日均生成 100 张估算，
  # 30 天约需 3-9 GB。建议预留 ≥ 10 GB。
  # 若磁盘不足，先清理旧 Python 编译缓存和日志文件：
  #   du -sh /opt/genplatform/app/project_workspace/content_gen_platform/src/backend/__pycache__/
  ```

- [ ] **可用内存 ≥ 1 GB**（热更新，无需重装依赖）：

  ```bash
  free -h
  # 参考 lessons_learned.md 元根因 D：内存约束级联失败
  # 若可用内存 < 1 GB，先停止非必要服务再进行部署
  ```

### 1.5 代码与配置

- [ ] **目标 commit 已通过 CI 全量检查**：
  - `ci.yml` 中 lint / test-unit / test-integration / build-frontend / validate-image 全部 PASS
  - GitHub Actions 最新 run 状态为绿色

- [ ] **新增依赖 tenacity==8.5.0 确认已在 requirements.txt**：

  ```bash
  # 在开发机（Windows PowerShell）执行
  Select-String -Path "project_workspace\content_gen_platform\src\backend\requirements.txt" -Pattern "tenacity"
  # 期望：找到 tenacity==8.5.0
  ```

---

## 2. 部署步骤

> **执行环境说明**：
> - 标注 `[开发机]` 的命令在 Windows 开发机（PowerShell）或 CI runner 上执行
> - 标注 `[ECS]` 的命令需要 SSH 到阿里云 ECS 后执行（Bash/sh）
> - 严禁在未完成第 1 节前置检查的情况下执行以下步骤

### Step 1 — 拉取最新代码

```bash
# [ECS] 方式 A：若 ECS 已安装 git（参考 lessons_learned.md 修复 12）
cd /opt/genplatform/app
git fetch origin main
git checkout main
git pull origin main
git log --oneline -3  # 确认最新 commit hash 符合预期

# [ECS] 方式 B：若使用 scp 上传（物理机部署标准方式，参考 deploy-physical.yml）
# 通过 GitHub Actions deploy-physical.yml 手动触发 workflow，
# scp-action 会自动将源码上传至 /opt/genplatform/app，跳过此步骤
```

**验证**：

```bash
# [ECS]
cat /opt/genplatform/app/project_workspace/content_gen_platform/src/backend/apps/image_generator/migrations/0002_imagebatch_and_fields.py | head -5
# 期望：显示迁移文件头部注释，确认文件已更新
```

### Step 2 — 安装 Python 依赖（新增 tenacity）

```bash
# [ECS]
source /opt/genplatform/venv/bin/activate

# 安装/更新依赖（包含新增的 tenacity==8.5.0）
pip install -r /opt/genplatform/app/project_workspace/content_gen_platform/src/backend/requirements.txt \
    --no-deps-check 2>&1 | tee /tmp/pip_install.log

# 若担心依赖冲突，使用完整解析（较慢）
# pip install -r requirements.txt

# 验证 tenacity 安装成功
pip show tenacity
# 期望输出：Name: tenacity, Version: 8.5.0
python -c "import tenacity; print('tenacity OK:', tenacity.__version__)"
```

**注意**：参考 `lessons_learned.md` 元根因 A，安装过程中**不允许**使用 `|| true` 掩盖错误。若 pip 报错，查看 `/tmp/pip_install.log` 定位原因。

### Step 3 — 执行数据库迁移

> **前提**：PostgreSQL 服务健康（已在 Step 1.2 确认），备份已完成（Step 1.1）。

```bash
# [ECS]
cd /opt/genplatform/app/project_workspace/content_gen_platform/src/backend
source /opt/genplatform/venv/bin/activate

# 查看当前迁移状态（执行前）
python manage.py showmigrations image_generator settings_vault

# 执行 image_generator 0002 迁移（新增 ImageBatch 表 + 新字段 + DB CHECK 约束）
python manage.py migrate image_generator 0002_imagebatch_and_fields
# 期望输出：Applying image_generator.0002_imagebatch_and_fields... OK

# 执行 settings_vault 0002 迁移（空迁移，版本锚点）
python manage.py migrate settings_vault 0002_add_doubao_image_service
# 期望输出：Applying settings_vault.0002_add_doubao_image_service... OK

# 或一次性执行所有待执行迁移（等效，更简洁）
# python manage.py migrate

# 执行后验证迁移状态
python manage.py showmigrations image_generator settings_vault
# 期望：两条 0002 迁移前均显示 [X]（已执行标记）
```

**若迁移失败**：立即停止，不执行后续步骤，参考第 3 节回滚剧本的"DB 回滚"路径。

### Step 4 — 收集静态文件

```bash
# [ECS]
cd /opt/genplatform/app/project_workspace/content_gen_platform/src/backend
source /opt/genplatform/venv/bin/activate

# 若前端 dist 有更新（通过 scp 上传），先确认 nginx 配置中 alias/root 路径
python manage.py collectstatic --noinput 2>&1
# 期望：输出复制文件数量（若无 Django admin 静态文件变化，可能为 0）
```

**注意**：本次迭代前端有 UI 改动（模型选择器），需确认前端 `dist/` 已通过 scp 上传至正确路径（nginx 配置中的 `root` 或 `alias` 目录）。

### Step 5 — 重启 gunicorn

```bash
# [ECS]
# 参考 lessons_learned.md 修复 11：使用 restart（幂等，避免 "already running" 错误）
systemctl restart genplatform-backend

# 等待 5 秒后检查状态
sleep 5
systemctl status genplatform-backend

# 关键：systemctl 返回 0 不代表服务真正可用！
# 参考 lessons_learned.md 元根因 B：退出码 0 ≠ 执行成功
# 必须执行以下功能性验证：
curl -sf -o /dev/null -w "HTTP %{http_code}\n" \
  -X POST -H "Content-Type: application/json" -d '{}' \
  http://localhost:8000/api/v1/auth/login/
# 期望：HTTP 400 或 HTTP 401
# 若返回 HTTP 000 或 HTTP 500：立即查看 journalctl 日志（见故障排查）
```

**若重启后服务不健康**：

```bash
# [ECS] 查看最近 50 行日志
journalctl -u genplatform-backend --lines=50 --no-pager
# 常见原因：新迁移未执行（Step 3 未完成）、requirements 未更新（Step 2 未完成）
# 参考 troubleshooting_runbook.md 对应章节
```

### Step 6 — 重启 celery worker

```bash
# [ECS]
systemctl restart genplatform-celery

# celery 启动较慢（sentence-transformers 模型加载约 2-5 分钟）
# 参考 lessons_learned.md 修复 9：不要同步等待 celery 就绪，等 5 分钟后再确认
echo "celery 已发送重启信号，等待 5 分钟后验证..."

# 5 分钟后验证：
sleep 300
systemctl status genplatform-celery | grep -E "active|running"
journalctl -u genplatform-celery --lines=30 --no-pager | grep -E "ready|celery@|ERROR"
```

**内存注意**：参考 `lessons_learned.md` 元根因 D，当前 gunicorn 配置为 2 workers（commit 8b91754），celery worker 含嵌入模型约占 600 MB。若 ECS 总内存 4 GB，两者合计约 1 GB，应有余量。

### Step 7 — Health Check（功能性验证）

**7.1 API 基础健康检查**

```bash
# [ECS] 登录接口（验证 gunicorn + Django + DB 链路）
curl -sf -o /dev/null -w "HTTP %{http_code}\n" \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"","password":""}' \
  http://localhost:8000/api/v1/auth/login/
# 期望：HTTP 400（参数校验，说明 Django + DB 正常）
```

**7.2 图片生成接口 Dry-run**

```bash
# [ECS] 先获取有效 Token（替换为实际测试账号的 username/password）
TOKEN=$(curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"[TEST_USER]","password":"[TEST_PASSWORD]"}' \
  http://localhost:8000/api/v1/auth/login/ | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access',''))")

echo "Token 获取状态：${#TOKEN} 字节"

# [ECS] 提交图片生成请求（单张，验证 API 路由 + 序列化器 + Celery task 提交）
# 注意：替换为实际字段名（参考 API 文档）
curl -sf -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "prompt": "一只在阳光下奔跑的柴犬",
    "model": "seedream-3-0",
    "n": 1,
    "size": "1024x1024"
  }' \
  http://localhost:8000/api/v1/images/generate/ \
  | python3 -m json.tool
# 期望：返回 HTTP 201 + batch_id，Celery task 已提交（可能有 ARK_API_KEY 未配置的错误，属预期）
```

**注意**：若测试账号未配置 Ark API Key，响应可能返回 4xx 错误（未配置密钥），这属于**预期行为**，不代表服务异常。真正的异常是 5xx 或 HTTP 000。

### Step 8 — 抽样验证（核心业务约束）

**8.1 验证单批次数量上限（n ≤ 4 约束）**

```bash
# [ECS] 提交 n=5 的请求，应返回 HTTP 400（DB CHECK 约束 + 序列化器层双重保护）
curl -sf -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "prompt": "测试超量",
    "model": "seedream-3-0",
    "n": 5
  }' \
  http://localhost:8000/api/v1/images/generate/ \
  -w "\nHTTP_CODE: %{http_code}\n"
# 期望：HTTP 400，响应体中包含数量限制错误说明
```

**8.2 验证模型选择器（三个版本可见）**

> 说明：模型列表是**前端硬编码常量**，无后端 `/api/v1/images/models/` 接口（见 `frontend/src/components/ImageGenerator/ModelSelector.vue:36-50`）。本步骤改为浏览器人工验证 + 静态资源校验。

**8.2.1 [开发机] 静态资源校验（前端 dist 已正确打包包含三个模型字符串）**

```bash
# 在已 build 的前端产物中检查三个模型 value 是否存在
cd project_workspace/content_gen_platform/src/frontend
grep -E "Doubao-Seedream-5\\.0-lite|Doubao-Seedream-4\\.5|Doubao-Seedream-4\\.0" dist/assets/*.js
# 期望：三个字符串均能在 minified JS 产物中匹配到（grep 输出非空）
```

**8.2.2 [浏览器] UI 抽查**

- 打开 `https://<生产域名>/image-generator`（已登录态）
- 期望模型选择下拉框包含 3 个选项，顺序由上至下：
  1. `Seedream 5.0 Lite` （value: `Doubao-Seedream-5.0-lite`，副本: 速度优先）
  2. `Seedream 4.5` （value: `Doubao-Seedream-4.5`，默认选中，副本: 推荐）
  3. `Seedream 4.0` （value: `Doubao-Seedream-4.0`，副本: 标准版）
- 期望页面**不再显示**任何即梦相关入口（OQ-1=A）
- 期望"高级参数"为可展开折叠面板（OQ-2=B），默认收起，内含 seed / negative_prompt / guidance_scale / steps / watermark


**8.3 验证旧素材（provider=null）数据保留**

```bash
# [ECS] 查询数据库，确认 provider=null 的旧记录仍存在（未被迁移脚本清除）
sudo -u genplatform /opt/genplatform/venv/bin/python \
  /opt/genplatform/app/project_workspace/content_gen_platform/src/backend/manage.py \
  shell -c "
from apps.image_generator.models import ImageGenerationRequest
total = ImageGenerationRequest.objects.count()
null_provider = ImageGenerationRequest.objects.filter(provider__isnull=True).count()
print(f'总记录数: {total}，provider=null 的记录: {null_provider}')
"
# 期望：provider=null 的记录数 == 迁移前的总记录数（无数据丢失）
```

---

## 3. 回滚剧本

> **触发条件**：部署后出现以下任意情况，立即启动回滚：
> - Step 5 gunicorn health check 连续 3 次返回 5xx 或 000
> - Step 8 业务约束验证失败（n=5 未被拦截）
> - 监控指标中 Ark 调用 5xx 率 > 50%（非 API Key 未配置导致）
> - 用户报告关键功能（生成图片、查看历史）完全不可用

### 3.1 代码回滚

```bash
# [ECS] 方式 A：git 回退（若服务器有 git）
cd /opt/genplatform/app
git log --oneline -5  # 确认当前 commit 和目标回退点

# 回退到上一个 tag（替换为实际 tag 名，如 v2.3.0）
git checkout <previous-tag>

# 重新安装依赖（tenacity 将被移除）
source /opt/genplatform/venv/bin/activate
pip install -r project_workspace/content_gen_platform/src/backend/requirements.txt

# 重启服务
systemctl restart genplatform-backend
systemctl restart genplatform-celery

# 方式 B：触发旧版本的 deploy-physical.yml（在 GitHub Actions 中手动触发，指定旧 commit）
# 在 GitHub 仓库 Actions 页面 → deploy-physical.yml → Run workflow → 指定旧 branch/tag
```

### 3.2 数据库迁移回滚

**重要**：数据库回滚有数据风险。执行前务必确认 Step 1.1 的备份文件可用。

**回滚 image_generator 0002**（反向 SQL，当 Django 管理命令不可用时使用）：

```sql
-- [ECS] 以 postgres 用户连接数据库
sudo -u postgres psql content_gen_platform

-- 反向操作：删除新字段和新表
-- 顺序重要：先删除外键依赖列，再删除表

ALTER TABLE image_generation_request DROP COLUMN IF EXISTS batch_id;
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS model;
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS provider;

DROP TABLE IF EXISTS image_batch;

-- 验证
\d image_generation_request
-- 期望：不再包含 batch_id / model / provider 列
\dt
-- 期望：image_batch 表不存在
```

**通过 Django 管理命令回滚**（推荐，更安全）：

```bash
# [ECS]
cd /opt/genplatform/app/project_workspace/content_gen_platform/src/backend
source /opt/genplatform/venv/bin/activate

# 回退 image_generator 到 0001（自动执行反向迁移）
python manage.py migrate image_generator 0001_initial
# 期望：Unapplying image_generator.0002_imagebatch_and_fields... OK

# 注意：settings_vault 0002 是空迁移（无 DB 变更），回滚不影响数据库结构
# 但若需要版本对齐，可执行：
python manage.py migrate settings_vault 0001_initial
```

**回滚 0002 对应的迁移文件注释（备查）**：

```
# apps/image_generator/migrations/0002_imagebatch_and_fields.py 中的回滚说明：
# 回滚方法（Django 命令）：
#     python manage.py migrate image_generator 0001_initial
#
# 回滚 SQL：
#     ALTER TABLE image_generation_request DROP COLUMN IF EXISTS batch_id;
#     ALTER TABLE image_generation_request DROP COLUMN IF EXISTS model;
#     ALTER TABLE image_generation_request DROP COLUMN IF EXISTS provider;
#     DROP TABLE IF EXISTS image_batch;
```

### 3.3 用户数据回滚

**OQ-5=A 决策**：`provider=null` 的旧素材数据保留原样，本次迁移**不做数据迁移脚本**，因此无需回滚用户历史数据。

若确认数据异常需要从备份恢复，执行：

```bash
# [ECS] 从备份恢复（破坏性操作，会覆盖所有数据，谨慎执行）
# 先停止服务
systemctl stop genplatform-backend genplatform-celery

# 恢复数据库
sudo -u postgres psql -c "DROP DATABASE IF EXISTS content_gen_platform;"
sudo -u postgres psql -c "CREATE DATABASE content_gen_platform;"
gunzip -c "$BACKUP_FILE" | sudo -u postgres psql content_gen_platform

# 重启服务（回滚代码后再重启）
systemctl start genplatform-backend
systemctl start genplatform-celery
```

---

## 4. 监控指标（24 小时观察窗）

部署完成后，持续观察以下指标至少 24 小时。建议在部署后第 1 小时、第 6 小时、第 24 小时分别人工检查一次。

### 4.1 Ark API 调用成功率

**观察目标**：Doubao Ark API 的调用成功率，识别 4xx/5xx 异常分布。

```bash
# [ECS] 通过 Celery 日志统计（替代方案：若有 APM 工具则优先使用）
journalctl -u genplatform-celery --since "1 hour ago" --no-pager | \
  grep -E "doubao|ark|image_generator" | \
  grep -cE "SUCCESS|FAILURE" | head -5

# 或通过 Django shell 查询 Celery task 结果
sudo -u genplatform /opt/genplatform/venv/bin/python manage.py shell -c "
from django_celery_results.models import TaskResult
from django.utils import timezone
from datetime import timedelta
cutoff = timezone.now() - timedelta(hours=24)
total = TaskResult.objects.filter(date_created__gte=cutoff).count()
success = TaskResult.objects.filter(date_created__gte=cutoff, status='SUCCESS').count()
failure = TaskResult.objects.filter(date_created__gte=cutoff, status='FAILURE').count()
print(f'24h: 总={total}, 成功={success}, 失败={failure}')
if total > 0:
    print(f'成功率: {success/total*100:.1f}%')
"
```

**预警阈值**：
- 正常：成功率 ≥ 90%（4xx 主要为用户 API Key 未配置，属预期）
- 关注：成功率 70%-90%，排查 Ark 服务稳定性
- 告警：成功率 < 70%，立即介入

### 4.2 Celery task 失败率

```bash
# [ECS] 查看最近 1 小时 Celery task 异常
journalctl -u genplatform-celery --since "1 hour ago" --no-pager | \
  grep -E "ERROR|CRITICAL|Traceback" | tail -20
```

**预警阈值**：
- 正常：无 CRITICAL 级别错误
- 关注：出现 RetryError（tenacity 重试耗尽），需排查 Ark API 可达性
- 告警：出现 OOM Kill（参考 `troubleshooting_runbook.md` F09/F10 章节）

### 4.3 WebSocket 推送延迟

图片生成进度通过 WebSocket 推送给前端。观察 Channels/Redis 是否正常。

```bash
# [ECS] 验证 Redis 连接正常
redis-cli ping
# 期望：PONG

# 查看 Channels layer 连接状态
journalctl -u genplatform-backend --since "1 hour ago" --no-pager | \
  grep -E "channels|websocket|daphne" | tail -10
```

**预警阈值**：
- 正常：无 WebSocket 断连错误
- 关注：出现频繁重连（可能是 Redis 内存不足），检查 Redis 内存使用

### 4.4 用户级 API Key 配置完成率

此指标用于评估用户体验：若用户未配置 Ark API Key，doubao_image 生成请求将失败（返回特定错误码）。

```bash
# [ECS] 统计已配置 doubao_image API Key 的用户数
sudo -u genplatform /opt/genplatform/venv/bin/python manage.py shell -c "
from apps.settings_vault.models import ServiceConfig
total_users = ServiceConfig.objects.values('user').distinct().count()
doubao_users = ServiceConfig.objects.filter(service_type='doubao_image').values('user').distinct().count()
print(f'已配置 doubao_image key 的用户数: {doubao_users}')
print(f'总 settings_vault 用户数: {total_users}')
"
```

**建议**：若上线 48 小时后，配置完成率 < 20%，考虑在前端首次进入图片生成页面时增加引导提示（feature flag 控制）。

### 4.5 Nginx 和服务整体状态

```bash
# [ECS] 每小时执行一次的综合状态检查
echo "=== $(date) ===" 
systemctl status genplatform-backend --no-pager | grep "Active:"
systemctl status genplatform-celery --no-pager | grep "Active:"
nginx -t && echo "Nginx config OK"
free -h | grep "Mem:"
df -h /opt/genplatform | tail -1
```

---

## 5. 故障切换策略

### 5.1 Ark 服务不可达时的降级策略

**重要**：按 OQ-1=A 决策，本次迁移已**删除即梦（Jimeng）图片生成的调用链路**（`jimeng_image_client.py` 保留文件但无生产调用入口）。

因此，当 Ark 服务降级时：
- **没有自动回退到即梦的机制**（调用链路已删除）
- 用户提交的图片生成请求将在 Celery task 中失败（tenacity 最大重试 3 次后抛出 `RetryError`）
- 前端通过 WebSocket 收到任务失败通知

**应对措施**：

| 场景 | 处理方式 |
|------|---------|
| Ark API 临时超时（< 30s） | tenacity 自动重试（指数退避，最多 3 次），用户无感 |
| Ark API 持续不可达（> 5 分钟） | 通过站内公告通知用户服务异常；在后台确认 Ark 服务状态 |
| Ark API Key 失效（401 错误） | 引导用户在设置页面更新 API Key；临时可在 `.env` 配置全局 `ARK_API_KEY` 兜底 |
| Ark 服务永久下线 | 需要新一轮迭代，接入其他图片生成服务 |

**确认 Ark 服务状态**：

```bash
# [开发机 Bash] 测试 Ark API 可达性（不包含真实 Key）
curl -sf -o /dev/null -w "HTTP %{http_code}\n" \
  https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Content-Type: application/json" \
  -d '{}'
# 期望：HTTP 401（未授权，但服务可达）；若 HTTP 000 或超时，说明服务不可达
```

### 5.2 数据库异常时的降级

若 PostgreSQL 出现异常（参考 `troubleshooting_runbook.md` F07/F11），图片生成相关功能将全部不可用。

**优先级**：数据库恢复 > 服务恢复 > 功能验证。

---

## 6. 应急联系与值班

> **注意**：以下为占位信息，部署前需填写实际联系人。

| 角色 | 姓名 | 联系方式 | 值班时段 |
|------|------|---------|---------|
| 主要负责人（后端）| [待填写] | [待填写] | 部署当天全天 |
| 主要负责人（前端）| [待填写] | [待填写] | 部署当天全天 |
| 数据库管理员 | [待填写] | [待填写] | 按需呼叫 |
| 阿里云账号管理员 | [待填写] | [待填写] | 按需呼叫 |

**升级路径**：
1. 发现问题 → 执行 Step 7 health check 确认范围
2. 范围确认 → 判断是否需要回滚（参考第 3 节）
3. 决定回滚 → 通知相关人员 → 执行回滚步骤 → 验证服务恢复

---

## 参考文档

- `docs/deployment/lessons_learned.md` — 12 次关键修复详情 + 6 类元根因（本文档每个关键步骤均已引用对应修复经验）
- `docs/deployment/alinux3_compatibility.md` — alinux3 服务名差异（第 2.2 节）、systemd 兼容写法（第 5 节）
- `docs/deployment/troubleshooting_runbook.md` — 快速诊断入口（第 0 节）、F07（DB 密码）、F08（服务名）、F09（Celery 超时）、F10（OOM）、F11（migrate 顺序）
- `docs/architecture/doubao_image_migration/module_design.md` — 迁移回滚脚本（第 3 章）、ADR-04（ImageBatch 约束）、ADR-06（settings_vault 迁移策略）
- `docs/requirements/doubao_image_migration/` — OQ-1（即梦调用链路删除）、OQ-5（旧素材保留策略）
