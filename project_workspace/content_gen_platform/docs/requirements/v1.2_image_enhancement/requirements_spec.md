# 需求规格说明书 v1.2 — AI 图片功能增强

**file_header**
- document_id: REQ-SPEC-v1.2
- author_agent: sub_agent_requirement_analyst
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2 AI 图片功能 4 项调整
- status: DRAFT
- created_at: 2026-05-14
- source: 用户原始业务需求（PARTIAL_FLOW）

---

## 1. 背景与目标

GenPlatform 内容生成平台当前已集成豆包 Seedream 3 个模型（PR #4/#5/#6/#7），支持文生图和图生图基础功能。本次 v1.2 迭代目标：

1. 按火山方舟官方 PDF 规格，完整覆盖豆包图片生成 API 所有可配置参数
2. 优化 AI 图片页面 UI 布局，容纳新增参数控件
3. 新增素材库（KB）图片放大预览功能
4. 清理已废弃的即梦 API 相关 UI 与后端代码

---

## 2. 火山方舟图片生成 API 参数完整规格

> 数据来源：火山方舟_图片生成 API_1778490637.pdf（OpenAI 兼容接口）
>
> 接口端点：`POST https://ark.cn-beijing.volces.com/api/v3/images/generations`
> 认证方式：Bearer Token（`Authorization: Bearer <api_key>`）

### 2.1 请求参数全表（真值来源）

| 参数名 | 类型 | 必填 | 默认值 | 取值范围 / 说明 |
|--------|------|------|--------|----------------|
| `model` | string | 是 | — | 模型 ID，见 §2.2 支持模型表 |
| `prompt` | string | 是 | — | 正向提示词，1–2000 字符（Ark 侧限制；平台层收紧至 500 字符以控制成本） |
| `n` | integer | 否 | 1 | 每次生成图片张数；取值 1–4（平台层硬限 ≤ 4，与现有约束一致） |
| `size` | string | 否 | "2048x2048" | 像素精确尺寸，格式 `{width}x{height}`；支持的枚举值见 §2.3 |
| `response_format` | string | 否 | "url" | 返回格式：`"url"`（返回 CDN URL）或 `"b64_json"`（返回 base64）；平台固定使用 `"url"` |
| `seed` | integer | 否 | null（随机） | 随机种子，0–2147483647；相同 seed + prompt + 其他参数可复现结果 |
| `guidance_scale` | float | 否 | 7.5 | CFG 引导强度，范围 1.0–20.0；越高越贴近提示词，越低越有创意 |
| `negative_prompt` | string | 否 | "" | 负向提示词，最大 500 字符；描述不希望出现的内容 |
| `steps` | integer | 否 | 模型默认 | 推理去噪步数，范围 10–100；**仅 Seedream 4.0 / 4.5 支持**，5.0 Lite 不支持 |
| `watermark` | boolean | 否 | false | 是否在生成图片上添加"豆包"水印 |
| `image_url` | string | 否 | null | 图生图参考图，data URI 格式（`data:image/jpeg;base64,...`）；传入则触发图生图模式 |

> **注意**：`response_format` 平台层固定为 `"url"`，不向用户开放配置。`image_url` 由后端 Task 层处理，前端仍通过文件上传接口传参。

### 2.2 支持模型表（model ID 含日期后缀，与 PR #6 一致）

| 模型名称 | model ID | 特性说明 |
|----------|----------|---------|
| Seedream 5.0 Lite | `doubao-seedream-5-0-260128` | 最新轻量版；不支持 `steps` 参数 |
| Seedream 4.5 | `doubao-seedream-4-5-251128` | 标准版；支持 `steps`；默认模型 |
| Seedream 4.0 | `doubao-seedream-4-0-250828` | 旧版本兼容；支持 `steps` |

> 历史告警（Ark model ID 格式约束，memory 记录）：model ID **必须**使用含日期后缀的完整格式；开发期必须真调一次生图端点验证可用性。

### 2.3 图片尺寸规格（三种输入方式归一化为 `size` 参数）

#### 方式 A：像素精确指定（直接传入）

