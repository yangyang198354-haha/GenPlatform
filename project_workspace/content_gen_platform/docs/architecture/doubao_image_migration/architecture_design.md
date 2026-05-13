# 架构设计文档：豆包 Seedream 图片生成接入

**文档编号**：ARCH-DES-IMG-001  
**版本**：v1.0  
**创建日期**：2026-05-13  
**状态**：DRAFT  
**输入文档**：REQ-SPEC-IMG-001 v0.2、REQ-US-IMG-001 v0.2、REQ-OQ-IMG-001 v0.2  
**作者**：system-architect 子代理（由 PM 编排）

---

## 一、高层架构概览

### 1.1 架构分层描述

本次迁移在现有 Django + Celery + Redis + PostgreSQL + WebSocket 技术栈上进行，不引入新的基础设施层。整体架构分为五层：

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层（Vue 3 + Element Plus）            │
│  图片生成页面（模型选择 / 高级参数折叠面板 / 批次管理 Tab）         │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API（HTTP/HTTPS）
                             │ WebSocket（Django Channels）
┌────────────────────────────▼────────────────────────────────────┐
│                     Django REST 层                               │
│  image_generator/views.py（提交 / 状态查询 / 批次 CRUD）          │
│  image_generator/serializers.py（请求校验，含 n≤4 硬约束）        │
└────────────────────────────┬────────────────────────────────────┘
                             │ Celery 任务调度（Redis Broker）
┌────────────────────────────▼────────────────────────────────────┐
│                   Celery Worker 层                               │
│  generate_image_task（豆包 Ark HTTP 调用 / 入库 / WebSocket 推送）│
│  DoubaoImageClient（Bearer Token / httpx 同步调用）              │
└────────┬──────────────────────────────────┬─────────────────────┘
         │                                  │
         │ PostgreSQL                        │ 火山方舟 Ark API
┌────────▼──────────┐              ┌────────▼───────────────────┐
│  数据库层           │              │  外部服务层                  │
│  ImageBatch        │              │  POST /api/v3/images/      │
│  ImageGeneration   │              │      generations           │
│  Request           │              │  Bearer Token 认证          │
│  MediaItem         │              │  同步响应（返回图片 URL）      │
│  UserServiceConfig │              └────────────────────────────┘
└───────────────────┘
```

### 1.2 与现有系统的关键变化

| 维度 | 改造前（即梦） | 改造后（豆包 Ark） |
|------|-------------|----------------|
| 认证方式 | HMAC-SHA256 签名 | Bearer Token |
| API 调用模式 | CVProcess 提交 + CVGetResult 轮询 | 单次 POST 同步返回 |
| Celery 任务结构 | 提交 + 轮询循环（最多 60 次） | 单次 HTTP 调用，无轮询循环 |
| 批次概念 | 无 | 新增 ImageBatch 模型 |
| 模型选择 | 无（固定） | 用户可选三种 Seedream 版本 |
| 高级参数 | 无 | 折叠面板暴露 |
| 多张生成 | 不支持（1张/次） | 支持 1-4 张/批次 |
| MediaItem 标记 | source=ai_generated（无 provider） | 新增 provider=doubao，batch_id 关联 |

---

## 二、架构决策记录（ADR）

---

### ADR-01：豆包 Ark 客户端实现方案

**关联需求**：FR-2、FR-3、NFR-3、NFR-5

**背景**：需要选择调用 `https://ark.cn-beijing.volces.com/api/v3/images/generations` 的客户端实现方式。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A（已决）| 直接使用 `httpx` 发起 HTTP POST，Bearer Token 手动注入 | 无额外依赖，与现有 `VolcanoProvider`（llm_gateway）模式完全一致；代码透明可控 | 需手动处理重试、超时、错误码映射 |
| B | 使用 `openai` Python SDK（openai>=1.0 兼容 base_url 替换） | SDK 封装省代码 | 引入 `openai` 包，但该项目中 LLM 调用均为手写 HTTP，风格不一致；SDK 对图片接口的参数校验可能与 Ark 实现存在差异 |
| C | 使用 `volcengine-python-sdk` | 官方 SDK | SDK 体积大、主要面向视频/通用 API；图片接口尚无完整支持；版本维护不稳定 |

