# 模块设计文档 v1.2 — AI 图片功能增强

**file_header**
- document_id: MOD-v1.2
- author_agent: sub_agent_system_architect
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2 AI 图片功能 4 项调整
- status: DRAFT
- created_at: 2026-05-14
- input_refs: architecture_design.md v1.2, requirements_spec.md v1.2

---

## 1. 后端模块详细设计

### 1.1 SizeNormalizer（新增，位于 serializers.py）

**职责**：将三种尺寸输入方式（pixel / tier / ratio×tier 组合）归一化为 Ark API 的 `size` 字符串，保证输出不低于 3MP。

**接口设计**：

```python
# image_generator/size_normalizer.py

# 档位映射（单独用于 tier 模式）
TIER_MAP: dict[str, str] = {
    "2K": "2048x2048",
    "3K": "3072x3072",
    "4K": "4096x4096",
}

# 比例 × 档位组合映射表（ratio 模式必须配合 size_tier）
# 格式：RATIO_TIER_MAP[ratio][tier] → "{w}x{h}"
RATIO_TIER_MAP: dict[str, dict[str, str]] = {
    "1:1": {
        "2K": "2048x2048",
        "3K": "3072x3072",
        "4K": "4096x4096",
    },
    "16:9": {
        "2K": "2880x1620",
        "3K": "3840x2160",
        "4K": "4096x2304",
    },
    "9:16": {
        "2K": "1620x2880",
        "3K": "2160x3840",
        "4K": "2304x4096",
    },
    "4:3": {
        "2K": "2880x2160",
        "3K": "3072x2304",
        "4K": "4096x3072",
    },
    "3:4": {
        "2K": "2160x2880",
        "3K": "2304x3072",
        "4K": "3072x4096",
    },
}

# 像素精确档枚举白名单（防止任意字符串注入 Ark）
PIXEL_VALID_SIZES: set[str] = {
    "2048x2048", "2880x1620", "1620x2880",
    "2160x2880", "2880x2160",
    "3072x3072", "3840x2160", "2160x3840",
    "3072x2304", "2304x3072",
    "4096x4096", "4096x2304", "2304x4096",
    "4096x3072", "3072x4096",
}

MIN_PIXELS = 3_000_000  # Ark Seedream 4+ 最小 3MP（PR #7 教训）


def _check_min_pixels(size_str: str) -> str:
    """断言像素数 ≥ 3MP，否则抛出 ValueError（外层调用方转为 ValidationError）。"""
    w, h = map(int, size_str.split("x"))
    if w * h < MIN_PIXELS:
        raise ValueError(f"尺寸 {size_str} 像素数 {w*h/1_000_000:.1f}MP 低于 Ark 最小要求 3MP")
    return size_str


def normalize_size(
    size_mode: str,
    size: str = "2048x2048",
    size_tier: str = "2K",
    size_ratio: str = "1:1",
) -> str:
    """
    归一化尺寸输入为 Ark API 接受的 `{w}x{h}` 字符串。

    参数：
        size_mode: "pixel" | "tier" | "ratio"
        size:      pixel 模式的像素字符串（如 "2048x2048"）
        size_tier: tier/ratio 模式的档位名（如 "3K"），ratio 模式时与 size_ratio 联合决定最终像素
        size_ratio: ratio 模式的比例字符串（如 "16:9"）

    返回：归一化后的 size 字符串（如 "3840x2160"）
    异常：ValueError（调用方在 Serializer.validate() 中转为 ValidationError）
    """
    if size_mode == "pixel":
        if size not in PIXEL_VALID_SIZES:
            raise ValueError(f"不支持的像素尺寸：{size!r}，支持值：{sorted(PIXEL_VALID_SIZES)}")
        return _check_min_pixels(size)

    elif size_mode == "tier":
        if size_tier not in TIER_MAP:
            raise ValueError(f"不支持的档位：{size_tier!r}，支持值：{list(TIER_MAP.keys())}")
        return _check_min_pixels(TIER_MAP[size_tier])

    elif size_mode == "ratio":
        if size_ratio not in RATIO_TIER_MAP:
            raise ValueError(f"不支持的比例：{size_ratio!r}，支持值：{list(RATIO_TIER_MAP.keys())}")
        tier_choices = RATIO_TIER_MAP[size_ratio]
        if size_tier not in tier_choices:
            raise ValueError(f"不支持的档位：{size_tier!r}，支持值：{list(tier_choices.keys())}")
        return _check_min_pixels(tier_choices[size_tier])

    else:
        raise ValueError(f"不支持的 size_mode：{size_mode!r}，必须为 pixel / tier / ratio")
```