| 尺寸字符串 | 宽 × 高 | 比例 | 像素数 |
|-----------|---------|------|-------|
| `2048x2048` | 2048 × 2048 | 1:1 | 4.2 MP |
| `2880x1620` | 2880 × 1620 | 16:9 | 4.7 MP |
| `1620x2880` | 1620 × 2880 | 9:16 | 4.7 MP |
| `2160x2880` | 2160 × 2880 | 3:4 | 6.2 MP |
| `2880x2160` | 2880 × 2160 | 4:3 | 6.2 MP |
| `3072x3072` | 3072 × 3072 | 1:1 | 9.4 MP（3K） |
| `4096x4096` | 4096 × 4096 | 1:1 | 16.8 MP（4K） |
| `4096x2304` | 4096 × 2304 | 16:9（4K） | 9.4 MP |
| `2304x4096` | 2304 × 4096 | 9:16（4K） | 9.4 MP |

> 最低像素要求：Seedream 4+ 最小 3MP（PR #7 历史修复已确认默认值 2048×2048 = 4.2MP 合规）。

#### 方式 B：档位指定（映射到像素字符串）

| 档位 | 默认映射 | 说明 |
|------|---------|------|
| 2K（默认） | `2048x2048` | 4.2 MP，1:1 方图基准 |
| 3K | `3072x3072` | 9.4 MP |
| 4K | `4096x4096` | 16.8 MP |

#### 方式 C：比例 × 档位组合指定（映射到像素字符串）

`size_mode=ratio` 时，必须配合 `size_tier`（默认 2K）共同决定最终像素。完整 15 个组合映射表：

| 比例 \ 档位 | 2K（默认） | 3K | 4K |
|-----------|---------|-----|-----|
| 1:1 | `2048x2048`（4.2MP） | `3072x3072`（9.4MP） | `4096x4096`（16.8MP） |
| 16:9 | `2880x1620`（4.7MP） | `3840x2160`（8.3MP） | `4096x2304`（9.4MP） |
| 9:16 | `1620x2880`（4.7MP） | `2160x3840`（8.3MP） | `2304x4096`（9.4MP） |
| 4:3 | `2880x2160`（6.2MP） | `3072x2304`（7.1MP） | `4096x3072`（12.6MP） |
| 3:4 | `2160x2880`（6.2MP） | `2304x3072`（7.1MP） | `3072x4096`（12.6MP） |

> 所有组合均满足 Ark Seedream 4+ 最小 3MP 约束（PR #7 教训）。已用户确认参数集完整，无需对照 PDF 额外核实比例枚举。
>
> 三种方式在后端 Serializer 层归一化为统一的 `size` 字符串（如 `"2048x2048"`），向 Ark API 传递。

### 2.4 图片格式（image format 参数）

Ark API 的 `response_format` 参数：

| 值 | 含义 | 平台策略 |
|----|------|---------|
| `url` | 返回 CDN 链接（有效期约 24h） | 固定使用（平台下载后入库，避免链接失效） |
| `b64_json` | 返回 base64 编码的图片数据 | 不开放（带宽开销大） |

---

## 3. 功能需求

### FR-1：豆包图片生成 API 参数完整支持

**来源**：用户需求 1（§2 参数表）

- **FR-1.1**：后端 Serializer 层支持 §2.1 全量参数（model / prompt / n / size / seed / guidance_scale / negative_prompt / steps / watermark），并实施 steps 仅 4.0/4.5 模型白名单过滤
- **FR-1.2**：size 参数支持三种输入方式（像素精确 / 档位 / 比例×档位组合），在 Serializer/Service 层归一化为 `{w}x{h}` 字符串传给 Ark；`ratio` 模式必须配合 `size_tier` 参数（默认 2K），完整 15 个组合见 §2.3 方式 C 映射表
- **FR-1.3**：MODEL_ADVANCED_PARAMS 白名单按 §2.2 模型特性更新，确保 5.0 Lite 不传 steps
- **FR-1.4**：组图生成：用户在 UI 可切换"主图模式"（n=1）和"多图模式"（n=2/3/4）
- **FR-1.5**：所有参数均有合理默认值，不传时后端自动填充（见 §4 默认值表）
- **FR-1.6**：开发期必须真调一次各模型的生图端点验证 model ID 可用性

### FR-2：AI 图片页面 UI 布局优化

**来源**：用户需求 2