**决策**：选择选项 A — 直接 `httpx` + Bearer Token。

**理由**：
1. 与现有 `VolcanoProvider`（`llm_gateway/providers.py`）保持一致的编码风格，`VOLCANO_BASE_URL` 已定义为 `https://ark.cn-beijing.volces.com/api/v3`，本次只需新建 `DoubaoImageClient` 类，端点为 `{VOLCANO_BASE_URL}/images/generations`。
2. 零新增强依赖：`httpx` 已在 `requirements.txt` 中。
3. 豆包 Ark 图片接口为 OpenAI 兼容格式，请求体字段明确，无需 SDK 封装。

**影响**：
- 新建 `apps/image_generator/doubao_image_client.py`（不删除 `jimeng_image_client.py`，停止调用即可）。
- 错误处理须在客户端层手动实现（见 ADR-07）。
- Celery task 无轮询循环（Ark 为同步响应，见 ADR-03）。

---

### ADR-02：即梦代码替换策略

**关联需求**：OQ-1、FR-1、NFR-2（US-06）

**背景**：OQ-1 已决"完全替换"，需决定 `jimeng_image_client.py` 的处置方式。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A（已决）| 保留文件，在代码中完全停止调用；所有 import 替换为 DoubaoImageClient | 历史提交可追溯；万一回滚可快速切换 | 项目中存在"死代码" |
| B | 物理删除 `jimeng_image_client.py` | 代码库最干净 | git 历史仍可查到；回滚成本略高；与 `video_generator/jimeng_client.py`（保留）混淆 |
| C | 保留文件并标记 `@deprecated` | 语义清晰 | 增加维护成本 |

**决策**：选择选项 A — 保留文件，停止调用。

**理由**：
1. OQ-1 原文"文件可保留但不再被任何代码路径调用"与本决策一致。
2. `video_generator/jimeng_client.py` 需继续保留（视频生成不在本期范围），两个 jimeng 文件并存不混乱。
3. 保留文件使回滚成本最低（紧急情况下不需要从 git 恢复文件再改 import）。

**影响**：
- `apps/image_generator/tasks.py` 中删除对 `JimengImageClient` 的 import，改为 `DoubaoImageClient`。
- `apps/image_generator/views.py` 无需改动（任务调度逻辑不感知客户端类型）。
- `apps/settings_vault/models.py`：`SERVICE_CHOICES` 新增 `doubao_image`，保留 `jimeng`（历史数据兼容）。
- 在 `jimeng_image_client.py` 文件顶部添加注释说明文件已停用，仅供历史参考。

---

### ADR-03：异步任务模式

**关联需求**：FR-2、FR-3、NFR-1、NFR-2、AC-03-4

**背景**：豆包 Ark `/images/generations` 为同步接口（POST 即返回图片 URL），与原即梦的"提交任务 + 轮询"模式有根本不同。需重新设计 Celery 任务结构。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A（已决）| 保留 Celery 任务，任务内单次同步 HTTP 调用 Ark，无轮询循环 | 与现有 Celery 架构一致；POST 接口在 500ms 内返回 202；进度推送简化为"pending→completed" | 任务执行时间取决于 Ark 响应时间（通常数秒到数十秒） |
| B | 改为 View 层同步等待（无 Celery） | 简单 | 阻塞 Django 线程；无法支持多张并发；违反 NFR-1（POST 须 500ms 内返回） |
| C | Webhook 回调（Ark 主动推送） | 理论上最优 | Ark 图片接口不支持 Webhook 回调模式 |

**决策**：选择选项 A — 保留 Celery，任务内单次 HTTP 同步调用，取消轮询循环。

**批次内多张图片处理策略（n > 1 时）**：

Ark `/images/generations` 接口支持 `n` 参数（一次请求最多返回 4 张图片 URL）。因此：

