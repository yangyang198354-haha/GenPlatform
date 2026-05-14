"""
SizeNormalizer 单元测试。

覆盖 normalize_size() 所有执行路径：
  - pixel 模式：直通白名单、非法尺寸拒绝
  - tier 模式：3 个档位映射、非法档位拒绝
  - ratio 模式：15 个组合映射（5 比例 × 3 档位）
  - ratio 模式：非法比例 / 非法档位拒绝
  - 3MP 最小值校验（兜底）
  - 未知 size_mode 拒绝

关联需求：FR-1.2、REQ-SPEC-v1.2 §2.3（PR #7 教训）
"""
import pytest

from apps.image_generator.size_normalizer import (
    PIXEL_VALID_SIZES,
    RATIO_TIER_MAP,
    TIER_MAP,
    normalize_size,
)


class TestNormalizeSizePixelMode:
    """pixel 模式：直接传入像素字符串。"""

    def test_pixel_2048x2048_passthrough(self):
        """TC-SIZE-01: 合法像素 2048x2048 直通返回。"""
        assert normalize_size("pixel", size="2048x2048") == "2048x2048"

    def test_pixel_2880x1620_passthrough(self):
        """TC-SIZE-02: 合法像素 2880x1620 直通。"""
        assert normalize_size("pixel", size="2880x1620") == "2880x1620"

    def test_pixel_4096x4096_passthrough(self):
        """TC-SIZE-03: 合法像素 4096x4096 直通。"""
        assert normalize_size("pixel", size="4096x4096") == "4096x4096"

    def test_pixel_all_valid_sizes_pass(self):
        """TC-SIZE-04: 所有 PIXEL_VALID_SIZES 枚举值均应通过。"""
        for size in PIXEL_VALID_SIZES:
            result = normalize_size("pixel", size=size)
            assert result == size, f"合法 size {size} 应直通，实际：{result}"

    def test_pixel_invalid_999x999_rejected(self):
        """TC-SIZE-05: 不在白名单的 999x999 应抛出 ValueError（AC-01-2）。"""
        with pytest.raises(ValueError, match="不支持的像素尺寸"):
            normalize_size("pixel", size="999x999")

    def test_pixel_invalid_arbitrary_string_rejected(self):
        """TC-SIZE-06: 任意非枚举字符串应抛出 ValueError。"""
        with pytest.raises(ValueError):
            normalize_size("pixel", size="1920x1080")

    def test_pixel_empty_string_rejected(self):
        """TC-SIZE-07: 空字符串应抛出 ValueError。"""
        with pytest.raises(ValueError):
            normalize_size("pixel", size="")


class TestNormalizeSizeTierMode:
    """tier 模式：按档位映射。"""

    def test_tier_2k_maps_to_2048x2048(self):
        """TC-SIZE-08: 档位 2K → 2048x2048（AC-02-1）。"""
        assert normalize_size("tier", size_tier="2K") == "2048x2048"

    def test_tier_3k_maps_to_3072x3072(self):
        """TC-SIZE-09: 档位 3K → 3072x3072。"""
        assert normalize_size("tier", size_tier="3K") == "3072x3072"

    def test_tier_4k_maps_to_4096x4096(self):
        """TC-SIZE-10: 档位 4K → 4096x4096（AC-02-2）。"""
        assert normalize_size("tier", size_tier="4K") == "4096x4096"

    def test_tier_all_tiers_consistent_with_tier_map(self):
        """TC-SIZE-11: TIER_MAP 中所有档位映射一致。"""
        for tier, expected in TIER_MAP.items():
            result = normalize_size("tier", size_tier=tier)
            assert result == expected

    def test_tier_invalid_5k_rejected(self):
        """TC-SIZE-12: 不支持的档位 5K 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="不支持的档位"):
            normalize_size("tier", size_tier="5K")

    def test_tier_invalid_hd_rejected(self):
        """TC-SIZE-13: 不在枚举中的 HD 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            normalize_size("tier", size_tier="HD")


