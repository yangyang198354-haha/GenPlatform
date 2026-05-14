# 部署计划 v1.1 — 增量补丁
# 豆包图片迁移 UX 修复迭代（API Key 配置 UX + PreflightBanner + ark_validator）

**文档编号**：DPL-PLAN-IMG-001-PATCH
**基准版本**：v1.0（随 commit c0506c0 上线，服务运行中）
**本补丁版本**：v1.1
**创建日期**：2026-05-14
**状态**：DRAFT — 等待 PM 门控评审
**作者**：devops-engineer 子代理（由 PM 编排）
**目标环境**：阿里云 ECS（Alibaba Cloud Linux 3），物理机部署（systemd + nginx）
**阅读方式**：本文档为**增量补丁**，与 v1.0 部署计划联合使用。不变项引用 v1.0 原文，不重复抄写。

> **安全提示**：本文档不包含任何真实 API Key、IP 地址、密码或其他敏感凭证。
> 生产环境凭证仅存在于 GitHub Actions Secrets 和服务器 `.env` 文件中。

---

## 一、本次迭代部署范围

### 1.1 与 v1.0 的差异（仅列变更项）

**后端变更（新增/修改）**：

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `apps/settings_vault/ark_validator.py` | 新增 | Ark API Key 验证模块，无新外部依赖 |
| `apps/settings_vault/models.py` | 修改 | 新增 `last_validated_at` 字段、`_required_keys()` / `_test_connection()` doubao_image 分支 |
| `apps/settings_vault/serializers.py` | 修改 | 新增 `ServiceStatusSerializer` / `TestAndSaveSerializer` |
| `apps/settings_vault/views.py` | 修改 | 新增 `ServiceStatusView` / `TestAndSaveView` |
| `apps/settings_vault/urls.py` | 修改 | 新增路由：`/services/<type>/status/`、`/services/<type>/test-and-save/` |
| `migrations/0003_userserviceconfig_last_validated_at.py` | 新增 | **含 DB Migration，部署时必须显式执行** |

**前端变更（新增/修改）**：

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/components/Settings/DoubaoImageKeyPanel.vue` | 新增 | 豆包图片 Key 配置面板（含"测试连接"按钮） |
| `src/components/ImageGenerator/PreflightBanner.vue` | 新增 | 图片生成页预检 Banner（无关闭按钮） |
| `src/views/SettingsView.vue` | 修改 | 新增"豆包图片生成" Tab |
| `src/views/ImageGeneratorView.vue` | 修改 | `onMounted` 调用 `/status/` 接口，Banner v-if 控制 |
| `src/api/index.js` | 修改 | 新增 `getDoubaoImageStatus` / `testAndSaveDoubaoKey` API 方法 |

**无新增 Python 依赖**（tenacity 和 httpx 已在 v1.0 的 requirements.txt 中）。

**无破坏性 DB 变更**（0003 仅新增 nullable 字段，向后兼容，回滚可逆）。

---

## 二、前置检查清单（部署前必须逐项确认）

### 2.1 服务运行状态检查（核心：避免覆盖故障服务）

在触发任何部署动作之前，先 SSH 到服务器执行以下检查：

```bash
# 检查 gunicorn 后端服务
systemctl status genplatform-backend
# 预期：active (running)

# 检查 celery worker
systemctl status genplatform-celery
# 预期：active (running)（首次部署后若出现延迟，参考 lessons_learned.md 修复9）

# 检查 nginx
systemctl status nginx
# 预期：active (running)

# 快速冒烟验证（确认上线版本 c0506c0 服务正常）
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/auth/login/ \
    -X POST -H "Content-Type: application/json" -d '{}'
# 预期：400 或 401（而非 000 / 500 / 502）
```

若任一服务处于 failed 状态，**必须先修复当前服务**，不允许在故障状态下执行增量部署。

### 2.2 数据库备份检查（本次含 Migration，强制备份）

本次迭代包含 Migration 0003，必须在执行 `migrate` 之前完成数据库备份：

```bash
# 备份当前数据库（替换 <timestamp> 为实际时间戳，不含敏感凭证）
sudo -u postgres pg_dump content_gen_platform \
    > /opt/genplatform/backups/content_gen_platform_pre_v1.1_<timestamp>.sql