- **优先方案（推荐）**：单次 Celery 任务，`n` 参数传入 Ark，一次 HTTP 请求返回所有 URL，逐一调用 `create_media_item_from_url` 入库，逐一推送 `image_completed` 事件。
- **降级方案**（若 Ark 实际不支持 `n > 1`）：同一 `ImageBatch` 的每张图片创建独立 `ImageGenerationRequest`，由同一 Celery 任务按序执行。Celery 任务参数增加 `batch_id`，最终统一更新 `ImageBatch.status`。

开发阶段以优先方案实现，并设计降级开关（`settings.DOUBAO_BATCH_MODE = "single_request" | "multi_request"`）。

**Celery 任务结构改造对比**：

```
改造前（即梦）：
generate_image_task(request_id)
  ├── submit_image_task()  → 获取 task_id
  └── for 60次: poll_image_status()  → 等待完成

改造后（豆包）：
generate_image_task(request_id, batch_id)
  ├── DoubaoImageClient.generate_images()  → 直接返回 [url1, url2, ...]
  ├── for url in urls: create_media_item_from_url()
  ├── for url in urls: push_notification_sync("image_completed")
  └── update ImageBatch.status
```

**影响**：
- `tasks.py` 重写（无轮询循环，无 `asyncio.run` 调用，改为同步 `httpx` 调用）。
- 进度推送策略简化：仅推送"pending→processing→completed/failed"三态，无百分比进度。

---

### ADR-04：ImageBatch 数据模型设计与 media_library 的关联

**关联需求**：FR-4、FR-5、AC-04-1 至 AC-04-5、US-05

**背景**：需新增 `ImageBatch` 模型，并确定其与 `ImageGenerationRequest`、`MediaItem` 的关联方式。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A（已决）| `ImageBatch` 独立表；`ImageGenerationRequest` 通过 FK 关联 `ImageBatch`；`MediaItem` 通过 `ImageGenerationRequest.media_item` 间接关联批次 | 数据层次清晰；`MediaItem` 无需改动模型（仅通过关联查询即可找到 batch）；`ImageGenerationRequest` 已有 `media_item` FK | `MediaItem` 本身无 `batch_id` 字段，批次查询需 JOIN |
| B | `MediaItem` 直接新增 `batch_id` FK | 查询路径最短 | `MediaItem` 是通用模型（视频/音频也用），加图片专用字段污染模型；历史 jimeng 数据的 `batch_id` 为 null 需特殊处理 |
| C | 新增 `BatchMediaItem` 中间表 | 解耦彻底 | 过度设计，增加 JOIN 层数 |

**决策**：选择选项 A — `ImageBatch` 独立表 + `ImageGenerationRequest.batch` FK 关联。

**理由**：
1. `MediaItem` 是通用媒体资产模型，保持干净是 NFR-5 可扩展性的要求。
2. 批次查询路径：`ImageBatch → ImageGenerationRequest → MediaItem`，通过 Django ORM `prefetch_related` 一次查出，性能可接受（批次内最多 4 张）。
3. 历史即梦数据的 `ImageGenerationRequest.batch` 为 null，查询批次列表时过滤 `batch__isnull=False` 即可排除（满足 AC-06-2）。

**ImageBatch 最终模型字段**（与需求规格 4.1 完全对齐）：

```python
class ImageBatch(models.Model):
    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("processing", "生成中"),
        ("completed", "已完成"),
        ("partial_failed", "部分失败"),
        ("failed", "失败"),
    ]
    user             = models.ForeignKey(User, on_delete=models.CASCADE)
    name             = models.CharField(max_length=255)          # 批次名称，可重命名
    model            = models.CharField(max_length=64)           # Doubao-Seedream-X.X
    prompt           = models.TextField()
    is_img2img       = models.BooleanField(default=False)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_count      = models.IntegerField()                     # 1-4
    completed_count  = models.IntegerField(default=0)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "image_batch"
        ordering = ["-created_at"]
```

**ImageGenerationRequest 新增字段**：