**单元测试要求（Canary 守卫）**：

```python
# image_generator/tests/test_size_normalizer.py

# TC-SIZE-01: tier "4K" → "4096x4096"
# TC-SIZE-02: ratio "9:16" + tier "2K" → "1620x2880"
# TC-SIZE-03: ratio "9:16" + tier "3K" → "2160x3840"
# TC-SIZE-04: ratio "16:9" + tier "4K" → "4096x2304"
# TC-SIZE-05: pixel "2880x1620" → "2880x1620"（直通）
# TC-SIZE-06: pixel 非枚举值 → ValueError
# TC-SIZE-07: tier 非枚举值 → ValueError
# TC-SIZE-08: ratio 非法比例 → ValueError
# TC-SIZE-09: size_mode 未知 → ValueError
# TC-SIZE-10: ratio "4:3" + tier "4K" → "4096x3072"（≥3MP 通过）
# TC-SIZE-11: ratio "3:4" + tier "3K" → "2304x3072"
```

---

### 1.2 ImageGenerationSubmitSerializer 扩展

在现有 Serializer 基础上新增字段并覆写 `validate()`：

```python
class ImageGenerationSubmitSerializer(serializers.Serializer):
    # --- 原有字段（保持不变）---
    prompt       = serializers.CharField(min_length=1, max_length=500)
    model        = serializers.ChoiceField(choices=SUPPORTED_MODELS, default="doubao-seedream-4-5-251128")
    n            = serializers.IntegerField(min_value=1, max_value=4, default=1)
    seed         = serializers.IntegerField(required=False, allow_null=True)
    negative_prompt = serializers.CharField(required=False, allow_blank=True, default="")
    guidance_scale  = serializers.FloatField(required=False, allow_null=True)
    steps        = serializers.IntegerField(required=False, allow_null=True)
    watermark    = serializers.BooleanField(required=False)

    # --- v1.2 新增字段 ---
    size_mode = serializers.ChoiceField(
        choices=["pixel", "tier", "ratio"],
        default="pixel",
        help_text="尺寸输入方式：pixel（像素精确）/ tier（档位）/ ratio（比例）",
    )
    size = serializers.ChoiceField(
        choices=list(PIXEL_VALID_SIZES),
        default="2048x2048",
        required=False,
        help_text="size_mode=pixel 时使用，像素精确尺寸字符串",
    )
    size_tier = serializers.ChoiceField(
        choices=["2K", "3K", "4K"],
        default="2K",
        required=False,
        help_text="size_mode=tier 时使用档位名称；size_mode=ratio 时与 size_ratio 联合决定像素（默认 2K）",
    )
    size_ratio = serializers.ChoiceField(
        choices=["1:1", "16:9", "9:16", "4:3", "3:4"],
        default="1:1",
        required=False,
        help_text="size_mode=ratio 时使用，比例字符串；必须配合 size_tier 使用",
    )

    def validate(self, data):
        """归一化 size，将三种输入方式统一为 validated_data['size']。
        ratio 模式下 size_tier 参与计算（默认 2K）。
        """
        from .size_normalizer import normalize_size
        try:
            normalized = normalize_size(
                size_mode=data.get("size_mode", "pixel"),
                size=data.get("size", "2048x2048"),
                size_tier=data.get("size_tier", "2K"),
                size_ratio=data.get("size_ratio", "1:1"),
            )
        except ValueError as e:
            raise serializers.ValidationError({"size": str(e)})
        data["size"] = normalized
        return data
```

**单元测试要求**：

```python
# image_generator/tests/test_serializers.py（扩展现有文件）

# TC-SER-01: size_mode=tier, size_tier=3K → validated_data["size"]="3072x3072"
# TC-SER-02: size_mode=ratio, size_ratio=9:16, size_tier=2K → validated_data["size"]="1620x2880"
# TC-SER-03: size_mode=ratio, size_ratio=16:9, size_tier=4K → validated_data["size"]="4096x2304"
# TC-SER-04: size_mode=ratio, size_ratio=9:16, size_tier=3K → validated_data["size"]="2160x3840"
# TC-SER-05: size_mode=pixel, size=2048x2048 → validated_data["size"]="2048x2048"（直通）
# TC-SER-06: size_mode=pixel, 非法 size → 400 ValidationError
# TC-SER-07: size_mode=tier 缺 size_tier → 使用默认值 "2K" → "2048x2048"
# TC-SER-08: n=5 → ValidationError（已有测试，确认不退化）
# TC-SER-09: model=5.0-lite, steps 字段出现在请求中 → Serializer 允许，Task 层过滤（守卫测试）
```

