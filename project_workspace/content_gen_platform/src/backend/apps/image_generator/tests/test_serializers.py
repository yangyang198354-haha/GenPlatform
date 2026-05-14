"""
图片生成序列化器单元测试——豆包 Seedream 版本。

测试内容：
- ImageGenerationSubmitSerializer：n 边界（0/1/4/5）Canary 守卫测试（OQ-4，AC-04-5）
- 模型枚举校验（AC-01-5）
- 高级参数提取（get_advanced_params）
- size 枚举校验

关联需求：FR-2、OQ-4、AC-04-5、AC-01-5、ADR-05

重要说明：
  本文件中的 n=5 边界拒绝用例是"Canary 守卫测试"——
  如果将来有人错误地把 max_value 从 4 改为更大值，此测试会立即失败并
  阻止错误代码进入 CI 流水线（参考 feedback_ci_coverage_guards.md）。
"""
import pytest

from apps.image_generator.serializers import ImageGenerationSubmitSerializer


class TestSubmitSerializerNBoundary:
    """
    n 参数边界值测试——Canary 守卫测试。

    根据 OQ-4 / AC-04-5 / feedback_ci_coverage_guards.md：
    - n=1：最小合法值，必须通过
    - n=4：最大合法值，必须通过
    - n=0：低于最小值，必须被拒绝
    - n=5：超过最大值，必须被拒绝（Canary 守卫）

    如果 max_value 被错误修改，n=5 的测试会第一时间暴露问题。
    """

    def _valid_base(self):
        return {"prompt": "测试提示词", "model": "Doubao-Seedream-4.5"}

    # ── Canary 守卫测试（最重要，必须保留）────────────────────────────────────

    def test_n_equals_5_is_rejected_canary_guard(self):
        """
        【Canary 守卫】n=5 必须被 Serializer 拒绝，返回 400。

        这是硬约束守卫测试：如果此测试失败，说明 max_value=4 被错误修改。
        此测试代表了"三层防护"中 Serializer 层的防线（OQ-4，AC-04-5）。
        """
        data = {**self._valid_base(), "n": 5}
        s = ImageGenerationSubmitSerializer(data=data)
        assert not s.is_valid(), "n=5 应被 Serializer 拒绝，但 is_valid() 返回 True"
        assert "n" in s.errors, f"错误字段应为 'n'，实际错误字段：{list(s.errors.keys())}"

    # ── 合法边界值测试 ─────────────────────────────────────────────────────────

    def test_n_equals_1_is_valid(self):
        """n=1 是最小合法值，必须通过（OQ-4）。"""
        data = {**self._valid_base(), "n": 1}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid(), f"n=1 应通过验证，错误：{s.errors}"
        assert s.validated_data["n"] == 1

    def test_n_equals_4_is_valid(self):
        """n=4 是最大合法值，必须通过（OQ-4，AC-04-5 正向用例）。"""
        data = {**self._valid_base(), "n": 4}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid(), f"n=4 应通过验证，错误：{s.errors}"
        assert s.validated_data["n"] == 4

    # ── 非法边界值测试 ─────────────────────────────────────────────────────────

    def test_n_equals_0_is_rejected(self):
        """n=0 低于最小值 1，必须被拒绝。"""
        data = {**self._valid_base(), "n": 0}
        s = ImageGenerationSubmitSerializer(data=data)
        assert not s.is_valid(), "n=0 应被拒绝"
        assert "n" in s.errors

    def test_n_default_is_1(self):
        """不传 n 时默认值为 1（FR-2 基础场景）。"""
        data = self._valid_base()  # 不含 n
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid(), f"默认 n 应通过验证，错误：{s.errors}"
        assert s.validated_data["n"] == 1


