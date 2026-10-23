# Knowledge Base — software_developer
<!-- 记录开发过程中积累的代码实现经验教训 -->

---

## SD-L001: DRF 注册接口 — 必须包含 password2 确认字段

**日期**: 2026-04-10  
**文件**: `apps/accounts/serializers.py`

本项目 `RegisterSerializer` 继承 `ModelSerializer`，明确要求 `password2` 字段。
任何调用注册 API 的代码（前端、测试、脚本）都必须传递。

```python
# serializers.py 摘要
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)  # 必须！

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "两次密码不一致"})
        return attrs
```

---

## SD-L002: 发布任务 API — 返回列表而非单对象

**日期**: 2026-04-10  
**文件**: `apps/publisher/views.py`

`POST /api/v1/publisher/tasks/` 接受 `platform_account_ids`（列表），
可一次对多个平台账号发布，响应是任务列表 `[{id, status, ...}]`。

```python
# 正确调用方式
{
    "content_id": 123,
    "platform_account_ids": [1, 2],  # 复数列表
}
# 响应: [{"id": 10, "status": "pending"}, {"id": 11, "status": "pending"}]
```

---

## SD-L003: 前端 API URL 路径 — knowledge 不是 knowledge-base

**日期**: 2026-04-10  
**问题**: 前端 `kbAPI` 使用 `/knowledge-base/documents/` 导致 404

**根因**: 后端 `config/urls.py` 注册路径是 `path("knowledge/", ...)`，
但前端 API 配置里用了 `/knowledge-base/`。

**已修复** `src/frontend/src/api/index.js`:
```js
export const kbAPI = {
  list: (params) => api.get("/knowledge/documents/", { params }),
  // 正确路径是 /knowledge/ 不是 /knowledge-base/
};
```

**教训**: 修改路由时前后端必须同步检查。

---

## SD-L004: JWT 过期 — 前端主动刷新策略

**日期**: 2026-04-10  
**文件**: `src/frontend/src/App.vue`

`App.vue` onMounted 中主动检查 token 剩余时间，不足 5 分钟则刷新，
避免进入页面后立即出现 401：

```js
onMounted(async () => {
  if (!authStore.accessToken) return;
  try {
    const payload = JSON.parse(atob(authStore.accessToken.split('.')[1]));
    const expiresSoon = Date.now() / 1000 >= payload.exp - 300;
    if (expiresSoon) {
      await authStore.refreshToken();
    }
  } catch {
    // 格式错误的 token — 让拦截器处理 401
  }
  if (!authStore.user) {
    await authStore.fetchProfile();
  }
});
```

---

## SD-L005: SSE 流 — backend 必须捕获异常并发送 done:true

**日期**: 2026-04-10  
**文件**: `apps/llm_gateway/views.py`

SSE stream 如果抛出异常但没有发送 `done:true`，前端 `generating.value` 永远不会置 false，
用户看到无限 "生成中..."。

**修复要点**:
1. `_run()` 内用 `try/except` 捕获异常，发送 `{"done": true, "error": str(exc)}`
2. 外层 while 循环也要 `except Exception` 兜底

**前端同步修复**:  
while 循环结束后检查 `generating.value` 是否仍为 true，是则强制置 false。

---

## SD-L006: ElementPlus 3.x — el-radio 使用 value 不是 label

**日期**: 2026-04-10  
**文件**: `src/frontend/src/views/SettingsView.vue`

ElementPlus 3.x 中 `el-radio` 的 `label` prop 已废弃，应使用 `value`。

```html
<!-- 错误（产生废弃警告）-->
<el-radio label="deepseek">DeepSeek</el-radio>

<!-- 正确 -->
<el-radio value="deepseek">DeepSeek</el-radio>
```

---

## SD-L008: SettingsView 表单验证 — 空字段用 warning 不用 error

**日期**: 2026-04-10  
**文件**: `src/frontend/src/views/SettingsView.vue`

前端验证空必填字段时使用 `ElMessage.warning()`，不是 `ElMessage.error()`：

```js
if (!llmForm.value.api_key) {
  ElMessage.warning("请填写 API Key");  // warning！
  return;
}
```

产生的 DOM class 是 `.el-message--warning`。
任何需要检查此提示的测试/E2E 必须用 `warning` class，不是 `error`。

---

## SD-L007: 测试隔离 — UserRateThrottle 在共享 locmem 缓存中累积

**日期**: 2026-04-10  
**文件**: `config/settings/test.py`, `config/settings/local_test.py`