---

### 1.3 MODEL_ADVANCED_PARAMS 白名单确认

现有代码（doubao_image_client.py）已正确实现：

```python
MODEL_ADVANCED_PARAMS: dict[str, set[str]] = {
    "doubao-seedream-5-0-260128": {"seed", "guidance_scale", "negative_prompt", "watermark"},
    "doubao-seedream-4-5-251128": {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
    "doubao-seedream-4-0-250828": {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
}
```

v1.2 无需变更，已覆盖 §2.1 全量高级参数。

**Canary 守卫测试（新增，强制覆盖已知教训）**：

```python
# image_generator/tests/test_doubao_client.py（扩展）

# TC-CLIENT-01: model=5.0-lite + advanced_params含steps → 请求体无 steps 键
# TC-CLIENT-02: model=4.5 + advanced_params含steps=50 → 请求体含 "steps": 50
# TC-CLIENT-03: guidance_scale=8.0 → 请求体含 "guidance_scale": 8.0
# TC-CLIENT-04: seed=12345 → 请求体含 "seed": 12345（复现能力守卫）
# TC-CLIENT-05: watermark=true → 请求体含 "watermark": true
```

---

### 1.4 即梦 API 后端清理评估

经代码审查，后端残留情况：

| 位置 | 残留内容 | 清理动作 |
|------|---------|---------|
| `settings_vault/models.py` L22 | `("jimeng", "即梦视频/图片生成")` 枚举值 | 保留（历史数据兼容，ADR-v1.2-04） |
| `settings_vault/views.py` | 可能有 jimeng 分支处理 | 需审查，若有独立图片即梦路由则删除 |
| `video_generator/jimeng_client.py` | 视频生成客户端 | 不在本次范围，保留 |

> 开发阶段需用 `grep -r "jimeng" apps/` 确认残留范围，本次设计不变更后端 jimeng 图片 API 路由（视频路由不动）。

---

## 2. 前端模块详细设计

### 2.1 SizeSelector.vue（新增组件）

**位置**：`src/components/ImageGenerator/SizeSelector.vue`

**Props / Emits**：

```typescript
// Props
interface Props {
  modelValue: {
    size_mode: 'pixel' | 'tier' | 'ratio'
    size: string        // pixel 模式使用
    size_tier: string   // tier 模式使用
    size_ratio: string  // ratio 模式使用
  }
  disabled: boolean
}

// Emits
emit('update:modelValue', SizeSelectorValue)
```

**UI 结构（ASCII 线框图）**：

```
┌─────────────────────────────────────────────┐
│ 图片尺寸                                      │
│  [ 精确像素 | 档位 | 比例 ]  ← el-radio-button│
│                                               │
│  精确像素 模式：                               │
│  ┌─────────────────────────────────────────┐ │
│  │ 2048×2048 (1:1, 4.2MP)              ▼  │ │  ← el-select
│  └─────────────────────────────────────────┘ │
│                                               │
│  档位模式：                                   │
│  [2K（4MP）] [3K（9MP）] [4K（17MP）]         │  ← el-radio-button
│                                               │
│  比例模式：                                   │
│  [1:1] [16:9] [9:16] [4:3] [3:4]            │  ← el-radio-button
└─────────────────────────────────────────────┘
```

**数据流**：组件内部维护 `localValue`，深监听变化后 emit `update:modelValue`；切换 size_mode 时自动重置对应子字段为默认值。

**提交时映射**（`ImageGeneratorView.submitGeneration()`）：

```javascript
// 将 SizeSelector 的值拆分追加到 FormData
formData.append('size_mode', sizeValue.size_mode)
if (sizeValue.size_mode === 'pixel')  formData.append('size', sizeValue.size)
if (sizeValue.size_mode === 'tier')   formData.append('size_tier', sizeValue.size_tier)
if (sizeValue.size_mode === 'ratio')  formData.append('size_ratio', sizeValue.size_ratio)
```

---

### 2.2 GenerationModeSelector.vue（新增组件）