- **FR-2.1**："生成设置"左侧面板宽度从 380px 扩展至 ≥ 460px，容纳新增参数控件
- **FR-2.2**：新增"尺寸设置"区块，以分段控件实现三种尺寸输入方式切换（Tab 或 RadioButton）
- **FR-2.3**："高级选项"折叠面板新增 guidance_scale（滑块）、steps（数字输入，条件显示）
- **FR-2.4**：新增"生成模式"切换控件（主图 n=1 / 多图 n=2/3/4 切换）
- **FR-2.5**：响应式布局：≤ 1100px 视口时折叠为单列；≤ 900px 时使用抽屉式侧边栏

### FR-3：素材库图片放大预览（Lightbox）

**来源**：用户需求 3

- **FR-3.1**：**MediaLibraryView**（`/media-library`）中，图片条目支持点击放大查看；知识库（KnowledgeBaseView）不需要图片预览功能
- **FR-3.2**：Lightbox 功能：显示原图 / 支持键盘 Esc 关闭 / 支持点击蒙层关闭 / 支持左右箭头切换
- **FR-3.3**：现有"删除"和"下载"操作并存，不受影响
- **FR-3.4**：仅对媒体类型为图片的条目显示预览入口（文档类型不显示）

### FR-4：清理即梦 API 残留

**来源**：用户需求 4

- **FR-4.1**：前端 SettingsView 删除"即梦 API"Tab pane（`name="jimeng"` 的 `el-tab-pane`）
- **FR-4.2**：删除 SettingsView 中 jimengForm / savingJimeng / testingJimeng / saveJimengConfig / testJimengConfig 相关变量与函数
- **FR-4.3**：后端评估是否有即梦相关路由/序列化器/视图残留，有则一并清理
- **FR-4.4**：`UserServiceConfig.SERVICE_CHOICES` 中保留 `"jimeng"` 枚举值以兼容历史数据，但不再开放新配置入口
- **FR-4.5**：`video_generator/jimeng_client.py` 的视频生成功能不在本次范围内（仅清理图片相关即梦配置 UI）

---

## 4. 参数默认值表（后端推荐默认）

| 参数 | 默认值 | 来源 |
|------|--------|------|
| model | `doubao-seedream-4-5-251128` | PR #6 既有逻辑 |
| n | 1 | 现有逻辑 |
| size | `2048x2048` | PR #7 修复后 |
| seed | null（每次随机） | Ark 默认 |
| guidance_scale | 7.5 | Ark 推荐 |
| negative_prompt | `""` | 无负向 |
| steps | null（模型默认，Seedream 4.x 约 25 步） | Ark 默认 |
| watermark | false | Ark 默认 |
| response_format | `"url"`（固定） | 平台策略 |

---

## 5. 非功能需求

| ID | 描述 |
|----|------|
| NFR-1 | POST /api/v1/image/generate/ 在 500ms 内返回 202（现有约束，保持不变） |
| NFR-2 | 新增参数不改变现有 Celery Task 签名，通过 advanced_params dict 扩展传递 |
| NFR-3 | API Key 禁止出现在任何日志或响应体中（现有约束，保持不变） |
| NFR-4 | 所有新增后端逻辑必须有 unit 测试（pytest mock）覆盖，覆盖率不低于现有水平 |
| NFR-5 | 即梦 API 清理不影响历史数据（jimeng 类型的 UserServiceConfig 记录仍保留） |
| NFR-6 | Lightbox 不引入重量级第三方库（使用 Element Plus 内置 el-image 或轻量 pure CSS） |

---

## 6. 约束与假设

1. **Ark model ID**：三个 Seedream model ID 已在 PR #6 硬编码（`doubao-seedream-5-0-260128` / `doubao-seedream-4-5-251128` / `doubao-seedream-4-0-250828`），Ark 发新版会失效，开发期必须真调验证
2. **参数集完整性**：§2.1 的 11 个参数已经用户确认完整，无遗漏参数，无需对照 PDF 额外核实
3. **即梦视频功能**：`apps/video_generator/jimeng_client.py` 的视频功能不纳入清理范围
4. **素材库页面**：Lightbox 预览目标为 **MediaLibraryView**（`/media-library`）；KnowledgeBaseView 不需要图片预览功能
5. **测试门控**：pre-commit hook 强制 `pytest apps/ tests/ -m "not integration"`，所有新增代码须配套 unit 测试

---

## 7. 范围边界（Out of Scope）

- 新增 Seedream 模型版本（Ark 未发布）
- 视频生成功能改造
- 后端存储策略变更
- 多租户/权限模型变更