```python
batch    = models.ForeignKey("ImageBatch", on_delete=models.SET_NULL, null=True, blank=True)
model    = models.CharField(max_length=64, blank=True)   # 豆包模型名
provider = models.CharField(max_length=20, blank=True)   # "doubao" 或空（即梦历史数据）
```

**影响**：
- 新增迁移文件（见 module_design.md 第五章）。
- 删除操作：`DELETE /api/v1/image/batches/{id}/` 级联删除路径为：`ImageBatch → ImageGenerationRequest（SET_NULL 改为 CASCADE 子集）→ MediaItem`（通过信号或在 Batch 的 `delete()` override 中处理，见 ADR-07）。

---

### ADR-05：高级参数透传方案

**关联需求**：FR-2（高级可选参数）、OQ-2、AC-01-3、AC-02-2

**背景**：豆包 Seedream 系列三个版本（5.0-lite / 4.5 / 4.0）对高级参数的支持可能有差异，需设计一套在 API 层兼容不同版本的透传方案。

**豆包 Ark `/images/generations` 实际支持的高级参数（基于官方文档）**：

| 参数 | 类型 | 适用模型 | 说明 |
|------|------|---------|------|
| `seed` | integer | 全部 | 随机种子，复现用 |
| `guidance_scale` | float | 全部 | CFG Scale，默认 7.5 |
| `negative_prompt` | string | 全部 | 负向提示词 |
| `steps` | integer | 4.0 / 4.5 | 推理步数；5.0-lite 不支持（忽略） |
| `watermark` | boolean | 全部 | 是否添加水印，默认 false |

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A（已决）| 前端全量传递所有高级参数；后端 `DoubaoImageClient` 按模型版本做参数过滤，仅传入该模型支持的参数 | 前端无需感知模型差异；参数兼容逻辑集中在后端客户端层 | 需维护模型-参数支持矩阵 |
| B | 前端按模型动态渲染参数控件（API 返回参数支持列表） | 前端体验最佳 | 需新增"模型能力查询"接口；实现复杂度高；与 OQ-2（折叠面板）过度设计 |
| C | 不做过滤，全量传入，由 Ark API 自行忽略不支持参数 | 最简单 | Ark API 可能对未知参数返回 400 |

**决策**：选择选项 A — 后端 `DoubaoImageClient` 内维护模型参数支持白名单，按模型过滤后传入。

**模型参数支持矩阵**（定义为常量，独立于业务逻辑）：

```python
# doubao_image_client.py
MODEL_ADVANCED_PARAMS: dict[str, set[str]] = {
    "Doubao-Seedream-5.0-lite": {"seed", "guidance_scale", "negative_prompt", "watermark"},
    "Doubao-Seedream-4.5":      {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
    "Doubao-Seedream-4.0":      {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
}
```

**影响**：
- `DoubaoImageClient.generate_images()` 接收 `advanced_params: dict`，内部执行过滤后组装请求体。
- Serializer 校验：高级参数字段均为 optional，前端不传则不透传。
- 未来新增模型版本只需更新 `MODEL_ADVANCED_PARAMS` 常量（满足 NFR-5）。

---

### ADR-06：API Key 与配额管理方案

**关联需求**：NFR-3、US-07、AC-07-1 至 AC-07-3

**背景**：豆包 Ark API Key 为 Bearer Token，需与现有 `settings_vault` 加密机制集成，并考虑配额耗尽时的处理。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A（已决）| 复用 `UserServiceConfig` 表，新增 `service_type="doubao_image"`；加密 JSON 格式为 `{"api_key": "..."}` | 与现有 `llm_deepseek`/`llm_volcano` 一致；AES-256-GCM 加密已实现 | 单 Key 无法做配额池轮转（本期不需要） |
| B | 新建独立表 `DoubaoApiKey` | 支持多 Key 轮转 | 过度设计；本期需求明确为单用户单 Key |
| C | 系统级全局 Key（环境变量） | 简单 | 无法按用户隔离配额；不符合平台多用户设计 |

**决策**：选择选项 A — 复用 `UserServiceConfig`，新增 `doubao_image` service_type。

