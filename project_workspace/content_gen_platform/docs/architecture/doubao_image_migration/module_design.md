# 模块设计文档：豆包 Seedream 图片生成接入

**文档编号**：ARCH-MOD-IMG-001  
**版本**：v1.0  
**创建日期**：2026-05-13  
**状态**：DRAFT  
**输入文档**：REQ-SPEC-IMG-001 v0.2、ARCH-DES-IMG-001 v1.0  
**作者**：system-architect 子代理（由 PM 编排）

---

## 一、后端新增/修改模块清单

### 1.1 新增文件

| 文件路径 | 类型 | 说明 | 关联需求 |
|---------|------|------|---------|
| `apps/image_generator/doubao_image_client.py` | 新增 | 豆包 Ark 图片生成 HTTP 客户端 | FR-2、FR-3、ADR-01 |
| `apps/image_generator/migrations/0002_imagebatch_and_fields.py` | 新增 | 数据库迁移：新增 image_batch 表，ImageGenerationRequest 新增字段 | FR-5、ADR-04 |
| `apps/image_generator/tests/test_doubao_client.py` | 新增 | DoubaoImageClient 单元测试 | NFR-4 |
| `apps/image_generator/tests/test_batch_views.py` | 新增 | 批次 CRUD API 单元测试 | US-05 |
| `apps/image_generator/tests/test_batch_task.py` | 新增 | 批次生成 Celery task 单元测试（mock httpx）| FR-2、FR-5 |
| `apps/settings_vault/migrations/0002_add_doubao_image_service.py` | 新增 | settings_vault service_type 枚举新增 doubao_image | NFR-3 |

### 1.2 修改文件

| 文件路径 | 修改内容摘要 | 关联需求 |
|---------|------------|---------|
| `apps/image_generator/models.py` | 新增 `ImageBatch` 模型；`ImageGenerationRequest` 新增 `batch`, `model`, `provider` 字段 | FR-5、ADR-04 |
| `apps/image_generator/serializers.py` | 新增 `ImageBatchSerializer`、`ImageGenerationSubmitSerializer`（含 n≤4 约束）；更新 `ImageGenerationRequestSerializer` | FR-2、OQ-4 |
| `apps/image_generator/views.py` | 改造提交视图（ImageGenerationSubmitView）；新增批次 CRUD 视图（ImageBatchListView, ImageBatchDetailView） | FR-2、FR-3、FR-5、US-05 |
| `apps/image_generator/urls.py` | 新增批次相关路由 | FR-5 |
| `apps/image_generator/tasks.py` | 替换 Jimeng 客户端为 DoubaoImageClient；移除轮询循环；新增批次状态更新逻辑 | FR-2、FR-3、FR-4、ADR-03 |
| `apps/settings_vault/models.py` | `SERVICE_CHOICES` 追加 `doubao_image` | NFR-3、ADR-06 |
| `apps/media_library/service.py` | `create_media_item_from_url` 新增可选参数 `provider: str = ""`，透传到 MediaItem 相关逻辑（注：MediaItem 表本身不新增 provider 字段，见 ADR-04；provider 信息通过 ImageGenerationRequest.provider 关联查询） | FR-4 |
| `apps/image_generator/jimeng_image_client.py` | 文件顶部添加废弃注释，不删除，不再被调用 | OQ-1、ADR-02 |

### 1.3 不修改文件（确认复用）

| 文件路径 | 理由 |
|---------|------|
| `apps/media_library/models.py` | MediaItem 表结构无需变更（ADR-04） |
| `apps/notifications/service.py` | 直接复用 `push_notification_sync` |
| `core/volcengine_signing.py` | 豆包 Ark 图片接口使用 Bearer Token，无需 HMAC 签名（视频生成保留） |
| `apps/video_generator/jimeng_client.py` | 视频生成不在本期范围 |

---

## 二、关键类与方法签名

### 2.1 DoubaoImageClient（新增）

**文件**：`apps/image_generator/doubao_image_client.py`

