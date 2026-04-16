# DevOps 工程师知识库 — CI 修复经验沉淀

> 更新日期：2026-04-16
> 来源：content_gen_platform 本轮 CI 修复（8 个失败测试）

---

## 经验一：GitHub Actions unit-test job 必须使用正确的 Django settings 模块

### 经验摘要
Django 项目通常有多套 settings（development / test / production）。
CI unit-test job 若使用了错误的 settings，会导致 Celery 任务异步执行、缓存后端不匹配、
throttle 行为与生产环境不符等一系列测试结果不可信的问题。

### 根因分析
- **问题 7** (`test_upload_txt_creates_chunks_in_db`)：
  CI unit-test job 使用 `DJANGO_SETTINGS_MODULE=config.settings.development`，
  该 settings 没有 `CELERY_TASK_ALWAYS_EAGER=True`，Celery 任务异步执行，
  测试断言时 chunk 状态始终为 `processing`，从未变为完成态。
- **问题 1** (`test_register_success` Redis ConnectionRefusedError)：
  CI unit-test job 使用的 settings 配置了 Redis 作为 throttle cache 后端，
  但 job 没有声明 Redis service，导致连接失败。切换到 `config.settings.test`
  后，test settings 使用 `LocMemCache`，不再需要 Redis service。

### 规则 / 结论

#### CI 各 job 的 `DJANGO_SETTINGS_MODULE` 对应关系

| CI Job | DJANGO_SETTINGS_MODULE | 说明 |
|--------|------------------------|------|
| unit-test | `config.settings.test` | 必须含 `CELERY_TASK_ALWAYS_EAGER=True`，cache 用 LocMemCache |
| integration-test | `config.settings.test` 或专用 integration settings | 按项目实际需求决定 |
| e2e-test | `config.settings.development` 或 staging settings | 接近真实环境 |
| production deploy | `config.settings.production` | 永远不在 CI 测试阶段使用 |

#### unit-test job 标准配置模板

```yaml
jobs:
  unit-test:
    runs-on: ubuntu-latest
    # 不需要 Redis service（test settings 使用 LocMemCache）
    env:
      DJANGO_SETTINGS_MODULE: config.settings.test
      SECRET_KEY: ci-test-secret-key
      DATABASE_URL: sqlite:///test.db
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: pytest apps/ --ignore=apps/e2e
```

---

## 经验二：unit-test job 是否需要 Redis service 的判断条件

### 经验摘要
Redis service 在 CI 中是额外的资源开销。unit-test job 是否需要 Redis，
完全取决于所用 Django settings 的 cache 后端配置，而不是项目是否"使用了 Redis"。

### 根因分析
- **问题 1**：`config.settings.development` 中 `CACHES` 指向 Redis（`django_redis`），
  DRF throttling 依赖 cache 后端，CI 没有 Redis service 时连接失败。
- 修复路径：将 unit-test job 的 settings 切换为 `config.settings.test`，
  test settings 中 `CACHES` 使用 `LocMemCache`（内存缓存），不需要任何外部服务。

### 规则 / 结论

**判断 unit-test job 是否需要 Redis service 的检查步骤：**

1. 查看 unit-test job 使用的 settings 文件（`DJANGO_SETTINGS_MODULE` 的值）。
2. 检查该 settings 中 `CACHES["default"]["BACKEND"]`：
   - `django.core.cache.backends.locmem.LocMemCache` → **不需要 Redis service**
   - `django_redis.cache.RedisCache` 或类似 → **需要 Redis service**
3. 同理检查 `CELERY_BROKER_URL`：
   - `memory://` 或 `CELERY_TASK_ALWAYS_EAGER=True` → **不需要 Redis/RabbitMQ service**
   - `redis://...` → **需要 Redis service**

**`config/settings/test.py` 必须包含的关键配置：**

```python
# 使用内存缓存，CI 不需要 Redis service
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery 同步执行，单元测试可断言任务结果
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# 使用内存 broker，不依赖外部消息队列
CELERY_BROKER_URL = "memory://"
```

---

## 经验三：新增 CI job 或修改 settings 时的 Checklist

在修改 `.github/workflows/*.yml` 或 `config/settings/` 时，必须逐项确认：

| 检查项 | 通过条件 |
|--------|---------|
| unit-test job 的 `DJANGO_SETTINGS_MODULE` | 必须是 `config.settings.test`，不得是 development |
| test settings 的 `CACHES` 后端 | 必须是 `LocMemCache`，不依赖 Redis |
| test settings 的 Celery 配置 | 必须有 `CELERY_TASK_ALWAYS_EAGER = True` |
| unit-test job 的 services 块 | 无需声明 Redis/RabbitMQ（由 test settings 保证） |
| e2e job 的 settings | 应接近真实环境，不使用 test settings |
| production 相关 settings | 绝不出现在任何 CI 测试 job 的 env 中 |