# 确认备份文件存在且非空
ls -lh /opt/genplatform/backups/content_gen_platform_pre_v1.1_<timestamp>.sql
# 预期：文件大小 > 0
```

### 2.3 现有用户配置兼容性检查

0003 migration 新增 `last_validated_at DateTimeField(null=True)`：

- 对现有 `UserServiceConfig` 记录（包括用户手动配置的 `doubao_image` 早期配置）：字段默认值为 `NULL`，不影响读写
- 无数据迁移（无 data migration），对现有行完全向后兼容
- 回滚命令：`python manage.py migrate settings_vault 0002`（删除该字段，见 §五）

确认项：

```bash
# 确认当前 migration 状态（上线前状态应为 0002 applied，0003 未 apply）
/opt/genplatform/venv/bin/python manage.py showmigrations settings_vault
# 预期输出：
#   [X] 0001_initial
#   [X] 0002_userserviceconfig_doubao_fields  (或类似名称)
#   [ ] 0003_userserviceconfig_last_validated_at  ← 未 apply，待本次部署执行
```

### 2.4 前端构建产物检查

```bash
# 确认本地或 CI 已完成 npm run build（dist 目录存在）
ls project_workspace/content_gen_platform/src/frontend/dist/index.html
# 预期：文件存在

# 若使用 deploy-physical.yml workflow，构建在 workflow 内自动执行，无需手动确认
```

### 2.5 GitHub Actions 冲突预防检查

```bash
# 在触发 deploy-physical.yml 之前，确认 main 分支最新 commit 已被 push
git log --oneline -3
git status  # 应为 clean working tree

# 准备好 cancel 命令（merge 后立即执行）
# gh run cancel <ci-run-id>  ← 见 §三 的详细说明
```

---

## 三、ci.yml deploy-production 冲突处理（必读）

> 这是上次部署（PR #4 / c0506c0）踩过的坑，本次必须提前处理。

### 3.1 冲突场景说明

当本次迭代的 PR merge 到 main 后，`ci.yml` 会自动触发全部 job，其中包含 `deploy-production` job（使用 docker compose），该 job 会尝试 `docker compose pull + up`，与服务器上的 systemd 物理机部署**直接冲突**。

### 3.2 必须执行的操作（merge 后 3 分钟内）

```bash
# Step 1：确认 ci.yml 已被触发
gh run list --workflow=ci.yml --limit=3
# 找到状态为 in_progress 的 run ID

# Step 2：立即取消（在 docker compose pull 完成之前）
gh run cancel <ci-run-id>

# Step 3：确认取消成功
gh run view <ci-run-id>
# 状态应显示 cancelled
```

### 3.3 若取消失败（已进入 docker compose up 阶段）

```bash
# 立即 SSH 到服务器检查 systemd 服务状态
systemctl status genplatform-backend genplatform-celery

# 若服务被 Docker 覆盖（出现 502），执行紧急恢复：
systemctl restart genplatform-backend genplatform-celery
# 验证
curl -s http://localhost:8000/api/v1/health/
```

---

## 四、部署步骤（热更新模式，run_setup=false）

### 推荐方式：通过 deploy-physical.yml workflow 执行

```bash
# 触发热更新（merge main 后，ci.yml 冲突已处理完毕后执行）
gh workflow run deploy-physical.yml --ref main -f run_setup=false

# 监控执行状态
gh run list --workflow=deploy-physical.yml --limit=3
gh run view <deploy-run-id> --log
```

### 手动步骤（若 workflow 不可用时的备用方案）

以下步骤在服务器上按顺序手动执行，每步执行后验证退出码为 0。

---

**Step 1 — 拉取最新代码**

```bash
cd /opt/genplatform/app
git pull origin main
git log --oneline -1
# 确认显示本次迭代的最新 commit hash
```

---

**Step 2 — 后端依赖安装（应快速通过，无新依赖）**

```bash
# 本次迭代无新 Python 依赖，此步骤应极快完成（仅确认无变化）
/opt/genplatform/venv/bin/pip install -r \
    project_workspace/content_gen_platform/src/backend/requirements.txt \
    --no-audit --no-fund