```python
"""豆包 Ark 图片生成客户端（OpenAI 兼容协议，Bearer Token 认证）。"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger(__name__)

ARK_IMAGES_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

# 各模型支持的高级参数白名单（ADR-05）
MODEL_ADVANCED_PARAMS: dict[str, set[str]] = {
    "Doubao-Seedream-5.0-lite": {"seed", "guidance_scale", "negative_prompt", "watermark"},
    "Doubao-Seedream-4.5":      {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
    "Doubao-Seedream-4.0":      {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
}

SUPPORTED_MODELS: list[str] = list(MODEL_ADVANCED_PARAMS.keys())


@dataclass
class ImageGenerationResult:
    """单次 Ark 调用的返回结果。"""
    image_urls: list[str] = field(default_factory=list)


class DoubaoContentFilterError(Exception):
    """内容审核拒绝。"""

class DoubaoQuotaExceededError(Exception):
    """API 配额耗尽（429）。"""

class DoubaoAuthError(Exception):
    """认证失败（401）。"""


class DoubaoImageClient:
    """
    豆包 Ark 图片生成客户端。

    认证：Bearer Token（Ark API Key，由 settings_vault 解密提供，禁止硬编码）。
    接口：POST https://ark.cn-beijing.volces.com/api/v3/images/generations
    协议：OpenAI 兼容。
    """

    def __init__(self, api_key: str):
        # api_key 由调用方（Celery task）从 settings_vault 解密后传入
        # 此处仅存储，不做任何日志记录
        self._api_key = api_key

    def generate_images(
        self,
        prompt: str,
        model: str,
        n: int = 1,
        size: str = "1024x1024",
        ref_image_b64: Optional[str] = None,   # data URI 格式，图生图时使用
        advanced_params: Optional[dict] = None,
    ) -> ImageGenerationResult:
        """
        调用 Ark 接口生成图片。

        参数：
            prompt: 提示词（1-500 字符，调用方负责校验）
            model: 豆包模型版本（须在 SUPPORTED_MODELS 内）
            n: 生成张数（1-4，调用方负责校验）
            size: 图片尺寸，如 "1024x1024"
            ref_image_b64: base64 参考图（图生图），格式 "data:image/jpeg;base64,..."
            advanced_params: 高级参数 dict（函数内部按 MODEL_ADVANCED_PARAMS 过滤）

        返回：
            ImageGenerationResult（含 image_urls 列表）

        异常：
            DoubaoContentFilterError: 内容审核拒绝
            DoubaoQuotaExceededError: 配额耗尽
            DoubaoAuthError: 认证失败
            RuntimeError: 其他 HTTP 错误或无效响应
        """
        ...

    def _build_request_body(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str,
        ref_image_b64: Optional[str],
        advanced_params: Optional[dict],
    ) -> dict:
        """组装请求体，过滤不支持的高级参数。"""
        ...

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    def _post_with_retry(self, body: dict) -> dict:
        """执行 HTTP POST，对网络错误自动重试一次（5秒后）。"""
        ...

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """将 HTTP 错误响应映射为对应异常类型。"""
        ...
```

---

### 2.2 ImageBatch（新增模型）

**文件**：`apps/image_generator/models.py`（在现有文件追加）

```python
class ImageBatch(models.Model):
    """
    一次提交生成的图片批次记录。
    关联需求：FR-5、ADR-04。
    """
    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("processing", "生成中"),
        ("completed", "已完成"),
        ("partial_failed", "部分失败"),
        ("failed", "失败"),
    ]

    user            = models.ForeignKey(User, on_delete=models.CASCADE,
                                        related_name="image_batches")
    name            = models.CharField(max_length=255)
    model           = models.CharField(max_length=64)
    prompt          = models.TextField()
    is_img2img      = models.BooleanField(default=False)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_count     = models.IntegerField()       # 1-4，DB CHECK 约束
    completed_count = models.IntegerField(default=0)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "image_batch"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_count__gte=1) & models.Q(total_count__lte=4),
                name="image_batch_total_count_1_to_4",
            )
        ]

    def delete(self, *args, **kwargs):
        """
        级联删除前检查批次状态（AC-05-5）。
        处于 processing 状态时拒绝删除（由 View 层提前检查，此处为兜底）。
        """
        ...
```

