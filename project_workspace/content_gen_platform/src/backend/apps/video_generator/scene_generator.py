"""Scene generation: convert confirmed content into structured storyboard scenes."""
import json
import logging
from typing import List

import httpx
from django.conf import settings

from apps.content.models import Content
from core.encryption import decrypt
from apps.settings_vault.models import UserServiceConfig

logger = logging.getLogger(__name__)

SCENE_GENERATION_PROMPT = """你是一名专业的视频分镜脚本创作师。

请将以下文案拆解为适合短视频的分镜脚本。每个分镜时长 3-8 秒，整体视频不超过 60 秒。

输出格式必须是严格的 JSON 数组，每个元素包含以下字段：
- scene_prompt: 画面描述（包含：主体、场景/背景、视觉风格、光线、镜头运动，用英文描述以提升 AI 生成质量）
- narration: 该分镜的中文配音文案（简短，与画面同步）
- voice_style: {"speed": "normal|slow|fast", "emotion": "neutral|warm|excited", "voice_id": "zh_female_1"}
- duration_sec: 时长（3-8 之间的整数）
- transition: "cut"|"fade"|"push_pull"

注意：
1. 相邻分镜的主体和场景必须保持逻辑连贯，不能突兀跳跃
2. scene_prompt 要具体可执行，避免模糊描述
3. 首个分镜要有吸引力的开场画面

文案内容：
{content_body}

请直接输出 JSON 数组，不要有任何其他文字。
"""


def generate_scenes_from_content(content: Content, user_id: int) -> List[dict]:
    """
    Call LLM to generate structured storyboard scenes from content body.
    Returns a list of scene dicts matching the Scene model fields.
    """
    try:
        llm_cfg = UserServiceConfig.objects.filter(
            user_id=user_id,
            service_type__startswith="llm_",
            is_active=True,
        ).first()
        if not llm_cfg:
            raise RuntimeError("未配置 LLM API Key，无法自动生成分镜")

        config = decrypt(bytes(llm_cfg.encrypted_config))
        api_key = config.get("api_key", "")
        service_type = llm_cfg.service_type

        prompt = SCENE_GENERATION_PROMPT.replace("{content_body}", content.body)

        if service_type == "llm_deepseek":
            base_url = "https://api.deepseek.com/v1"
            model = config.get("model_name", "deepseek-chat")
        else:
            base_url = "https://ark.cn-beijing.volces.com/api/v3"
            model = config.get("model_name", "doubao-pro-4k")

        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是专业的视频分镜脚本创作师，只输出 JSON，不输出其他文字。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 3000,
            },
            timeout=60,
        )
        response.raise_for_status()
        raw_json = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if raw_json.startswith("```"):
            raw_json = raw_json.split("\n", 1)[1].rsplit("```", 1)[0]

        scenes_data = json.loads(raw_json)
        return _validate_and_normalize_scenes(scenes_data)

    except Exception as e:
        logger.exception("Scene generation failed for content %d", content.pk)
        raise RuntimeError(f"分镜生成失败：{e}") from e


def _validate_and_normalize_scenes(scenes: list) -> List[dict]:
    """Validate and clamp scene fields to allowed ranges."""
    validated = []
    for i, scene in enumerate(scenes):
        validated.append({
            "scene_index": i,
            "scene_prompt": str(scene.get("scene_prompt", "")),
            "narration": str(scene.get("narration", "")),
            "voice_style": scene.get("voice_style", {"speed": "normal", "emotion": "neutral", "voice_id": "zh_female_1"}),
            "duration_sec": max(2, min(10, int(scene.get("duration_sec", 5)))),
            "transition": scene.get("transition", "cut") if scene.get("transition") in ("cut", "fade", "push_pull") else "cut",
        })
    return validated


def validate_scene_continuity(scenes: List[dict]) -> List[dict]:
    """
    Check adjacent scenes for logical continuity.
    Returns a list of issue dicts: {scene_index, issue_description}.
    """
    issues = []
    for i in range(1, len(scenes)):
        prev = scenes[i - 1]
        curr = scenes[i]
        # Simple heuristic: if narration content has zero word overlap, flag it
        prev_words = set(prev.get("narration", "").replace("，", " ").replace("。", " ").split())
        curr_words = set(curr.get("narration", "").replace("，", " ").replace("。", " ").split())
        if len(prev_words) > 0 and len(curr_words) > 0:
            overlap = len(prev_words & curr_words) / min(len(prev_words), len(curr_words))
            if overlap < 0.05 and len(prev_words) > 3:
                issues.append({
                    "scene_index": i,
                    "issue_description": f"第{i}和第{i+1}个分镜的配音内容似乎缺乏连贯性，请检查叙事逻辑。",
                })
    return issues
