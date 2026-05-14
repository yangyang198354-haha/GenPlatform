# 需求规格说明书：豆包 Seedream 图片生成接入

**文档编号**：REQ-SPEC-IMG-001  
**版本**：v0.2（已决稿）  
**创建日期**：2026-05-13  
**最后更新**：2026-05-13  
**状态**：APPROVED — 所有开放问题已决，可进入架构设计阶段  
**负责人**：需求分析子代理（由 PM 编排）

---

## 一、业务背景与目标

### 1.1 现状

平台当前的 AI 图片生成功能（`apps/image_generator`）依赖即梦（Jimeng）API，调用链路为：

- 接入点：`https://visual.volcengineapi.com`（火山引擎视觉智能平台）
- 协议：CVProcess（提交异步任务）+ CVGetResult（轮询结果）
- 认证：HMAC-SHA256 签名（`core/volcengine_signing.py`）
- 异步执行：Celery worker，每 10 秒轮询，最多 60 次（约 10 分钟）

即梦 API 目前仅支持单一固定模型，无法由用户选择模型版本，且不支持高级生成参数的暴露。

### 1.2 变更动机

豆包 Seedream 系列模型（由火山方舟平台托管）在图像质量、文生图语义理解和图生图一致性方面均有显著提升，且提供 OpenAI 兼容协议，接入成本低。主要变更目标：

1. **完全替换底层图片生成调用**：删除即梦 CVProcess 接入逻辑，唯一使用豆包 Ark `/images/generations` 接口
2. **暴露模型版本选择**：用户可按需选择 Doubao-Seedream-5.0-lite / 4.5 / 4.0
3. **同时支持文生图和图生图**
4. **提供高级生成参数**：通过折叠面板暴露 seed、negative_prompt、guidance_scale 等参数（以豆包接口实际支持为准）
5. **维持并增强素材库集成**：生成图片自动存入 `media_library`
6. **新增批次分组管理**：同一次提交的多张图归为一个批次，支持批次的浏览、重命名和删除

### 1.3 成功标准

- 用户通过界面可选择豆包模型并成功完成文生图、图生图
- 生成的图片自动出现在素材库，且带有批次标签
- 用户可按批次查看历史生成图片
- 旧即梦生成的图片在素材库中保留原样，可正常显示（无批次归属，不出现在批次列表）

---

## 二、功能性需求（FR）

### FR-1 模型选择

| 字段 | 说明 |
|------|------|
| **需求 ID** | FR-1 |
| **需求名称** | 豆包模型版本选择 |
| **来源** | 用户原始需求："可以选择 Doubao-Seedream-5.0-lite、Doubao-Seedream-4.5、Doubao-Seedream-4.0" |
| **描述** | 在提交图片生成请求时，用户必须能够从以下三个模型中选择一个：Doubao-Seedream-5.0-lite（速度优先）、Doubao-Seedream-4.5（均衡）、Doubao-Seedream-4.0（标准）。即梦模型不再作为可选项出现。 |
| **默认值** | `Doubao-Seedream-4.5` |
| **约束** | 模型列表由后端枚举维护，不可由用户自由输入；系统不提供即梦 / 豆包切换开关（OQ-1 决策：完全替换） |

### FR-2 文生图（Text-to-Image）

| 字段 | 说明 |
|------|------|
| **需求 ID** | FR-2 |
| **需求名称** | 文字提示词生成图片 |
| **来源** | 用户原始需求："可以文生图" |
| **描述** | 用户输入提示词（prompt），选择模型和图片尺寸，系统调用豆包 Ark 接口生成图片。用户还可展开"高级选项"折叠面板，调整 seed、negative_prompt、guidance_scale 等参数（OQ-2 决策：折叠面板暴露）。 |
| **必填参数** | `prompt`（提示词，1-500 字符）、`model`（FR-1 枚举值之一） |
| **基础可选参数** | `size`（尺寸，如 `1024x1024`、`1280x720`、`720x1280`；默认 `1024x1024`）；`n`（生成张数，1-4，默认 1，OQ-4 决策） |
| **高级可选参数（折叠面板）** | `seed`（随机种子，整数）、`negative_prompt`（负向提示词）、`guidance_scale`（CFG Scale）、`steps`（生成步数）；以豆包 Ark 接口实际支持的参数为准，架构阶段确认后补全 |
| **结果** | 生成 1 至 4 张图片，异步完成，WebSocket 推送进度 |
| **错误处理** | API 调用失败、超时（10 分钟）、内容审核拒绝时，返回明确错误提示 |

### FR-3 图生图（Image-to-Image）