`UserRateThrottle`（100次/小时）在 locmem 缓存中跨测试累积，当单次测试 session
请求超过阈值时出现 429 错误。

**修复**: 在测试 settings 中禁用 throttle：
```python
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
```

---

## SD-L012: JWT 刷新 — ROTATE_REFRESH_TOKENS=True 时必须保存新 refresh token

**日期**: 2026-04-11  
**文件**: `src/frontend/src/stores/auth.js`, `src/frontend/src/api/index.js`

**问题**: 后端 `ROTATE_REFRESH_TOKENS=True` 时，每次刷新 access token 同时
返回一个新的 refresh token（旧的被加入黑名单）。但 `auth.js` 的 `refreshToken()`
只保存了 `data.access`，忽略了 `data.refresh`。

**后果**: 15 分钟后（access token 再次过期），store 用的仍是旧的（已黑名单）
refresh token 刷新 → 后端返回 401 → 用户被强制退出。

**修复**:
```js
async refreshToken() {
  const { data } = await authAPI.refreshToken(this.refreshTokenVal)
  this.accessToken = data.access
  localStorage.setItem('access_token', data.access)
  // 必须保存轮换后的新 refresh token！
  if (data.refresh) {
    this.refreshTokenVal = data.refresh
    localStorage.setItem('refresh_token', data.refresh)
  }
},
```

---

## SD-L013: JWT 刷新 — 并发 401 必须用 Promise 互斥锁

**日期**: 2026-04-11  
**文件**: `src/frontend/src/api/index.js`, `src/frontend/src/App.vue`

**问题**: 页面同时有多个 API 请求，access token 刚好过期 → 全部收到 401 →
拦截器各自独立调用 `refreshToken()` → N 次并发刷新。

在 `ROTATE_REFRESH_TOKENS=True` 下，第一个刷新成功后旧 token 被黑名单，
后续刷新都返回 401 → 用户被退出登录（俗称"401 风暴"）。

**修复**: 用 `_refreshPromise` 变量实现互斥锁——刷新进行中时所有并发调用
共享同一个 Promise，避免多次请求：

```js
let _refreshPromise = null;

export function ensureTokenRefreshed(auth) {
  if (!_refreshPromise) {
    _refreshPromise = auth.refreshToken().finally(() => {
      _refreshPromise = null;
    });
  }
  return _refreshPromise;
}

// 拦截器中用 ensureTokenRefreshed(auth) 代替 auth.refreshToken()
// App.vue onMounted 的主动刷新也必须走同一个函数，防止与拦截器竞争
```

**原则**: 任何地方需要刷新 token，一律通过 `ensureTokenRefreshed()` 调用，
不直接调用 `auth.refreshToken()`。

---

## SD-L009: Celery 队列路由 — CELERY_TASK_DEFAULT_QUEUE 必须与 worker -Q 对齐

**日期**: 2026-04-11  
**文件**: `config/settings/base.py`, `docker-compose.yml`

**问题**: Celery 内置默认队列名是 `celery`，但 docker-compose.yml 中
celery_worker 启动参数是 `-Q default,video,publish`，只消费 `default` 队列。
未设置 `CELERY_TASK_DEFAULT_QUEUE` 时，所有没有显式 `queue=` 的任务都发送到
`celery` 队列，worker 永远不会处理它们。

**现象**: 上传文档后状态永远停留在"处理中"（`processing`），`chunk_count=0`。

**修复**:
```python
# config/settings/base.py
CELERY_TASK_DEFAULT_QUEUE = "default"  # 必须与 worker -Q 里的队列名一致
```

**教训**: 每次修改 docker-compose.yml 中 worker 的 `-Q` 参数，或新增
`CELERY_TASK_DEFAULT_QUEUE`，必须同步检查另一侧。两者不一致会导致任务
静默积压而无任何报错。

---

## SD-L011: 嵌入模型选型 — 生产环境优先用轻量中文模型

**日期**: 2026-04-11  
**文件**: `config/settings/base.py`, `apps/knowledge_base/models.py`, `Dockerfile`

**问题**: `BAAI/bge-m3`（2.3 GB，1024维）在阿里云 ECS 小实例上处理文档时失败：
- 首次使用需从 hf-mirror.com 下载 2.3 GB，易超时或因磁盘空间不足失败
- 加载模型本身需要 ~2.3 GB RAM，小实例（2-4 GB）OOM

