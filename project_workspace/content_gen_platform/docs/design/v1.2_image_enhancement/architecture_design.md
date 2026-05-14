# 架构设计文档 v1.2 — AI 图片功能增强

**file_header**
- document_id: ARCH-v1.2
- author_agent: sub_agent_system_architect
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2 AI 图片功能 4 项调整
- status: DRAFT
- created_at: 2026-05-14
- input_refs: requirements_spec.md v1.2, user_stories.md v1.2

---

## 1. 架构决策总览

本次 v1.2 是在已稳定的豆包 Seedream 集成（PR #4–#7）基础上的增量改造，架构不重构，仅在现有分层上扩展。核心改动集中在：

1. **参数层扩展**：Serializer 新增尺寸三模式归一化逻辑；Task 通过 `advanced_params` dict 传递
2. **豆包 API 调用层**：`DoubaoImageClient._build_request_body()` 保持不变（已支持完整参数），仅更新 `MODEL_ADVANCED_PARAMS` 白名单
3. **前端参数面板重构**：AdvancedParamsPanel + 新增 SizeSelector 组件
4. **素材库 Lightbox**：纯前端增量组件，无后端变更
5. **即梦 API 清理**：前端 SettingsView 删除 Tab；后端评估残留

---

## 2. 系统分层架构（现有，v1.2 变更标注）

```
┌─────────────────────────────────────────────────────┐
│                    前端 Vue 3                         │
│  ┌─────────────────┐  ┌────────────────────────┐   │
│  │ ImageGeneratorView│  │ MediaLibraryView        │   │
│  │  ┌─────────────┐ │  │  (/media-library)       │   │
│  │  │SizeSelector  │ │  │  ┌──────────────────┐  │   │
│  │  │[NEW v1.2]    │ │  │  │ el-image preview  │  │   │  ← v1.2 新增
│  │  └─────────────┘ │  │  │ [Lightbox 增强]   │  │   │
│  │  AdvancedParams  │  │  └──────────────────┘  │   │
│  │  Panel [增强]    │  └────────────────────────┘   │
│  └─────────────────┘                                 │
│  ┌─────────────────────────────────────────────┐     │
│  │  SettingsView [移除即梦 Tab]                  │     │  ← v1.2 清理
│  └─────────────────────────────────────────────┘     │
└───────────────────┬─────────────────────────────────┘
                    │ HTTP REST (Axios)
┌───────────────────▼─────────────────────────────────┐
│              Django REST Framework                    │
│  ┌────────────────────────────────────────────────┐  │
│  │  ImageGenerationSubmitView                      │  │
│  │    → ImageGenerationSubmitSerializer [扩展]     │  │  ← v1.2 扩展
│  │      ├─ SizeInputValidator（归一化三模式）       │  │  ← v1.2 新增
│  │      └─ StepsModeGuard（白名单过滤）            │  │
│  └────────────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────────┘
                    │ Celery Task
┌───────────────────▼─────────────────────────────────┐
│  generate_image_task(batch_id, advanced_params, size) │
│    → DoubaoImageClient.generate_images()             │
│      → _build_request_body()（无变更，已支持全参数）  │
│      → MODEL_ADVANCED_PARAMS[model]（更新白名单）     │  ← v1.2 更新
└───────────────────┬─────────────────────────────────┘
                    │ HTTPS
┌───────────────────▼─────────────────────────────────┐
│  火山方舟 Ark API                                      │
│  POST /api/v3/images/generations                     │
└─────────────────────────────────────────────────────┘
```

---

## 3. 核心架构决策（ADR）

### ADR-v1.2-01：尺寸三模式归一化位置

**问题**：三种尺寸输入方式（像素精确 / 档位 / 比例）应在哪一层归一化？

**方案对比**：

| 方案 | 归一化位置 | 优点 | 缺点 |
|------|-----------|------|------|
| A（本决策） | 后端 Serializer | 前端不需要知道映射表；API 防御性强；前端改动最小 | Serializer 稍复杂 |
| B | 前端 composable | 逻辑更靠近用户；Serializer 简单 | 前端与后端映射表可能不一致；API 直调绕过归一化 |
| C | Service 层（Task） | 与 Serializer 解耦 | Task 承担过多业务逻辑；测试困难 |

**决策：方案 A（后端 Serializer 层）**