class TestNormalizeSizeRatioMode:
    """ratio 模式：比例 × 档位 15 个组合。"""

    # ── 1:1 ─────────────────────────────────────────────────────────────────
    def test_ratio_1x1_tier_2k(self):
        """1:1 × 2K → 2048x2048。"""
        assert normalize_size("ratio", size_tier="2K", size_ratio="1:1") == "2048x2048"

    def test_ratio_1x1_tier_3k(self):
        """1:1 × 3K → 3072x3072。"""
        assert normalize_size("ratio", size_tier="3K", size_ratio="1:1") == "3072x3072"

    def test_ratio_1x1_tier_4k(self):
        """1:1 × 4K → 4096x4096。"""
        assert normalize_size("ratio", size_tier="4K", size_ratio="1:1") == "4096x4096"

    # ── 16:9 ────────────────────────────────────────────────────────────────
    def test_ratio_16x9_tier_2k(self):
        """TC-SIZE-14: 16:9 × 2K → 2880x1620（AC-03-1 等价）。"""
        assert normalize_size("ratio", size_tier="2K", size_ratio="16:9") == "2880x1620"

    def test_ratio_16x9_tier_3k(self):
        """16:9 × 3K → 3840x2160。"""
        assert normalize_size("ratio", size_tier="3K", size_ratio="16:9") == "3840x2160"

    def test_ratio_16x9_tier_4k(self):
        """TC-SIZE-15: 16:9 × 4K → 4096x2304（AC-03-3）。"""
        assert normalize_size("ratio", size_tier="4K", size_ratio="16:9") == "4096x2304"

    # ── 9:16 ────────────────────────────────────────────────────────────────
    def test_ratio_9x16_tier_2k(self):
        """9:16 × 2K → 1620x2880（AC-03-1）。"""
        assert normalize_size("ratio", size_tier="2K", size_ratio="9:16") == "1620x2880"

    def test_ratio_9x16_tier_3k(self):
        """TC-SIZE-16: 9:16 × 3K → 2160x3840（AC-03-4）。"""
        assert normalize_size("ratio", size_tier="3K", size_ratio="9:16") == "2160x3840"

    def test_ratio_9x16_tier_4k(self):
        """9:16 × 4K → 2304x4096。"""
        assert normalize_size("ratio", size_tier="4K", size_ratio="9:16") == "2304x4096"

    # ── 4:3 ─────────────────────────────────────────────────────────────────
    def test_ratio_4x3_tier_2k(self):
        """4:3 × 2K → 2880x2160（AC-03-2）。"""
        assert normalize_size("ratio", size_tier="2K", size_ratio="4:3") == "2880x2160"

    def test_ratio_4x3_tier_3k(self):
        """4:3 × 3K → 3072x2304。"""
        assert normalize_size("ratio", size_tier="3K", size_ratio="4:3") == "3072x2304"

    def test_ratio_4x3_tier_4k(self):
        """4:3 × 4K → 4096x3072。"""
        assert normalize_size("ratio", size_tier="4K", size_ratio="4:3") == "4096x3072"

    # ── 3:4 ─────────────────────────────────────────────────────────────────
    def test_ratio_3x4_tier_2k(self):
        """3:4 × 2K → 2160x2880。"""
        assert normalize_size("ratio", size_tier="2K", size_ratio="3:4") == "2160x2880"

    def test_ratio_3x4_tier_3k(self):
        """3:4 × 3K → 2304x3072（TC-SIZE-11 等价）。"""
        assert normalize_size("ratio", size_tier="3K", size_ratio="3:4") == "2304x3072"

    def test_ratio_3x4_tier_4k(self):
        """3:4 × 4K → 3072x4096。"""
        assert normalize_size("ratio", size_tier="4K", size_ratio="3:4") == "3072x4096"

    # ── 全表一致性测试 ────────────────────────────────────────────────────────
    def test_ratio_all_15_combinations_consistent_with_map(self):
        """TC-SIZE-17: RATIO_TIER_MAP 中 15 个组合与 normalize_size 输出一致。"""
        count = 0
        for ratio, tier_map in RATIO_TIER_MAP.items():
            for tier, expected in tier_map.items():
                result = normalize_size("ratio", size_tier=tier, size_ratio=ratio)
                assert result == expected, (
                    f"组合 {ratio!r} × {tier!r} 期望 {expected!r}，实际 {result!r}"
                )
                count += 1
        assert count == 15, f"应有 15 个组合，实际测试了 {count} 个"

    # ── ratio 模式错误处理 ────────────────────────────────────────────────────
    def test_ratio_invalid_ratio_rejected(self):
        """TC-SIZE-08: 非法比例应抛出 ValueError。"""
        with pytest.raises(ValueError, match="不支持的比例"):
            normalize_size("ratio", size_tier="2K", size_ratio="21:9")

    def test_ratio_invalid_tier_rejected(self):
        """TC-SIZE-09: 合法比例配合非法档位应抛出 ValueError。"""
        with pytest.raises(ValueError, match="不支持的档位"):
            normalize_size("ratio", size_tier="8K", size_ratio="16:9")


class TestNormalizeSizeEdgeCases:
    """边界情况与防御性测试。"""

    def test_unknown_size_mode_rejected(self):
        """TC-SIZE-09: 未知 size_mode 应抛出 ValueError（AC-01-2 通用）。"""
        with pytest.raises(ValueError, match="不支持的 size_mode"):
            normalize_size("absolute")

    def test_default_arguments_return_2048x2048(self):
        """TC-SIZE-10: 默认参数（pixel 模式）返回 2048x2048。"""
        assert normalize_size("pixel") == "2048x2048"

    def test_all_valid_sizes_are_at_least_3mp(self):
        """TC-SIZE-11（Canary 守卫）: 所有 PIXEL_VALID_SIZES 均满足 3MP 约束（PR #7 教训）。"""
        min_pixels = 3_000_000
        for size in PIXEL_VALID_SIZES:
            w, h = map(int, size.split("x"))
            pixels = w * h
            assert pixels >= min_pixels, (
                f"尺寸 {size} 仅有 {pixels / 1_000_000:.2f}MP，低于 3MP 最小约束"
            )

    def test_all_ratio_tier_combinations_are_at_least_3mp(self):
        """TC-SIZE-12（Canary 守卫）: RATIO_TIER_MAP 15 个组合均 ≥ 3MP（PR #7 教训）。"""
        min_pixels = 3_000_000
        for ratio, tier_map in RATIO_TIER_MAP.items():
            for tier, size_str in tier_map.items():
                w, h = map(int, size_str.split("x"))
                pixels = w * h
                assert pixels >= min_pixels, (
                    f"组合 {ratio!r} × {tier!r} → {size_str}，"
                    f"仅有 {pixels / 1_000_000:.2f}MP，低于 3MP 约束"
                )