class TestSubmitSerializerModelValidation:
    """模型枚举校验测试（AC-01-5）。"""

    def test_supported_model_50_lite_is_valid(self):
        """Doubao-Seedream-5.0-lite 是支持的模型，应通过。"""
        s = ImageGenerationSubmitSerializer(data={
            "prompt": "test", "model": "Doubao-Seedream-5.0-lite"
        })
        assert s.is_valid(), f"5.0-lite 应通过，错误：{s.errors}"

    def test_supported_model_45_is_valid(self):
        """Doubao-Seedream-4.5 是支持的模型，应通过。"""
        s = ImageGenerationSubmitSerializer(data={
            "prompt": "test", "model": "Doubao-Seedream-4.5"
        })
        assert s.is_valid(), f"4.5 应通过，错误：{s.errors}"

    def test_supported_model_40_is_valid(self):
        """Doubao-Seedream-4.0 是支持的模型，应通过。"""
        s = ImageGenerationSubmitSerializer(data={
            "prompt": "test", "model": "Doubao-Seedream-4.0"
        })
        assert s.is_valid(), f"4.0 应通过，错误：{s.errors}"

    def test_unsupported_model_jimeng_is_rejected(self):
        """即梦模型（已下线）必须被拒绝（AC-01-5，清理验证）。"""
        s = ImageGenerationSubmitSerializer(data={
            "prompt": "test", "model": "Jimeng-v1"
        })
        assert not s.is_valid(), "不支持的模型应被拒绝"
        assert "model" in s.errors

    def test_unsupported_model_random_is_rejected(self):
        """任意非白名单模型应被拒绝（AC-01-5）。"""
        s = ImageGenerationSubmitSerializer(data={
            "prompt": "test", "model": "GPT-4-vision"
        })
        assert not s.is_valid()
        assert "model" in s.errors

    def test_default_model_is_45(self):
        """不传 model 时默认使用 Doubao-Seedream-4.5。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "test"})
        assert s.is_valid(), f"默认模型应通过，错误：{s.errors}"
        assert s.validated_data["model"] == "Doubao-Seedream-4.5"


class TestSubmitSerializerPromptValidation:
    """提示词校验测试（FR-2）。"""

    def test_empty_prompt_is_rejected(self):
        """空提示词必须被拒绝。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": ""})
        assert not s.is_valid()
        assert "prompt" in s.errors

    def test_prompt_500_chars_is_valid(self):
        """500 字符的提示词是边界合法值。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "a" * 500})
        assert s.is_valid(), f"500 字符提示词应通过，错误：{s.errors}"

    def test_prompt_501_chars_is_rejected(self):
        """501 字符的提示词超出最大长度，应被拒绝。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "a" * 501})
        assert not s.is_valid()
        assert "prompt" in s.errors


class TestSubmitSerializerAdvancedParams:
    """高级参数提取测试（ADR-05，OQ-2）。"""

    def _valid_base(self):
        return {"prompt": "test", "model": "Doubao-Seedream-4.5"}

    def test_get_advanced_params_extracts_seed(self):
        """传入 seed 时应在 advanced_params 中返回。"""
        data = {**self._valid_base(), "seed": 42}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid()
        params = s.get_advanced_params()
        assert params.get("seed") == 42

    def test_get_advanced_params_excludes_none_values(self):
        """值为 None 的参数不应出现在 advanced_params 中。"""
        data = {**self._valid_base(), "seed": None}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid()
        params = s.get_advanced_params()
        assert "seed" not in params

    def test_get_advanced_params_excludes_empty_negative_prompt(self):
        """空字符串的 negative_prompt 不应出现在 advanced_params 中。"""
        data = {**self._valid_base(), "negative_prompt": ""}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid()
        params = s.get_advanced_params()
        assert "negative_prompt" not in params

    def test_get_advanced_params_includes_guidance_scale(self):
        """非 None 的 guidance_scale 应被提取。"""
        data = {**self._valid_base(), "guidance_scale": 7.5}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid()
        params = s.get_advanced_params()
        assert params.get("guidance_scale") == 7.5

    def test_get_advanced_params_empty_when_no_extra_params(self):
        """只传基础参数时，advanced_params 应为空（或只含默认 watermark=False）。"""
        data = self._valid_base()
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid()
        params = s.get_advanced_params()
        # watermark=False 默认值不应被包含（因为 False 是 falsy）
        assert "watermark" not in params

    def test_watermark_true_is_included(self):
        """watermark=True 时应被包含在 advanced_params 中。"""
        data = {**self._valid_base(), "watermark": True}
        s = ImageGenerationSubmitSerializer(data=data)
        assert s.is_valid()
        params = s.get_advanced_params()
        assert params.get("watermark") is True


class TestSubmitSerializerSizeValidation:
    """尺寸枚举校验测试。"""

    def test_valid_size_1024x1024(self):
        """1024x1024 是默认合法尺寸。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "test", "size": "1024x1024"})
        assert s.is_valid()

    def test_valid_size_1280x720(self):
        """1280x720（横向）是合法尺寸。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "test", "size": "1280x720"})
        assert s.is_valid()

    def test_valid_size_720x1280(self):
        """720x1280（竖向）是合法尺寸。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "test", "size": "720x1280"})
        assert s.is_valid()

    def test_invalid_size_is_rejected(self):
        """不在枚举中的尺寸应被拒绝。"""
        s = ImageGenerationSubmitSerializer(data={"prompt": "test", "size": "4096x4096"})
        assert not s.is_valid()
        assert "size" in s.errors