理由：
1. Ark API 的 size 参数是字符串枚举（§2.3），Serializer 是校验/归一化的天然位置
2. 前端直接传 `size_mode`（enum: `"pixel"|"tier"|"ratio"`）和对应值，Serializer 输出统一的 `"WxH"` 字符串
3. API 直调也能正确处理，防御性更强

**实现接口**：
```
POST /api/v1/image/generate/
请求体扩展：
  size_mode: "pixel" | "tier" | "ratio"  （默认 "pixel"）
  size: "2048x2048"                        （pixel 模式直接用）
  size_tier: "2K" | "3K" | "4K"           （tier 模式用）
  size_ratio: "1:1" | "16:9" | "9:16" | "4:3" | "3:4"  （ratio 模式用）

Serializer.validate() 后输出统一字段：
  validated_data["size"] = "2048x2048"   （归一化后的像素字符串）
```

---

### ADR-v1.2-02：steps 参数白名单策略

**问题**：5.0 Lite 不支持 steps，如何防止误传？

**决策**：维持现有 `MODEL_ADVANCED_PARAMS` 白名单机制（`DoubaoImageClient._build_request_body()`），在 `5.0-260128` 的 set 中不包含 `steps`。Serializer 层不做过滤（允许用户传入，但 task 层过滤），同时前端条件隐藏该控件（双重保护）。

理由：Serializer 层过滤会给 API 调用方提示 400，而该参数对于高版本模型是合法的；task 层的白名单是最终防线，职责更清晰。

---

### ADR-v1.2-03：Lightbox 组件选型

**问题**：素材库图片预览用什么组件实现？

**方案对比**：

| 方案 | 实现方式 | bundle 增量 | 交互完整性 |
|------|---------|------------|-----------|
| A（本决策） | Element Plus `el-image` 的 preview 属性 | 0 KB（已引入） | 支持多图切换、Esc 关闭、缩放 |
| B | vue-viewer / viewerjs | ~40 KB | 功能最全 |
| C | 自定义 dialog + `<img>` | 0 KB | 需手动实现 Esc/蒙层 |

**决策：方案 A（Element Plus `el-image` preview 属性）**

理由：
1. Element Plus 已在项目中引入，无额外依赖（NFR-6）
2. `el-image` 的 `preview-src-list` 属性天然支持多图切换、Esc 关闭、缩放、点击蒙层关闭
3. 改造量最小：仅需在 **MediaLibraryView**（`/media-library`）的图片条目列渲染中使用 `el-image` 替代 `<img>`，并传入 `preview-src-list`；KnowledgeBaseView 不做 Lightbox 改造

---

### ADR-v1.2-04：即梦 API 清理范围边界

**问题**：后端 `jimeng_client.py` 是否一并清理？

**决策**：本次仅清理前端 SettingsView 的即梦图片 API 配置 Tab；后端 `video_generator/jimeng_client.py`（视频功能）保留。`UserServiceConfig.SERVICE_CHOICES` 中的 `jimeng` 枚举值保留，以兼容历史数据。

范围确认：
- 删除：SettingsView 中 jimeng Tab + 相关 JS 逻辑（4 个函数 + 1 个 ref）
- 保留：`video_generator/jimeng_client.py`；`jimeng` service_type 枚举；历史 DB 记录

---

## 4. 数据流：尺寸归一化

```
用户选择尺寸方式
        │
        ▼
前端 SizeSelector
  size_mode = "tier"
  size_tier = "3K"
        │ POST FormData
        ▼
ImageGenerationSubmitSerializer.validate()
  size_mode = "tier"
  size_tier = "3K"
        │ 调用 SizeNormalizer.normalize()
        ▼
  validated_data["size"] = "3072x3072"
        │
        ▼
generate_image_task.delay(batch_id, advanced_params={...}, size="3072x3072")
        │
        ▼
DoubaoImageClient.generate_images(size="3072x3072")
        │
        ▼
Ark API body: { "size": "3072x3072", ... }
```

---

## 5. 数据流：高级参数传递（含 steps 白名单过滤）