**修复**: 切换至 `BAAI/bge-small-zh-v1.5`（90 MB，512维）：
- RAM 占用仅 ~250 MB，小实例完全可以承受
- 专为中文优化，RAG 场景质量足够
- 在 Dockerfile 中 CI 构建时预下载（GitHub Actions 有 HuggingFace 直连），无需运行时下载

**Dockerfile 预下载模式**:
```dockerfile
# 在 pip install 之后，COPY 代码之前（利用 Docker 层缓存）
ARG EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

COPY . .
```

**向量维度同步要求**:
- `VectorField(dimensions=512)` 必须与模型输出维度一致
- 切换模型时需创建 migration 修改列类型
- 单元测试 mock `np.zeros((1, 512), ...)` 也要同步修改

**原则**: 生产首选 `bge-small-zh-v1.5`（512维）；如需更高质量改用 `bge-base-zh-v1.5`（768维，400 MB）；`bge-m3`（1024维）仅适合有 GPU 或充裕内存的大实例。

---

## SD-L014: Celery 任务 — 必须设置 soft_time_limit 防止 OOM 导致永久 "processing"

**日期**: 2026-04-16  
**文件**: `apps/knowledge_base/tasks.py`

**问题**: `process_document_task` 调用 `model.encode(chunks)` 时，大型 DOCX
会产生大量 chunk，全部一次性传入 encode 导致峰值 RAM 超限，
Linux OOM killer 发送 **SIGKILL** 杀掉 worker 进程。

SIGKILL 是 OS 信号，Python 的 `try/except Exception` **完全无法捕获**，
所有异常处理代码都不会执行，文档永久停留在 `"processing"` 状态。

**双重修复**：

1. **`batch_size=32`**（services.py）— 分批编码，峰值 RAM 可控：
```python
embeddings = model.encode(
    chunks, batch_size=32, show_progress_bar=False, normalize_embeddings=True
)
```

2. **`soft_time_limit=300`**（tasks.py）— Celery 发 SIGUSR1（Python 可捕获）而非 SIGKILL：
```python
from celery.exceptions import SoftTimeLimitExceeded

@shared_task(bind=True, max_retries=0, soft_time_limit=300)
def process_document_task(self, document_id: int) -> None:
    try:
        _process_document(document_id)
    except SoftTimeLimitExceeded:
        Document.objects.filter(pk=document_id).update(
            status="error",
            error_message="处理超时，请重试或联系管理员（文档可能过大）",
        )
    except Exception as exc:
        Document.objects.filter(pk=document_id).update(
            status="error", error_message=f"Task error: {exc}"
        )
```

**通用规则**:
- 处理文件/ML 推理的 Celery task 必须设 `soft_time_limit`（发 Python 异常）
- `soft_time_limit` 必须有对应的 `SoftTimeLimitExceeded` 测试
- `except Exception` 挡不住 SIGKILL，只有 `soft_time_limit` + `batch_size` 才能防止永久 "processing"

---

## SD-L015: 嵌入编码 — model.encode() 必须指定 batch_size 防止 OOM

**日期**: 2026-04-16  
**文件**: `apps/knowledge_base/services.py`

**问题**: `model.encode(chunks)` 默认一次性编码所有输入，峰值内存 ∝ chunk 数量。
对于大型文档（数百 chunk），这会耗尽 Celery worker 的可用 RAM，
触发 OOM killer 的 SIGKILL，文档永久卡在 "processing"。

**正确做法**：始终传 `batch_size`：
```python
embeddings = model.encode(
    chunks,
    batch_size=32,           # 每批 32 个 chunk，峰值内存可控
    show_progress_bar=False,
    normalize_embeddings=True,
)
```

**规则**: 凡是对可变长度列表调用 ML 推理（encode/predict/embed），
必须指定 `batch_size` 或等效的分批参数，且该参数必须有测试断言。

---

## SD-L010: Celery 任务 — max_retries=0 避免 retry 覆盖 error 状态

**日期**: 2026-04-11  
**文件**: `apps/knowledge_base/tasks.py`

`_process_document()` 内部捕获所有异常并将文档状态设为 `error`。
如果任务设置了 `max_retries > 0`，retry 会把状态重置回 `processing`，
用户看到文档闪烁或永远卡在处理中。

**正确做法**:
```python
@shared_task(bind=True, max_retries=0)
def process_document_task(self, document_id: int) -> None:
    try:
        _process_document(document_id)
    except Exception as exc:
        # _process_document 意外抛出时兜底（如 DB 宕机）
        Document.objects.filter(pk=document_id).update(
            status="error", error_message=f"Task error: {exc}"
        )
```
