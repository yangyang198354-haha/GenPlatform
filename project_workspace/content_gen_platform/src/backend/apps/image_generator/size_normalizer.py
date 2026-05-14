"""
SizeNormalizer — 图片尺寸归一化模块。

将三种用户输入方式（pixel 精确像素 / tier 档位 / ratio 比例×档位组合）
归一化为 Ark API 接受的 "{w}x{h}" 字符串。

设计依据：
  - v1.2 需求规格 §2.3（档位×比例 15 个组合映射表）
  - Ark Seedream 4+ 最小 3MP 约束（PR #7 教训）

关联需求：FR-1.2、REQ-SPEC-v1.2 §2.3
"""

# ── 档位映射（单独用于 tier 模式） ─────────────────────────────────────────────
TIER_MAP: dict[str, str] = {
    "2K": "2048x2048",
    "3K": "3072x3072",
    "4K": "4096x4096",
}

# ── 比例 × 档位组合映射表（ratio 模式必须配合 size_tier） ──────────────────────
# RATIO_TIER_MAP[ratio][tier] → "{w}x{h}"
# 15 个组合（5 比例 × 3 档位），全部 ≥ 3MP
RATIO_TIER_MAP: dict[str, dict[str, str]] = {
    "1:1": {
        "2K": "2048x2048",   # 4.2 MP
        "3K": "3072x3072",   # 9.4 MP
        "4K": "4096x4096",   # 16.8 MP
    },
    "16:9": {
        "2K": "2880x1620",   # 4.7 MP
        "3K": "3840x2160",   # 8.3 MP
        "4K": "4096x2304",   # 9.4 MP
    },
    "9:16": {
        "2K": "1620x2880",   # 4.7 MP
        "3K": "2160x3840",   # 8.3 MP
        "4K": "2304x4096",   # 9.4 MP
    },
    "4:3": {
        "2K": "2880x2160",   # 6.2 MP
        "3K": "3072x2304",   # 7.1 MP
        "4K": "4096x3072",   # 12.6 MP
    },
    "3:4": {
        "2K": "2160x2880",   # 6.2 MP
        "3K": "2304x3072",   # 7.1 MP
        "4K": "3072x4096",   # 12.6 MP
    },
}

# ── 像素精确档枚举白名单（防止任意字符串注入 Ark） ─────────────────────────────
# 包含所有 RATIO_TIER_MAP 值 + TIER_MAP 值，已去重
PIXEL_VALID_SIZES: set[str] = {
    # 2K 系列
    "2048x2048", "2880x1620", "1620x2880", "2880x2160", "2160x2880",
    # 3K 系列
    "3072x3072", "3840x2160", "2160x3840", "3072x2304", "2304x3072",
    # 4K 系列
    "4096x4096", "4096x2304", "2304x4096", "4096x3072", "3072x4096",
}

# 最小像素数（Ark Seedream 4+ 约束，PR #7 教训）
MIN_PIXELS = 3_000_000


def _check_min_pixels(size_str: str) -> str:
    """
    断言像素数 ≥ 3MP，否则抛出 ValueError。
    调用方在 Serializer.validate() 中将 ValueError 转为 ValidationError。
    """
    w, h = map(int, size_str.split("x"))
    if w * h < MIN_PIXELS:
        raise ValueError(
            f"尺寸 {size_str} 像素数 {w * h / 1_000_000:.1f}MP 低于 Ark 最小要求 3MP"
        )
    return size_str


def normalize_size(
    size_mode: str,
    size: str = "2048x2048",
    size_tier: str = "2K",
    size_ratio: str = "1:1",
) -> str:
    """
    归一化尺寸输入为 Ark API 接受的 "{w}x{h}" 字符串。

    参数：
        size_mode:  "pixel" | "tier" | "ratio"
        size:       pixel 模式的像素字符串（如 "2048x2048"）
        size_tier:  tier/ratio 模式的档位名（"2K" | "3K" | "4K"）；
                    ratio 模式下与 size_ratio 联合决定最终像素（默认 "2K"）
        size_ratio: ratio 模式的比例字符串（如 "16:9"）

    返回：
        归一化后的 size 字符串（如 "3840x2160"）

    异常：
        ValueError：输入不合法，调用方在 Serializer.validate() 中转为 ValidationError
    """
    if size_mode == "pixel":
        if size not in PIXEL_VALID_SIZES:
            raise ValueError(
                f"不支持的像素尺寸：{size!r}，"
                f"支持值：{sorted(PIXEL_VALID_SIZES)}"
            )
        return _check_min_pixels(size)

    elif size_mode == "tier":
        if size_tier not in TIER_MAP:
            raise ValueError(
                f"不支持的档位：{size_tier!r}，支持值：{list(TIER_MAP.keys())}"
            )
        return _check_min_pixels(TIER_MAP[size_tier])

    elif size_mode == "ratio":
        if size_ratio not in RATIO_TIER_MAP:
            raise ValueError(
                f"不支持的比例：{size_ratio!r}，"
                f"支持值：{list(RATIO_TIER_MAP.keys())}"
            )
        tier_choices = RATIO_TIER_MAP[size_ratio]
        if size_tier not in tier_choices:
            raise ValueError(
                f"不支持的档位：{size_tier!r}，"
                f"比例 {size_ratio!r} 支持的档位：{list(tier_choices.keys())}"
            )
        return _check_min_pixels(tier_choices[size_tier])

    else:
        raise ValueError(
            f"不支持的 size_mode：{size_mode!r}，必须为 pixel / tier / ratio"
        )