# 预期输出：Requirement already satisfied（所有包均已安装）
```

---

**Step 3 — 执行 DB Migration（关键步骤）**

> 此步骤在 v1.0 部署中不存在，是本次迭代最重要的新增步骤。

```bash
cd /opt/genplatform/app/project_workspace/content_gen_platform/src/backend

# 先确认 PostgreSQL 运行正常
systemctl is-active postgresql-15 || systemctl is-active postgresql
# 预期：active

# 确认连接正常
/opt/genplatform/venv/bin/python manage.py dbshell -c "SELECT 1;" 2>/dev/null && echo "[OK] DB 连接正常"

# 执行 Migration 0003
/opt/genplatform/venv/bin/python manage.py migrate settings_vault 0003

# 验证 Migration 已 apply
/opt/genplatform/venv/bin/python manage.py showmigrations settings_vault
# 预期：[X] 0003_userserviceconfig_last_validated_at

# 验证字段存在（使用 dbshell）
/opt/genplatform/venv/bin/python manage.py dbshell -c \
    "SELECT column_name FROM information_schema.columns \
     WHERE table_name='settings_vault_userserviceconfig' \
     AND column_name='last_validated_at';" 2>/dev/null
# 预期：返回 last_validated_at
```

---

**Step 4 — 前端打包**

> 注意：前端构建（Vite）是内存密集操作，必须先停服务释放内存（历史教训：修复10）。

```bash
# 停止服务释放内存（关键：避免 OOM Kill）
systemctl stop genplatform-backend genplatform-celery genplatform-celery-beat 2>/dev/null || true
sync && echo 3 > /proc/sys/vm/drop_caches
free -h
# 确认 available 内存 > 1GB 再继续

# 设置镜像源（国内服务器加速）
npm config set registry https://registry.npmmirror.com

# 构建
export NODE_OPTIONS="--max-old-space-size=1024"
cd /opt/genplatform/app/project_workspace/content_gen_platform/src/frontend
npm ci --no-audit --no-fund
npm run build

# 验证构建产物
ls -la dist/index.html
# 预期：文件存在，大小 > 0
```

---

**Step 5 — 部署前端 dist 到 Nginx 静态目录**

```bash
# 确认 nginx 静态目录路径（按实际服务器配置调整）
NGINX_STATIC_DIR="/opt/genplatform/frontend/dist"

# 备份旧 dist（用于紧急回滚）
cp -r "$NGINX_STATIC_DIR" "${NGINX_STATIC_DIR}.bak.v1.0"

# 同步新 dist
rsync -av --delete \
    /opt/genplatform/app/project_workspace/content_gen_platform/src/frontend/dist/ \
    "$NGINX_STATIC_DIR/"

# 验证
ls "$NGINX_STATIC_DIR/index.html"
```

---

**Step 6 — 重启后端服务**

```bash
# 重启 gunicorn
systemctl restart genplatform-backend
sleep 3
systemctl status genplatform-backend
# 预期：active (running)

# 重启 celery（非致命，允许延迟启动）
systemctl restart genplatform-celery 2>/dev/null || echo "[WARN] Celery 重启延迟，属正常现象"
systemctl restart genplatform-celery-beat 2>/dev/null || true

# 重载 nginx（配置未变，仅 reload 即可）
nginx -t && nginx -s reload
```

---

## 五、部署后验证（Health Check）

按顺序执行以下验证，任一失败需立即停止并执行回滚：

### 验证 1 — API 基础连通性

```bash
# 登录接口（预期：400 或 401，表示服务正常响应）
curl -s -o /dev/null -w "%{http_code}" \
    http://localhost/api/v1/auth/login/ \
    -X POST -H "Content-Type: application/json" -d '{}'
# 预期：400 或 401（非 000/500/502）
```

### 验证 2 — 新接口 status（需登录 token，需提前获取）

```bash
# 先获取 token（替换为测试用户的用户名/密码）
TOKEN=$(curl -s http://localhost/api/v1/auth/login/ \
    -X POST -H "Content-Type: application/json" \
    -d '{"username":"<TEST_USER>","password":"<TEST_PASS>"}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access',''))")