**ImageGenerationRequest 新增字段**（追加到现有模型）：

```python
# 在 ImageGenerationRequest.Meta 之前追加
batch    = models.ForeignKey(
    "ImageBatch",
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name="requests",
)
model    = models.CharField(max_length=64, blank=True)     # 豆包模型名
provider = models.CharField(max_length=20, blank=True)     # "doubao" 或空（即梦历史数据）
```

---

### 2.3 Serializers（改造）

**文件**：`apps/image_generator/serializers.py`

```python
class ImageGenerationSubmitSerializer(serializers.Serializer):
    """
    POST /api/v1/image/generate/ 请求体校验。
    单批次最大 4 张（OQ-4）约束在此层实现。
    关联需求：FR-2、FR-3、AC-04-5、AC-01-5。
    """
    SUPPORTED_MODELS = [
        "Doubao-Seedream-5.0-lite",
        "Doubao-Seedream-4.5",
        "Doubao-Seedream-4.0",
    ]
    SUPPORTED_SIZES = ["1024x1024", "1280x720", "720x1280"]

    prompt          = serializers.CharField(min_length=1, max_length=500)
    model           = serializers.ChoiceField(choices=SUPPORTED_MODELS,
                                               default="Doubao-Seedream-4.5")
    n               = serializers.IntegerField(min_value=1, max_value=4, default=1)
                      # max_value=4 是 OQ-4 硬约束的实现层（AC-04-5）
    size            = serializers.ChoiceField(choices=SUPPORTED_SIZES,
                                               default="1024x1024")
    # 高级参数（折叠面板，默认不传）
    seed            = serializers.IntegerField(required=False, allow_null=True)
    negative_prompt = serializers.CharField(required=False, allow_blank=True)
    guidance_scale  = serializers.FloatField(required=False, allow_null=True)
    steps           = serializers.IntegerField(required=False, allow_null=True)
    watermark       = serializers.BooleanField(required=False, default=False)


class ImageBatchSerializer(serializers.ModelSerializer):
    """批次列表/详情序列化。"""
    requests = ImageGenerationRequestSerializer(many=True, read_only=True)

    class Meta:
        model = ImageBatch
        fields = (
            "id", "name", "model", "prompt", "is_img2img",
            "status", "total_count", "completed_count",
            "created_at", "updated_at", "requests",
        )
        read_only_fields = (
            "id", "model", "prompt", "is_img2img",
            "status", "total_count", "completed_count",
            "created_at", "updated_at",
        )
        # name 可通过 PATCH 修改（重命名，AC-05-3）


class ImageBatchListSerializer(serializers.ModelSerializer):
    """批次列表（不含 requests 详情，减少响应体大小）。"""
    class Meta:
        model = ImageBatch
        fields = (
            "id", "name", "model", "prompt", "is_img2img",
            "status", "total_count", "completed_count",
            "created_at",
        )
        read_only_fields = fields
```

---

### 2.4 改造后的 Celery Task

**文件**：`apps/image_generator/tasks.py`

```python
@shared_task(bind=True, max_retries=0)
def generate_image_task(self, batch_id: int) -> None:
    """
    豆包 Ark 图片批次生成流水线。
    关联需求：FR-2、FR-3、FR-4、FR-5、ADR-03、ADR-07。

    流程：
    1. 从 DB 加载 ImageBatch 及关联 ImageGenerationRequest（n 条）
    2. 从 settings_vault 读取解密后的 doubao_image API Key
    3. 若为图生图，读取临时文件并 base64 编码
    4. 调用 DoubaoImageClient.generate_images()（内部含重试）
    5. 清理临时参考图（try/finally，无论成功失败均执行）
    6. 逐张下载入库（create_media_item_from_url）
    7. 更新各 ImageGenerationRequest 状态
    8. 原子更新 ImageBatch.completed_count（F() 表达式）
    9. 判断并更新 ImageBatch.status（completed/partial_failed/failed）
    10. WebSocket 推送 image_completed × n + batch_completed × 1

    错误分类处理（ADR-07）：
    - DoubaoContentFilterError → failed，提示"提示词包含不允许的内容"
    - DoubaoQuotaExceededError → failed，提示"配额已耗尽"
    - DoubaoAuthError → failed，提示"API Key 无效"
    - 网络类错误 → tenacity 已在客户端层重试，耗尽后在此置 failed
    - 其他 RuntimeError → failed，记录完整 error_message

    日志记录（NFR-4）：
    - 记录：model, batch_id, task_id, 耗时, 成功/失败原因
    - 禁止记录 API Key 任何形式
    """
    ...
```