**位置**：`src/components/ImageGenerator/GenerationModeSelector.vue`

**UI**：

```
生成模式：
[主图 (×1)] [多图 (×2)] [多图 (×3)] [多图 (×4)]
← el-radio-button group
```

- 选择"主图"时，`modelValue = 1`
- 选择"多图×N"时，`modelValue = N`（N ∈ {2, 3, 4}）
- 该组件替代现有 `BatchCountSelector.vue`（BatchCountSelector 可保留用于向下兼容或移除）

---

### 2.3 ImageGeneratorView.vue 布局调整

**当前**：`grid-template-columns: 380px 1fr`

**v1.2**：`grid-template-columns: 480px 1fr`（断点 ≤ 1100px 改为 1fr）

**面板内组件顺序**（自上而下）：

```
1. 提示词输入（已有）
2. 模型选择（已有）
3. 生成模式切换 [新增 GenerationModeSelector]
4. 图片尺寸 [新增 SizeSelector]
5. 参考图上传（已有）
6. 高级选项折叠面板（已有，内容微调）
7. 开始生成按钮（已有）
```

---

### 2.4 AdvancedParamsPanel.vue 微调

- `guidance_scale` 滑块范围从 `1–20` 调整（已是正确范围，确认 step=0.1）
- 确认 `steps` 条件显示逻辑：`v-if="modelSupportsSteps"`，5.0 Lite 隐藏
- 移除 `BatchCountSelector` 的重复嵌入（如 BatchCountSelector 已被 GenerationModeSelector 替代）

---

### 2.5 MediaLibraryView.vue — Lightbox 改造

> 用户已确认：Lightbox 目标为 **MediaLibraryView**（`/media-library`）。KnowledgeBaseView 不需要图片预览，不做任何改动。

**改造方案**：在 MediaLibraryView 的图片列表条目中，使用 `el-image` 的 `preview-src-list` 实现点击放大。

**设计方案**：

```vue
<!-- 在操作列添加预览按钮（仅图片类型显示）-->
<el-image
  v-if="isImageType(row.file_type)"
  :src="row.file_url"
  :preview-src-list="allImageUrls"
  :initial-index="getImageIndex(row)"
  preview-teleported
  style="width: 32px; height: 32px; cursor: pointer;"
/>

<!-- allImageUrls：当前列表中所有图片 URL 的数组，支持左右切换 -->
<!-- preview-teleported：将预览弹层挂载到 body，避免 z-index 问题 -->
```

```javascript
// 判断是否为图片类型
function isImageType(fileType) {
  return ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(fileType?.toLowerCase())
}

// 所有图片 URL 列表（用于 preview-src-list 支持左右切换）
const allImageUrls = computed(() =>
  mediaItems.value
    .filter(d => isImageType(d.file_type))
    .map(d => d.file_url)
    .filter(Boolean)
)

function getImageIndex(row) {
  return allImageUrls.value.indexOf(row.file_url)
}
```

> 注意：需确认 MediaLibraryView 条目的字段名（`file_url` / `file_type`）。如字段名不同则按实际字段名调整；如无图片类型条目则 Lightbox 功能静默不显示，不影响现有文档流程。

---

### 2.6 SettingsView.vue — 即梦 Tab 清理

删除内容：

```vue
<!-- 以下内容整体删除 -->
<el-tab-pane label="即梦 API" name="jimeng">
  <el-card>
    <h3>即梦（即创）视频 API</h3>
    <el-form :model="jimengForm" label-width="140px">
      ...
    </el-form>
  </el-card>
</el-tab-pane>
```

```javascript
// 以下变量和函数整体删除
const jimengForm    = ref({ access_key: "", secret_key: "" });
const savingJimeng  = ref(false);
const testingJimeng = ref(false);
async function saveJimengConfig() { ... }
async function testJimengConfig() { ... }

// onMounted 中以下 else-if 分支删除（服务端列表遍历）：
} else if (cfg.service_type === "jimeng" && cfg.is_configured) {
  if (preview.access_key) jimengForm.value.access_key = preview.access_key;
  if (preview.secret_key) jimengForm.value.secret_key = preview.secret_key;
}
```

---

## 3. 数据库变更

**本次 v1.2 无 DB Migration**：

- SizeNormalizer 逻辑在 Serializer/Task 层，不持久化 size_mode
- ImageBatch 不新增字段（size 仍通过 task 参数传递，ADR-04 原则）
- 即梦清理仅为前端 UI 删除，不删除 DB 记录