# 检查 doubao_image status 接口（未配置时）
curl -s http://localhost/api/v1/settings/users/me/services/doubao_image/status/ \
    -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# 预期：{"is_configured": false, "last_validated_at": null}

# 检查未知 service_type 的守卫（TODO-03）
curl -s -o /dev/null -w "%{http_code}" \
    http://localhost/api/v1/settings/users/me/services/unknown_service/status/ \
    -H "Authorization: Bearer $TOKEN"
# 预期：400
```

### 验证 3 — Migration 验证（接口层）

```bash
# 通过 test-and-save 接口确认 DB 字段可写（使用无效 Key 测试格式校验）
curl -s http://localhost/api/v1/settings/users/me/services/doubao_image/test-and-save/ \
    -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"api_key":""}' | python3 -m json.tool
# 预期：400（api_key 为空，格式校验失败，不调用 Ark）
```

### 验证 4 — 前端页面（浏览器人工验证）

| 验证点 | 操作 | 预期结果 |
|-------|------|---------|
| 设置页新 Tab | 登录 → 进入设置页 | 应出现"豆包图片生成"Tab（v1.0 没有此 Tab） |
| 未配置时 Banner | 登录 → 进入图片生成页（Key 未配置）| 应显示 PreflightBanner（橙色/黄色警告，无关闭按钮） |
| Banner 消失逻辑 | 在设置页完成 Key 配置（测试成功后自动保存）→ 返回图片生成页 | Banner 不再显示 |
| 图片生成功能 | 在已配置 Key 后提交图片生成任务 | 任务提交成功，功能与 v1.0 一致 |

---

## 六、回滚剧本（三层可逆）

> 只有在部署后验证出现严重问题时才执行回滚。

### 回滚条件判断

| 症状 | 严重级别 | 推荐操作 |
|------|---------|---------|
| gunicorn 重启后无法启动（active failed） | CRITICAL | 立即执行代码回滚 |
| 新接口 /status/ 返回 500 | HIGH | 代码回滚 |
| migration apply 报错（DB 损坏） | CRITICAL | DB 回滚 + 代码回滚 |
| 前端页面加载 404 | MEDIUM | 前端 dist 回滚 |
| Banner 不显示（但功能正常） | LOW | 记录 bug，下次迭代修复，不需回滚 |

---

### 代码回滚

```bash
# 回退代码到 v1.0（豆包主功能上线版本）
cd /opt/genplatform/app
git fetch origin
git checkout c0506c0  # v1.0 commit hash（豆包主功能上线版本）

# 重新安装依赖（v1.0 的 requirements.txt）
/opt/genplatform/venv/bin/pip install -r \
    project_workspace/content_gen_platform/src/backend/requirements.txt

# 重启服务
systemctl restart genplatform-backend
systemctl restart genplatform-celery

# 验证 v1.0 功能恢复
curl -s -o /dev/null -w "%{http_code}" \
    http://localhost/api/v1/auth/login/ \
    -X POST -H "Content-Type: application/json" -d '{}'
# 预期：400 或 401
```

---

### DB 回滚（回退 Migration 0003）

> 仅在 migration apply 引发问题时执行。0003 仅删除 last_validated_at 字段（nullable），操作安全。

```bash
# 确认当前 migration 状态
/opt/genplatform/venv/bin/python manage.py showmigrations settings_vault

# 回滚 0003（删除 last_validated_at 字段）
/opt/genplatform/venv/bin/python manage.py migrate settings_vault 0002

# 验证回滚成功
/opt/genplatform/venv/bin/python manage.py showmigrations settings_vault
# 预期：[X] 0002 / [ ] 0003

# 确认字段已移除（操作成功则查询返回空）
/opt/genplatform/venv/bin/python manage.py dbshell -c \
    "SELECT column_name FROM information_schema.columns \
     WHERE table_name='settings_vault_userserviceconfig' \
     AND column_name='last_validated_at';" 2>/dev/null