**API Key 全生命周期安全约束**：
1. 存储：AES-256-GCM 加密（复用 `core.encryption.encrypt/decrypt`）。
2. 使用：Celery task 中调用 `decrypt(jimeng_cfg.encrypted_config)`（参照现有 tasks.py，字段名改为 `doubao_cfg`）。
3. 日志：`DoubaoImageClient` 的所有日志语句中，API Key 绝不以任何形式出现（Logger filter 在 Django settings 已配置）。
4. 错误响应：`UserServiceConfig.DoesNotExist` 时，返回给前端的错误消息为"请先在设置中配置豆包 Ark API Key"，不暴露内部异常详情。
5. 配额耗尽处理：Ark 返回 HTTP 429 时，任务状态置为 `failed`，`error_message` 写入"豆包 API 配额已耗尽，请检查账户余额"（见 ADR-07）。

**影响**：
- `settings_vault/models.py`：`SERVICE_CHOICES` 追加 `("doubao_image", "豆包图片生成")`。
- `settings_vault` 视图/序列化器：无需新增，现有通用 CRUD 接口已支持任意 `service_type`。

---

### ADR-07：错误处理与重试策略

**关联需求**：NFR-1、NFR-2、FR-2（错误处理）、AC-03-3、US-05（AC-05-5）

**背景**：豆包 Ark 可能返回多种错误，需区分处理策略：可重试 vs 不可重试。

**错误分类与处理矩阵**：

| 错误类型 | Ark HTTP 状态码 / 错误码 | 处理策略 | 用户提示 |
|---------|----------------------|---------|---------|
| 网络超时 / 连接失败 | `httpx.TimeoutException` / `httpx.ConnectError` | 重试 1 次（延迟 5 秒）；仍失败置 `failed` | "网络连接失败，请稍后重试" |
| 服务端 5xx | HTTP 500/502/503 | 重试 1 次；仍失败置 `failed` | "豆包服务暂时不可用，请稍后重试" |
| 内容审核拒绝 | HTTP 400，`error.code` 含 "content_filter" / "sensitive" | 不重试，直接置 `failed` | "提示词包含不允许的内容，请修改后重试" |
| 参数错误 | HTTP 400，非审核原因 | 不重试，置 `failed`，记录完整错误信息 | "请求参数有误，请检查输入" |
| 配额耗尽 | HTTP 429 | 不重试，置 `failed` | "豆包 API 配额已耗尽，请检查账户余额" |
| 认证失败 | HTTP 401 | 不重试，置 `failed` | "豆包 API Key 无效，请重新配置" |
| 生成超时（Ark 侧） | HTTP 408 或响应超时 > 600s | 重试 1 次；仍失败置 `failed` | "图片生成超时（超过10分钟），请重试" |

**重试实现方案**：

```
不使用 Celery 的 self.retry()，原因：
  - Ark 为同步接口，失败后无需延迟重新入队列
  - 采用客户端层内部重试（tenacity 库，指数退避）

DoubaoImageClient.generate_images() 内部重试配置：
  - 仅对可重试错误（网络超时、5xx）启用 1 次重试
  - 重试等待：wait_fixed(5)（5秒后重试）
  - 不可重试错误（4xx 非 429 除外 / 审核拒绝）直接抛出对应异常
```

**批次级联删除的安全约束**（AC-05-5）：

```python
# ImageBatch.delete() override（或在 View 层 pre-check）
if self.status == "processing":
    raise BatchDeletionConflict("批次生成中，无法删除")
# 通过后：级联删除步骤
# 1. 找出所有关联 ImageGenerationRequest
# 2. 找出所有关联 MediaItem，调用 MediaItem.delete()（触发文件清理）
# 3. 删除 ImageGenerationRequest
# 4. 删除 ImageBatch
```

**影响**：
- 新增依赖：`tenacity`（轻量重试库，已在同类项目中使用）。
- `DoubaoImageClient` 使用 `tenacity.retry` 装饰器处理网络层重试。
- 新增自定义异常类：`DoubaoContentFilterError`、`DoubaoQuotaExceededError`、`DoubaoAuthError`。
- `tasks.py` 捕获上述异常，映射为不同的用户提示消息。