---

## 三、数据库迁移方案

### 3.1 迁移文件：`0002_imagebatch_and_fields.py`

**操作列表**（有序，PostgreSQL 安全）：

1. 创建 `image_batch` 表（全新表，无依赖）
2. 在 `image_generation_request` 表新增列：
   - `batch_id` INTEGER NULL，FK → `image_batch.id` ON DELETE SET NULL
   - `model` VARCHAR(64) NOT NULL DEFAULT ''
   - `provider` VARCHAR(20) NOT NULL DEFAULT ''
3. 新增 DB-level CHECK 约束：`image_batch_total_count_1_to_4`（total_count BETWEEN 1 AND 4）
4. 在 `settings_service_config` 表的 `service_type` 字段：Django choice 层添加 `doubao_image`（无需 DB migration，choices 在 Django 层维护）

**说明**：
- 现有 `image_generation_request` 表中的历史记录：`batch_id=NULL`, `model=''`, `provider=''`，符合 OQ-5 决策（保留原样）。
- `model` 和 `provider` 字段使用 `DEFAULT ''` 而非 `NULL`，原因：新记录必须填写，历史记录保持空字符串即可。

### 3.2 迁移文件：`apps/settings_vault/migrations/0002_add_doubao_image_service.py`

Django choices 变更通常不需要 DB migration（choices 在 Python 层约束）。但为保持迁移记录一致性，生成一个空 migration 文件作为版本锚点：

```python
# 空迁移，仅记录 service_type 枚举变更的版本信息
class Migration(migrations.Migration):
    dependencies = [("settings_vault", "0001_initial")]
    operations = []
```

### 3.3 回滚方案

**PostgreSQL 回滚脚本**（在 migration 的 `database_backwards` 方法中实现）：

```sql
-- 回滚 image_generation_request 新增字段
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS batch_id;
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS model;
ALTER TABLE image_generation_request DROP COLUMN IF EXISTS provider;

-- 回滚 image_batch 表（会级联删除 FK 约束）
DROP TABLE IF EXISTS image_batch;
```

**Django 命令**：
```bash
python manage.py migrate image_generator 0001_initial
```

**注意事项**：
- 回滚后，豆包接入代码需同步切换回旧版本（代码回滚）。
- 历史即梦数据不受影响（`batch_id`, `model`, `provider` 字段回滚后消失，原有字段不变）。

---

## 四、REST API 端点设计

### 4.1 新增/改造端点总览

| 方法 | 路径 | 视图类 | 说明 |
|------|------|--------|------|
| POST | `/api/v1/image/generate/` | `ImageGenerationSubmitView`（改造） | 提交批次生成请求 |
| GET | `/api/v1/image/generate/{pk}/status/` | `ImageGenerationStatusView`（保留） | 单个请求状态查询（降级轮询） |
| GET | `/api/v1/image/history/` | `ImageGenerationListView`（保留） | 用户生成历史 |
| GET | `/api/v1/image/batches/` | `ImageBatchListView`（新增） | 批次列表（分页） |
| GET | `/api/v1/image/batches/{id}/` | `ImageBatchDetailView`（新增） | 批次详情（含图片列表） |
| PATCH | `/api/v1/image/batches/{id}/` | `ImageBatchDetailView`（新增） | 批次重命名 |
| DELETE | `/api/v1/image/batches/{id}/` | `ImageBatchDetailView`（新增） | 批次删除（级联） |

---

### 4.2 POST `/api/v1/image/generate/`（改造）

**请求体**（`multipart/form-data` 或 `application/json`）：