# 预期：返回空（字段已删除）
```

---

### 前端 dist 回滚

```bash
# 确认旧 dist 备份存在（见 Step 5）
NGINX_STATIC_DIR="/opt/genplatform/frontend/dist"
ls "${NGINX_STATIC_DIR}.bak.v1.0/index.html"
# 预期：文件存在

# 还原旧 dist
rsync -av --delete "${NGINX_STATIC_DIR}.bak.v1.0/" "$NGINX_STATIC_DIR/"

# 重载 nginx
nginx -t && nginx -s reload

# 验证前端恢复（浏览器访问主页）
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# 预期：200
```

---

## 七、部署后 24h 监控指标

部署完成后，在 24h 内重点监控以下指标：

| 指标 | 监控方式 | 告警阈值 |
|------|---------|---------|
| `/services/doubao_image/status/` 接口成功率 | 服务器访问日志 | 成功率 < 99% 告警 |
| `/services/doubao_image/test-and-save/` 错误分布 | Django 应用日志（journalctl） | ARK_UNREACHABLE 错误率 > 20% 告警（可能是 Ark 服务问题） |
| `ARK_KEY_INVALID` / `ARK_QUOTA_EXCEEDED` 错误率 | Django 应用日志 | 正常值（表示用户输入了无效 Key），无告警，但需关注异常突增 |
| Banner 出现率（is_configured=false 占比） | `/status/` 接口响应统计 | 基线值待建立（首次部署后统计） |
| gunicorn 5xx 错误率 | nginx 访问日志 | 5xx > 1% 告警 |
| 服务器内存使用率 | `free -h`（定时检查） | available < 500MB 告警 |

**监控命令参考**：

```bash
# 查看 /status/ 接口调用日志
journalctl -u genplatform-backend --since "1 hour ago" --no-pager \
    | grep "services.*status"

# 查看 /test-and-save/ 错误日志
journalctl -u genplatform-backend --since "1 hour ago" --no-pager \
    | grep -E "ARK_KEY_INVALID|ARK_QUOTA_EXCEEDED|ARK_UNREACHABLE"

# 查看内存状态
free -h && ps aux --sort=-%mem | head -10
```

---

## 八、历史踩坑提醒（本次部署尤其注意）

基于 `docs/deployment/lessons_learned.md` 的 12 次历史修复，以下项对本次部署特别相关：

| 历史教训 | 本次是否有风险 | 防范措施 |
|---------|-------------|---------|
| npm build OOM Kill（修复10） | 有（Step 4 需要重建前端） | Step 4 前先停服、drop_caches、确认可用内存 > 1GB |
| systemctl restart 退出 0 ≠ 服务真正运行（元根因B） | 有 | Step 6 后 `systemctl status` 确认 active (running) |
| ci.yml deploy-production 与物理机冲突 | 高（本次同样需要 merge main） | merge 后立即 gh run cancel（§三） |
| Migration 步骤顺序（修复11） | 有（Step 3 依赖 PG 服务正常） | Step 3 前先确认 `systemctl is-active postgresql-15` |
| 服务健康检查：验证产物而非退出码（元根因B） | 贯穿全程 | 每步均有显式验证命令 |

---

## 九、等待用户二次 CONFIRM

> **当前状态：本文档为文档输出阶段，尚未执行任何实际部署动作。**

以下操作在用户发出**二次 CONFIRM 信号**之前，绝对不允许执行：

- `gh workflow run deploy-physical.yml`（触发生产部署 workflow）
- 任何 SSH 到生产服务器的写操作
- 任何 `git push` 到 main 分支
- `python manage.py migrate`（生产环境）
- `systemctl restart`（生产环境）

用户二次 CONFIRM 的发出方式：在对话中明确回复 **CONFIRM DEPLOY v1.1**（或类似明确授权语句）。

PM 在收到二次 CONFIRM 后，将指导执行 §三 的冲突预防操作 + §四 的热更新步骤 + §五 的验证步骤。

---

*文档版本 v1.1，状态 DRAFT，等待 PM 门控评审。*
*PM 门控 PASS 后，此文档状态升级为 APPROVED，可作为真实部署的操作依据。*