---

## 4. API 接口变更

### 扩展接口：POST /api/v1/image/generate/

**新增字段（向下兼容，旧客户端仍可不传 size_mode）**：

```json
// 请求体（FormData 或 JSON）
{
  "prompt": "...",
  "model": "doubao-seedream-4-5-251128",
  "n": 1,
  "size_mode": "ratio",      // 新增，默认 "pixel"
  "size": "2048x2048",       // size_mode=pixel 时（已有，保留向下兼容）
  "size_tier": "3K",         // size_mode=tier 时（新增）
  "size_ratio": "16:9",      // size_mode=ratio 时（新增）
  "seed": null,
  "guidance_scale": 7.5,
  "negative_prompt": "",
  "steps": null,
  "watermark": false
}
```

**响应体（不变）**：

```json
{
  "batch_id": 42,
  "batch_name": "0514-1030 日落时分...",
  "request_ids": [101],
  "status": "pending",
  "total_count": 1
}
```

**无新增接口**；KB Lightbox 完全前端实现，无后端 API 变更。

---

## 5. 测试策略

### 5.1 后端 unit 测试（pytest，不含 integration 标记）

| 测试文件 | 新增测试数 | 覆盖内容 |
|---------|---------|---------|
| `test_size_normalizer.py`（新建） | 7 | SizeNormalizer 所有路径 |
| `test_serializers.py`（扩展） | 7 | 序列化器新字段 + 归一化集成 |
| `test_doubao_client.py`（扩展） | 5 | 白名单过滤 Canary 守卫 |
| `test_views.py`（扩展） | 3 | View 层 size_mode 字段透传 |

### 5.2 前端 E2E（Playwright）

| 测试文件 | 场景 |
|---------|------|
| `test_image_ui_size.spec.ts` | US-01~03 尺寸三模式 |
| `test_image_ui_mode.spec.ts` | US-05 生成模式切换 |
| `test_image_ui_layout.spec.ts` | US-06 面板宽度/响应式 |
| `test_media_library_lightbox.spec.ts` | US-07 Lightbox（MediaLibraryView） |
| `test_settings_cleanup.spec.ts` | US-08 即梦 Tab 消失 |

---

## 6. ASCII 线框图：调整后的 AI 图片页面

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AI 图片生成                                                                   │
│  [生成图片] [批次管理]                                                          │
├───────────────────────────┬──────────────────────────────────────────────────┤
│  生成设置 (480px)          │  生成结果                                          │
│ ┌───────────────────────┐ │ ┌──────────────────────────────────────────────┐ │
│ │ 描述提示词 *           │ │ │                                              │ │
│ │ ┌─────────────────┐  │ │ │                                              │ │
│ │ │                 │  │ │ │              ( 空闲 / 生成中 / 结果网格 )      │ │
│ │ └─────────────────┘  │ │ │                                              │ │
│ │                       │ │ │                                              │ │
│ │ 选择模型              │ │ │                                              │ │
│ │ [◉ Seedream 4.5] [○4.0] [○5.0 Lite]                                   │ │
│ │                       │ │ │                                              │ │
│ │ 生成模式              │ │ │                                              │ │
│ │ [主图(×1)] [×2] [×3] [×4]                                              │ │
│ │                       │ │ │                                              │ │
│ │ 图片尺寸              │ │ │                                              │ │
│ │ [精确像素|档位|比例]  │ │ │                                              │ │
│ │ ┌────────────────┐   │ │ │                                              │ │
│ │ │ 2048×2048 ▼   │   │ │ │                                              │ │
│ │ └────────────────┘   │ │ │                                              │ │
│ │                       │ │ │                                              │ │
│ │ 参考图片（可选）       │ │ │                                              │ │
│ │ ┌────────────────┐   │ │ │                                              │ │
│ │ │  拖拽/点击上传  │   │ │ │                                              │ │
│ │ └────────────────┘   │ │ │                                              │ │
│ │                       │ │ │                                              │ │
│ │ ▷ 高级选项            │ │ │                                              │ │
│ │   seed / neg_prompt   │ │ │                                              │ │
│ │   guidance / steps    │ │ │                                              │ │
│ │   watermark           │ │ │                                              │ │
│ │                       │ │ │                                              │ │
│ │ [    开始生成    ]     │ │ │                                              │ │
│ └───────────────────────┘ │ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```