```json
{
  "prompt": "日落时分的海边灯塔",
  "model": "Doubao-Seedream-4.5",
  "n": 2,
  "size": "1024x1024",
  "seed": 42,
  "negative_prompt": "",
  "guidance_scale": 7.5,
  "steps": null,
  "watermark": false
}
```

图生图时，`ref_image` 作为 `multipart/form-data` 文件字段上传（与现有保持一致）。

**成功响应 202 Accepted**：

```json
{
  "batch_id": 55,
  "batch_name": "0513-1430 日落时分的海边...",
  "request_ids": [101, 102],
  "status": "pending",
  "total_count": 2
}
```

**错误响应**：

| 场景 | HTTP 状态码 | 响应体 |
|------|-----------|--------|
| `n > 4` | 400 | `{"error": "单批次最多生成 4 张图片"}` |
| 不支持的模型 | 400 | `{"error": "不支持的模型版本"}` |
| 未配置 API Key | 400 | `{"error": "请先在设置中配置豆包 Ark API Key"}` |
| 参考图格式不符 | 400 | `{"error": "参考图片仅支持 JPEG 和 PNG 格式"}` |
| 参考图超大 | 400 | `{"error": "参考图片大小不能超过 10 MB"}` |

---

### 4.3 GET `/api/v1/image/batches/`（新增）

**查询参数**：
- `page`（默认 1）
- `page_size`（默认 20，最大 100）

**成功响应 200 OK**：

```json
{
  "count": 35,
  "next": "/api/v1/image/batches/?page=2",
  "previous": null,
  "results": [
    {
      "id": 55,
      "name": "0513-1430 日落时分的海边...",
      "model": "Doubao-Seedream-4.5",
      "prompt": "日落时分的海边灯塔",
      "is_img2img": false,
      "status": "completed",
      "total_count": 2,
      "completed_count": 2,
      "created_at": "2026-05-13T14:30:00Z"
    }
  ]
}
```

---

### 4.4 GET `/api/v1/image/batches/{id}/`（新增）

**成功响应 200 OK**：

```json
{
  "id": 55,
  "name": "0513-1430 日落时分的海边...",
  "model": "Doubao-Seedream-4.5",
  "prompt": "日落时分的海边灯塔",
  "is_img2img": false,
  "status": "completed",
  "total_count": 2,
  "completed_count": 2,
  "created_at": "2026-05-13T14:30:00Z",
  "updated_at": "2026-05-13T14:30:45Z",
  "requests": [
    {
      "id": 101,
      "status": "completed",
      "progress": 100,
      "media_item_id": 201,
      "error_message": "",
      "created_at": "2026-05-13T14:30:00Z"
    },
    {
      "id": 102,
      "status": "completed",
      "progress": 100,
      "media_item_id": 202,
      "error_message": "",
      "created_at": "2026-05-13T14:30:00Z"
    }
  ]
}
```

---

### 4.5 PATCH `/api/v1/image/batches/{id}/`（重命名，新增）

**请求体**：

```json
{"name": "海边灯塔系列 v2"}
```

**成功响应 200 OK**：返回更新后的批次对象（同 GET 格式，不含 requests 列表）。

**错误响应**：

| 场景 | HTTP 状态码 | 响应体 |
|------|-----------|--------|
| 批次不存在或非本人 | 404 | `{"detail": "Not found."}` |
| name 为空 | 400 | `{"name": ["该字段不能为空。"]}` |

---

### 4.6 DELETE `/api/v1/image/batches/{id}/`（删除，新增）

**成功响应 204 No Content**：空响应体。

**错误响应**：

| 场景 | HTTP 状态码 | 响应体 |
|------|-----------|--------|
| 批次生成中（status=processing）| 409 | `{"error": "批次生成中，无法删除"}` |
| 批次不存在或非本人 | 404 | `{"detail": "Not found."}` |

---

## 五、WebSocket 事件 Schema

所有事件通过 `notifications.service.push_notification_sync` 推送，走 Django Channels，频道组名为 `user_{user_id}`。

### 5.1 `batch_progress`

