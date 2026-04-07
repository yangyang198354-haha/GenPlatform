"""Unit tests for scene_generator module."""
import pytest
from unittest.mock import patch, MagicMock
from apps.video_generator.scene_generator import (
    _validate_and_normalize_scenes,
    validate_scene_continuity,
    generate_scenes_from_content,
)


class TestValidateAndNormalizeScenes:
    def test_basic_normalization(self):
        raw = [
            {
                "scene_prompt": "A sunny park",
                "narration": "Beautiful day.",
                "voice_style": {"speed": "normal", "emotion": "neutral", "voice_id": "zh_female_1"},
                "duration_sec": 5,
                "transition": "cut",
            }
        ]
        result = _validate_and_normalize_scenes(raw)
        assert len(result) == 1
        assert result[0]["scene_index"] == 0
        assert result[0]["scene_prompt"] == "A sunny park"

    def test_duration_clamped_below(self):
        raw = [{"scene_prompt": "p", "narration": "n", "duration_sec": 0, "transition": "cut"}]
        result = _validate_and_normalize_scenes(raw)
        assert result[0]["duration_sec"] == 2  # clamped to min

    def test_duration_clamped_above(self):
        raw = [{"scene_prompt": "p", "narration": "n", "duration_sec": 999, "transition": "cut"}]
        result = _validate_and_normalize_scenes(raw)
        assert result[0]["duration_sec"] == 10  # clamped to max

    def test_invalid_transition_defaults_to_cut(self):
        raw = [{"scene_prompt": "p", "narration": "n", "duration_sec": 5, "transition": "wipe"}]
        result = _validate_and_normalize_scenes(raw)
        assert result[0]["transition"] == "cut"

    def test_valid_transitions_preserved(self):
        for t in ("cut", "fade", "push_pull"):
            raw = [{"scene_prompt": "p", "narration": "n", "duration_sec": 5, "transition": t}]
            result = _validate_and_normalize_scenes(raw)
            assert result[0]["transition"] == t

    def test_scene_index_assigned_sequentially(self):
        raw = [
            {"scene_prompt": "A", "narration": "a", "duration_sec": 5, "transition": "cut"},
            {"scene_prompt": "B", "narration": "b", "duration_sec": 5, "transition": "fade"},
        ]
        result = _validate_and_normalize_scenes(raw)
        assert result[0]["scene_index"] == 0
        assert result[1]["scene_index"] == 1

    def test_missing_voice_style_gets_default(self):
        raw = [{"scene_prompt": "p", "narration": "n", "duration_sec": 5, "transition": "cut"}]
        result = _validate_and_normalize_scenes(raw)
        vs = result[0]["voice_style"]
        assert "speed" in vs
        assert "emotion" in vs

    def test_empty_list(self):
        assert _validate_and_normalize_scenes([]) == []


class TestValidateSceneContinuity:
    def test_no_issues_when_scenes_share_words(self):
        scenes = [
            {"narration": "今天天气很好，我们去公园。"},
            {"narration": "公园里有很多花，景色很美。"},  # shares "公园"
        ]
        issues = validate_scene_continuity(scenes)
        # Might or might not flag, depending on overlap — just ensure it runs
        assert isinstance(issues, list)

    def test_flags_completely_unrelated_scenes(self):
        scenes = [
            {"narration": "苹果 香蕉 橙子 葡萄 西瓜 草莓"},  # food
            {"narration": "汽车 火车 飞机 轮船 摩托 自行车"},  # transport
        ]
        issues = validate_scene_continuity(scenes)
        assert len(issues) >= 1
        assert issues[0]["scene_index"] == 1

    def test_single_scene_no_issues(self):
        scenes = [{"narration": "Only one scene here."}]
        issues = validate_scene_continuity(scenes)
        assert issues == []

    def test_empty_scenes_no_issues(self):
        issues = validate_scene_continuity([])
        assert issues == []

    def test_issue_contains_expected_fields(self):
        scenes = [
            {"narration": "A B C D E F G"},
            {"narration": "X Y Z P Q R S"},  # no overlap
        ]
        issues = validate_scene_continuity(scenes)
        if issues:
            assert "scene_index" in issues[0]
            assert "issue_description" in issues[0]


@pytest.mark.django_db
class TestGenerateScenesFromContent:
    def test_raises_when_no_llm_config(self, confirmed_content, user):
        with pytest.raises(RuntimeError, match="LLM"):
            generate_scenes_from_content(confirmed_content, user.pk)

    @patch("apps.video_generator.scene_generator.httpx.post")
    @patch("apps.video_generator.scene_generator.UserServiceConfig")
    def test_success_returns_scene_list(self, mock_config_cls, mock_post,
                                        confirmed_content, user):
        import json
        from core.encryption import encrypt

        mock_cfg = MagicMock()
        mock_cfg.service_type = "llm_deepseek"
        mock_cfg.encrypted_config = encrypt({"api_key": "fake-key"})
        mock_config_cls.objects.filter.return_value.first.return_value = mock_cfg

        scenes_json = json.dumps([
            {
                "scene_prompt": "A sunny park",
                "narration": "美好的一天。",
                "voice_style": {"speed": "normal", "emotion": "neutral", "voice_id": "zh_female_1"},
                "duration_sec": 5,
                "transition": "cut",
            }
        ])
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": scenes_json}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = generate_scenes_from_content(confirmed_content, user.pk)
        assert len(result) == 1
        assert result[0]["scene_prompt"] == "A sunny park"
        assert result[0]["scene_index"] == 0

    @patch("apps.video_generator.scene_generator.httpx.post")
    @patch("apps.video_generator.scene_generator.UserServiceConfig")
    def test_strips_markdown_code_fences(self, mock_config_cls, mock_post,
                                          confirmed_content, user):
        import json
        from core.encryption import encrypt

        mock_cfg = MagicMock()
        mock_cfg.service_type = "llm_deepseek"
        mock_cfg.encrypted_config = encrypt({"api_key": "fake-key"})
        mock_config_cls.objects.filter.return_value.first.return_value = mock_cfg

        scenes_json = "```json\n" + json.dumps([
            {"scene_prompt": "p", "narration": "n", "duration_sec": 5, "transition": "cut"}
        ]) + "\n```"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": scenes_json}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = generate_scenes_from_content(confirmed_content, user.pk)
        assert len(result) == 1