---

## 三、与现有即梦调用链路的对比与迁移路径

### 3.1 调用链路对比

**即梦调用链路（改造前）**：

```
前端 POST /api/v1/image/generate/
  → View 创建 ImageGenerationRequest（无批次，无 model 字段）
  → generate_image_task.delay(request_id)
  → Celery Worker:
      → 读取 UserServiceConfig(service_type="jimeng")
      → JimengImageClient.submit_image_task()
          → HMAC-SHA256 签名
          → POST https://visual.volcengineapi.com/?Action=CVProcess
          → 返回 task_id
      → 保存 jimeng_task_id
      → 清理临时参考图
      → for 60次 (每10秒):
          → JimengImageClient.poll_image_status(task_id)
              → POST https://visual.volcengineapi.com/?Action=CVGetResult
          → push "image_progress" (进度百分比)
          → if completed: break
      → create_media_item_from_url(url, source="ai_generated")
          （无 provider 字段）
      → push "image_completed"
```

**豆包调用链路（改造后）**：

```
前端 POST /api/v1/image/generate/
  （新增参数：model, n, size, advanced_params）
  → View 校验（n≤4 硬约束在 Serializer 层）
  → View 创建 ImageBatch（name=时间戳+prompt摘要, total_count=n）
  → View 创建 n 个 ImageGenerationRequest（均关联同一 batch_id, provider="doubao"）
  → generate_image_task.delay(batch_id)
  → Celery Worker:
      → 读取 UserServiceConfig(service_type="doubao_image")
      → DoubaoImageClient.generate_images(
            prompt, model, n, size, is_img2img, ref_image_b64, advanced_params
        )
          → 组装请求体（按 MODEL_ADVANCED_PARAMS 过滤高级参数）
          → POST https://ark.cn-beijing.volces.com/api/v3/images/generations
              Authorization: Bearer <api_key>
          → 同步返回 {"data": [{"url": "..."}, ...]}
      → 清理临时参考图
      → for url in result_urls:
          → create_media_item_from_url(url, source="ai_generated", provider="doubao")
              （media_library.service 需新增 provider 参数，或通过 MediaItem 新字段）
          → 更新对应 ImageGenerationRequest（status=completed, media_item=item）
          → 更新 ImageBatch.completed_count += 1
          → push "image_completed"（含 batch_id）
      → 更新 ImageBatch.status（completed / partial_failed / failed）
      → push "batch_completed"
```

### 3.2 迁移路径（分步实施）

| 步骤 | 操作 | 说明 |
|------|------|------|
| Step 1 | 数据库迁移 | 新增 `image_batch` 表；`image_generation_request` 表新增 `batch_id`, `model`, `provider` 字段；`settings_vault` 新增枚举值；`media_library` 无需改表结构（provider 通过关联查询获得） |
| Step 2 | 新建 `doubao_image_client.py` | 实现 `DoubaoImageClient`，单元测试全覆盖 |
| Step 3 | 改造 `tasks.py` | 替换 Jimeng 客户端调用，适配新批次逻辑；旧即梦轮询循环代码注释掉（不删除，保留 1 个迭代后清理） |
| Step 4 | 改造 `views.py` 和 `serializers.py` | 新增批次创建逻辑，新增批次 CRUD 端点 |
| Step 5 | 前端改造 | 替换模型选择、高级参数折叠面板、批次管理页面 |
| Step 6 | 灰度验证 | 内部测试账号验证全链路；确认历史即梦图片正常展示 |
| Step 7 | 正式上线 | 替换生产环境配置，关闭即梦 API Key 配置入口（前端隐藏） |

---

## 四、数据流图

### 4.1 完整数据流（文生图，n=2）