```json
{
  "event_type": "batch_progress",
  "payload": {
    "batch_id": 55,
    "status": "processing"
  }
}
```

触发时机：Celery task 开始执行，更新 ImageBatch.status = "processing" 后推送。

---

### 5.2 `image_completed`

```json
{
  "event_type": "image_completed",
  "payload": {
    "batch_id": 55,
    "request_id": 101,
    "media_item_id": 201,
    "file_url": "/media/images/3/abcdef123456.jpg",
    "completed_count": 1,
    "total_count": 2
  }
}
```

触发时机：每张图片入库成功后推送（满足 AC-03-4）。`completed_count` 帮助前端更新进度显示。

---

### 5.3 `image_failed`

```json
{
  "event_type": "image_failed",
  "payload": {
    "batch_id": 55,
    "request_id": 102,
    "error": "提示词包含不允许的内容，请修改后重试"
  }
}
```

触发时机：单张图片生成失败后推送。

---

### 5.4 `batch_completed`

```json
{
  "event_type": "batch_completed",
  "payload": {
    "batch_id": 55,
    "status": "completed",
    "completed_count": 2,
    "total_count": 2
  }
}
```

触发时机：批次内所有图片处理完毕（无论全部成功、部分失败或全部失败）后推送。`status` 取值：`completed` / `partial_failed` / `failed`。

---

## 六、前端组件清单

### 6.1 新增/改造组件

| 组件路径 | 类型 | 说明 | 关联 US |
|---------|------|------|---------|
| `src/frontend/src/components/ImageGenerator/ModelSelector.vue` | 新增 | 模型选择下拉框（Doubao 三版本，默认 4.5，无即梦选项） | US-01 |
| `src/frontend/src/components/ImageGenerator/AdvancedParamsPanel.vue` | 新增 | 高级参数折叠面板（el-collapse），含 seed/negative_prompt/guidance_scale/steps/watermark | US-01、US-02 |
| `src/frontend/src/components/ImageGenerator/BatchCountSelector.vue` | 新增 | 生成张数选择器（el-input-number，min=1 max=4 默认 1） | US-01、US-04 |
| `src/frontend/src/views/ImageGenerator/GeneratorPage.vue` | 改造 | 主页面，集成 ModelSelector、AdvancedParamsPanel、BatchCountSelector、RefImageUpload | US-01、US-02 |
| `src/frontend/src/views/ImageGenerator/BatchListPage.vue` | 新增 | 批次列表页面（分页、重命名、删除操作） | US-05 |
| `src/frontend/src/views/ImageGenerator/BatchDetailPage.vue` | 新增 | 批次详情页面（缩略图网格） | US-05 |
| `src/frontend/src/store/imageBatch.js` | 新增 | Pinia store，管理批次状态、WebSocket 事件处理 | US-04、US-05 |
| `src/frontend/src/api/imageGenerator.js` | 改造 | 新增批次 API 调用函数（getBatches, getBatchDetail, renameBatch, deleteBatch） | US-05 |

### 6.2 前端校验规则（对应后端约束）

| 校验规则 | 前端实现位置 | 对应后端约束 |
|---------|-----------|-----------|
| 提示词 1-500 字符 | `GeneratorPage.vue` el-form 规则 | `ImageGenerationSubmitSerializer.prompt` |
| 生成张数 1-4 | `BatchCountSelector.vue` el-input-number `max=4` | `ImageGenerationSubmitSerializer.n max_value=4` |
| 模型必选 | `ModelSelector.vue` el-select `required` | `ImageGenerationSubmitSerializer.model ChoiceField` |
| 参考图 JPEG/PNG / ≤10MB | `GeneratorPage.vue` el-upload `before-upload` hook | `ImageGenerationSubmitView` 文件校验 |
| 未配置 API Key 时禁止提交 | `GeneratorPage.vue`（调用 `GET /api/v1/settings/configs/doubao_image/` 检查是否存在配置） | `generate_image_task` 中 `UserServiceConfig.DoesNotExist` 处理 |

---

*文档版本 v1.0，状态 DRAFT，等待 PM 门控评审。*