| 字段 | 说明 |
|------|------|
| **需求 ID** | FR-3 |
| **需求名称** | 参考图 + 提示词生成新图片 |
| **来源** | 用户原始需求："也可以图生图" |
| **描述** | 用户上传一张参考图，配合提示词，系统以参考图风格/内容为基础生成新图片。高级参数同 FR-2（折叠面板暴露）。 |
| **参考图格式** | JPEG / PNG，大小 ≤ 10 MB（与现有即梦客户端保持一致） |
| **参考图传输** | base64 编码后作为 `image_url` 参数提交给豆包 Ark 接口（data URI 格式） |
| **必填参数** | `ref_image`（文件）、`prompt`、`model` |
| **可选参数** | 同 FR-2 |
| **结果** | 同 FR-2 |

### FR-4 生成图片自动入素材库

| 字段 | 说明 |
|------|------|
| **需求 ID** | FR-4 |
| **需求名称** | AI 生成图片自动存入 media_library |
| **来源** | 用户原始需求："生成的图片自动存放在素材库中" |
| **描述** | Celery 任务在获得图片 URL 后，调用 `media_library.service.create_media_item_from_url`，将图片下载并存入 `MediaItem`，`source` 字段标记为 `ai_generated`，`provider` 字段标记为 `doubao` |
| **关联** | 每张生成图片均关联到当次提交的批次记录（FR-5） |
| **无需用户操作** | 入库完全自动，用户无需手动保存 |

### FR-5 批次分组管理

| 字段 | 说明 |
|------|------|
| **需求 ID** | FR-5 |
| **需求名称** | 同批次图片分组、批次管理 |
| **来源** | 用户原始需求："不同批次生成的图片可以分组管理" |
| **描述** | 每次用户提交图片生成请求（无论一次生成几张）均创建一条 `ImageBatch` 记录；同一次生成的所有图片均关联到该批次；用户可按批次浏览、重命名、删除图片组 |
| **批次默认命名规则** | 时间戳 + prompt 摘要组合（OQ-3 决策）：格式为 `MMDD-HHmm <prompt前N字>...`，例如 `0513-1430 日落时分的海边...`；具体 N 值由架构/开发阶段确定（建议 10-15 字） |
| **生成张数范围** | 每批次 1 至 4 张（OQ-4 决策）；默认 1 张；超过 4 张的请求后端拒绝 |
| **批次字段** | 见第四章数据需求 |
| **批次操作** | 列表查看、重命名（修改 `name` 字段）、删除（级联删除批次内所有图片及 MediaItem） |

---

## 三、非功能性需求（NFR）

### NFR-1 性能

- **接口响应延迟**：提交接口（POST）在 500ms 内返回受理确认
- **生成超时上限**：单张图片生成时间上限 10 分钟（保持与即梦现有策略一致）
- **轮询间隔**：Celery worker 轮询间隔 ≥ 5 秒（避免过频请求豆包 API）
- **单批次并发上限**：单次提交最多 4 张（OQ-4 决策），由 Celery 并行或串行执行，具体方式在架构阶段确定

### NFR-2 可用性

- 豆包 Ark API 不可达时，任务状态置为 `failed`，用户收到明确错误提示，系统不崩溃
- WebSocket 断线时，前端降级为轮询状态接口（`GET /api/v1/image/generate/{pk}/status/`）
- 历史即梦图片（`provider` 为空或 `jimeng`）在素材库中保留原样，不受本次迁移影响（OQ-5 决策）

### NFR-3 安全性（API Key 管理）

- 豆包 Ark API Key 以 AES-256-GCM 加密存储（复用现有 `settings_vault` 机制）
- `service_type` 新增枚举值 `doubao_image`，与现有 `llm_volcano` 区分
- API Key 不得出现在日志、错误响应或任何明文字段中
- 参考图片以 base64 编码提交后，临时文件在任务结束后立即清理（复用现有逻辑）

### NFR-4 可观测性

- Celery 任务日志：记录模型版本、批次 ID、任务 ID、耗时、成功/失败原因
- Django 请求日志：记录提交用户、模型选择、是否为图生图、生成张数
- 生产告警：任务连续失败率 > 20%（1 小时窗口）时触发告警（具体配置在 DevOps 阶段处理）

### NFR-5 可扩展性

- 模型枚举表独立维护，未来新增豆包模型版本只需修改枚举，不改动核心逻辑
- 图片生成客户端抽象为接口（`BaseImageClient`），豆包客户端实现该接口，为未来再次切换做准备

---

## 四、数据需求

### 4.1 新增数据模型：ImageBatch（图片批次）