```
用户操作：填写 prompt，选择 Doubao-Seedream-4.5，生成 2 张
         │
         ▼
[前端] POST /api/v1/image/generate/
  body: {
    prompt: "日落时分的海边灯塔",
    model: "Doubao-Seedream-4.5",
    n: 2,
    size: "1024x1024",
    advanced_params: {seed: 42}
  }
         │
         ▼
[Django View] ImageGenerationSubmitView.post()
  ├── Serializer 校验（n≤4，model 枚举校验）
  ├── ImageBatch.objects.create(
  │     name="0513-1430 日落时分的海边...",
  │     model="Doubao-Seedream-4.5",
  │     prompt="日落时分的海边灯塔",
  │     total_count=2, status="pending"
  │   )
  ├── ImageGenerationRequest.objects.create(..., batch=batch, provider="doubao") × 2
  └── generate_image_task.delay(batch_id=batch.pk)
         │
         ▼ 202 Accepted
  {request_ids: [101, 102], batch_id: 55, batch_name: "0513-1430 日落时分的海边..."}
         │
         ▼ （WebSocket 已建立）
[Celery Worker] generate_image_task(batch_id=55)
  ├── 读取 UserServiceConfig(service_type="doubao_image") → decrypt → api_key
  ├── 更新 ImageBatch.status = "processing"
  ├── push_notification_sync(user_id, "batch_progress", {batch_id: 55, status: "processing"})
  ├── DoubaoImageClient.generate_images(
  │     api_key, model="Doubao-Seedream-4.5",
  │     prompt="日落时分的海边灯塔", n=2,
  │     size="1024x1024", advanced_params={seed:42}
  │   )
  │       ├── 过滤 advanced_params（按 MODEL_ADVANCED_PARAMS["Doubao-Seedream-4.5"]）
  │       ├── POST https://ark.cn-beijing.volces.com/api/v3/images/generations
  │       │     Headers: {Authorization: "Bearer <api_key>"}
  │       │     Body: {model: "...", prompt: "...", n: 2, size: "1024x1024", seed: 42}
  │       └── 返回 {data: [{url: "https://ark.../img1.jpg"}, {url: "https://ark.../img2.jpg"}]}
  ├── 清理临时参考图（文生图时无参考图，跳过）
  ├── for url in [img1.jpg, img2.jpg]:
  │     ├── media_item = create_media_item_from_url(user, url, "image", "ai_generated")
  │     ├── ImageGenerationRequest(batch=batch, 序号=i).update(
  │     │     status="completed", media_item=media_item, provider="doubao"
  │     │   )
  │     ├── ImageBatch.completed_count += 1（原子更新）
  │     └── push_notification_sync(user_id, "image_completed", {
  │               batch_id: 55, request_id: 10x,
  │               media_item_id: media_item.pk,
  │               file_url: media_item.file.url
  │             })
  ├── ImageBatch.status = "completed"（completed_count==total_count）
  └── push_notification_sync(user_id, "batch_completed", {batch_id: 55, status: "completed"})
         │
         ▼ WebSocket 推送到前端
[前端] 收到 "image_completed" × 2 → 页面渲染图片缩略图
[前端] 收到 "batch_completed" → 批次状态更新为"已完成"
```

### 4.2 图生图数据流补充说明

图生图与文生图流程相同，区别在于：
- View 层：接收 `ref_image` 文件，保存为临时路径，传入任务。
- Celery 任务：在调用 `DoubaoImageClient` 前，读取临时文件，base64 编码后赋值给 `image_url` 参数（data URI 格式）。
- 调用后：立即清理临时文件（`os.remove`），无论成功或失败均执行清理（`try/finally`）。

### 4.3 WebSocket 事件 Schema（简版，详见 module_design.md）

| 事件类型 | 触发时机 | 关键字段 |
|---------|---------|---------|
| `batch_progress` | 批次任务开始处理 | `batch_id`, `status` |
| `image_completed` | 单张图片入库完成 | `batch_id`, `request_id`, `media_item_id`, `file_url` |
| `image_failed` | 单张图片生成失败 | `batch_id`, `request_id`, `error` |
| `batch_completed` | 批次全部完成 | `batch_id`, `status` (completed/partial_failed/failed) |

---

*文档版本 v1.0，状态 DRAFT，等待 PM 门控评审。*