```
前端 AdvancedParamsPanel
  { seed: 123, steps: 50, guidance_scale: 8.0 }
        │ POST FormData
        ▼
ImageGenerationSubmitSerializer
  validated_data: { seed: 123, steps: 50, guidance_scale: 8.0 }
  serializer.get_advanced_params() → { seed: 123, steps: 50, guidance_scale: 8.0 }
        │
        ▼
generate_image_task(advanced_params={ seed: 123, steps: 50, guidance_scale: 8.0 })
        │
        ▼
DoubaoImageClient._build_request_body(model="doubao-seedream-5-0-260128", advanced_params=...)
  MODEL_ADVANCED_PARAMS["doubao-seedream-5-0-260128"] = {"seed", "guidance_scale", "watermark"}
        │ steps 不在白名单，过滤掉
        ▼
Ark body: { "model": "...", "prompt": "...", "seed": 123, "guidance_scale": 8.0 }
  (steps 已过滤)
```

---

## 6. 前端组件树变更（v1.2 diff）

```
ImageGeneratorView.vue（已有）
  ├── PreflightBanner.vue（已有，不变）
  ├── ModelSelector.vue（已有，不变）
  ├── SizeSelector.vue（新增 v1.2）← ADR-v1.2-01
  │     ├── Tab: 精确像素 → el-select（枚举下拉）
  │     ├── Tab: 档位    → el-radio-group（2K/3K/4K）
  │     └── Tab: 比例    → el-radio-group（1:1/16:9/9:16/4:3/3:4）
  ├── GenerationModeSelector.vue（新增 v1.2）← FR-2.4
  │     └── el-radio-button: 主图(n=1) | 多图(n=2/3/4)
  ├── AdvancedParamsPanel.vue（扩展 v1.2）
  │     ├── seed（已有）
  │     ├── negative_prompt（已有）
  │     ├── guidance_scale（已有，优化滑块范围 1.0–20.0）
  │     ├── steps（已有，条件显示）
  │     └── watermark（已有）
  └── BatchCountSelector.vue（已有，不变）

MediaLibraryView.vue（已有，`/media-library`）
  └── 图片列改用 el-image preview-src-list（扩展，不新增组件）← ADR-v1.2-03
  注：KnowledgeBaseView 不做 Lightbox 改造（用户已确认知识库不需要图片预览）

SettingsView.vue（已有，精简 v1.2）← ADR-v1.2-04
  └── 移除 el-tab-pane name="jimeng" 及相关 JS
```

---

## 7. 后端模块变更（v1.2 diff）

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `image_generator/serializers.py` | 扩展 | 新增 SizeNormalizer 逻辑，新增 size_mode/size_tier/size_ratio 字段 |
| `image_generator/doubao_image_client.py` | 微调 | MODEL_ADVANCED_PARAMS 无需改动（白名单已是正确结构）；如 PDF 有新参数则更新 |
| `image_generator/tasks.py` | 不变 | size 参数路径不变 |
| `image_generator/views.py` | 不变 | 转发 serializer 结果即可 |
| `image_generator/models.py` | 不变 | 不新增 DB 字段 |
| `settings_vault/models.py` | 不变 | jimeng 枚举保留 |
| 前端 `SettingsView.vue` | 删减 | 删除 jimeng Tab + 相关 JS |
| 前端 `ImageGeneratorView.vue` | 扩展 | 引入 SizeSelector + GenerationModeSelector |
| 前端 `MediaLibraryView.vue` | 扩展 | 图片 preview 改用 el-image（`/media-library`，KnowledgeBaseView 不动） |

---

## 8. 安全与合规

- API Key 不在任何日志/响应体中记录（NFR-3，不变）
- size 归一化在 Serializer 层，非法 size 返回 400（防御注入非法字符）
- Lightbox 不引入额外 CSP 绕过风险（el-image 是受控组件）
- 即梦 API 清理后，历史 UserServiceConfig 记录仍安全保留，不泄露

---

## 9. 需求覆盖矩阵

| 需求 ID | 架构组件 | ADR 引用 |
|---------|---------|---------|
| FR-1.1 | Serializer + DoubaoImageClient | ADR-v1.2-01 |
| FR-1.2 | Serializer SizeNormalizer | ADR-v1.2-01 |
| FR-1.3 | MODEL_ADVANCED_PARAMS 白名单 | ADR-v1.2-02 |
| FR-1.4 | GenerationModeSelector.vue | — |
| FR-2.1–2.4 | ImageGeneratorView 布局 + SizeSelector | — |
| FR-3.1–3.4 | MediaLibraryView + el-image preview | ADR-v1.2-03 |
| FR-4.1–4.4 | SettingsView 精简 | ADR-v1.2-04 |