```
表名：image_batch

字段：
  id              INTEGER      主键，自增
  user            FK(User)     所属用户，级联删除
  name            VARCHAR(255) 批次显示名称（默认值 = 时间戳 + prompt 摘要；可重命名）
  model           VARCHAR(64)  使用的豆包模型（如 Doubao-Seedream-4.5）
  prompt          TEXT         本批次使用的提示词
  is_img2img      BOOLEAN      是否为图生图请求
  status          VARCHAR(20)  批次整体状态：pending / processing / completed / partial_failed / failed
  total_count     INTEGER      本批次预计生成图片数（1-4）
  completed_count INTEGER      已完成图片数（默认 0）
  created_at      DATETIME     创建时间（自动）
  updated_at      DATETIME     最后更新时间（自动）
```

### 4.2 修改现有模型：ImageGenerationRequest

在 `ImageGenerationRequest` 中新增字段：

```
新增字段：
  batch           FK(ImageBatch, null=True)  所属批次，SET_NULL（历史数据为 null）
  model           VARCHAR(64)                本次请求使用的豆包模型
  provider        VARCHAR(20)                生成来源：doubao（新数据固定写入）；历史即梦数据此字段为 null
```

> **说明（OQ-1 决策）**：`jimeng_task_id` 等即梦专有字段保留在数据库中（历史数据兼容），但新数据不再写入。即梦接入逻辑（`jimeng_image_client.py`）停用，不再被调用。

> **说明（OQ-5 决策）**：历史 `ImageGenerationRequest` 记录的 `provider` 字段为空（null），不执行迁移脚本补标，不关联任何 `ImageBatch`。

### 4.3 settings_vault 变更

`UserServiceConfig.service_type` 新增枚举值：

```
doubao_image    —  豆包图片生成（Ark Bearer Token）
```

加密配置结构（JSON）：

```json
{
  "api_key": "<Ark API Key>"
}
```

---

## 五、系统边界与约束

### 5.1 接口对接说明

豆包 Ark 图片生成接口特征（供架构阶段参考，本阶段仅作约束描述）：

- **端点**：`https://ark.cn-beijing.volces.com/api/v3/images/generations`
- **协议**：HTTP POST，OpenAI 兼容
- **认证**：`Authorization: Bearer <ARK_API_KEY>`
- **响应**：同步返回图片 URL（与即梦异步轮询模式不同，Celery 任务流程需评估改造幅度）

### 5.2 与现有系统的边界

| 组件 | 处理策略 |
|------|---------|
| `jimeng_image_client.py` | 停用（OQ-1 决策：完全替换）；文件可保留但不再被任何代码路径调用 |
| `core/volcengine_signing.py` | 豆包 Ark 使用 Bearer Token，不需要 HMAC 签名；该模块为视频生成保留，不删除 |
| `media_library.service` | 直接复用，无需修改 |
| `notifications.service` | 直接复用，无需修改 |
| 前端图片生成页面 | 需新增模型选择下拉框、生成张数选择（1-4）、高级参数折叠面板、批次管理 Tab/页面 |

### 5.3 边界与约束（已决）

| 约束项 | 决策来源 | 具体约束 |
|-------|---------|---------|
| 即梦代码策略 | OQ-1（方案 A） | 完全替换，不提供双模切换，前端无即梦入口 |
| 高级参数暴露 | OQ-2（方案 B） | 折叠面板暴露，默认收起；具体参数以豆包 Ark 接口实际支持为准 |
| 批次命名规则 | OQ-3（方案 C） | 时间戳 + prompt 摘要组合；用户可重命名 |
| 单批次最大张数 | OQ-4（4 张） | 前端限制 1-4 张；后端对超出请求返回 400 |
| 旧即梦数据 | OQ-5（方案 A） | 历史数据保留原样，不迁移，不关联批次；新数据打 `provider=doubao` |

### 5.4 不在本期范围内

- 视频生成（`video_generator`）不受影响，不在本次迁移范围
- 知识库（`knowledge_base`）不受影响
- 历史即梦图片的批量迁移或补标（已决：保留原样）
- 即梦与豆包的双模并存切换开关（已决：不保留）

---

## 六、假设与依赖

1. 豆包 Ark `/images/generations` 为同步接口（一次 HTTP 请求即返回结果 URL），与即梦异步轮询不同；若实际接口行为不同，Celery 任务流程需在架构阶段调整。
2. 用户已持有有效的火山方舟（Ark）API Key，并可通过 settings_vault 配置。
3. 前端框架（Vue 3 + Element Plus）已有图片生成页面骨架，改造仅需新增组件，不重写页面。
4. 豆包 Ark 接口对单次 `/images/generations` 请求支持 `n` 参数（一次返回多张），上限需在架构阶段确认；若不支持，则由 Celery 并行/串行多次调用。

---

*本文档已基于 OQ-1 至 OQ-5 的用户决策（2026-05-13）更新至 v0.2，状态为 APPROVED。*  
*所有"取决于 OQ-x"的悬而未决措辞均已消除，架构设计阶段可直接以本文档为输入。*
