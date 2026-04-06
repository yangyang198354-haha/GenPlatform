"""Celery tasks for video generation pipeline."""
import asyncio
import logging
import time

from celery import shared_task
from django.conf import settings

from core.encryption import decrypt
from apps.settings_vault.models import UserServiceConfig
from apps.notifications.service import push_notification
from .models import VideoProject, Scene
from .jimeng_client import JimengAPIClient

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 10
MAX_POLL_ATTEMPTS = 60  # 10 minutes max


@shared_task(bind=True, max_retries=1)
def generate_video_task(self, project_id: int) -> None:
    """
    Full video generation pipeline:
    1. Load scene data from DB
    2. Submit to Jimeng API
    3. Poll for completion
    4. Store clip URLs back to scenes
    5. Notify user
    """
    try:
        project = VideoProject.objects.prefetch_related("scenes").get(pk=project_id)
        scenes = list(project.scenes.filter(is_deleted=False).order_by("scene_index"))

        if not scenes:
            project.status = "failed"
            project.error_message = "没有可生成的分镜"
            project.save(update_fields=["status", "error_message"])
            return

        # Get Jimeng credentials
        try:
            jimeng_cfg = UserServiceConfig.objects.get(
                user_id=project.user_id, service_type="jimeng", is_active=True
            )
            config = decrypt(bytes(jimeng_cfg.encrypted_config))
            client = JimengAPIClient(
                access_key=config["access_key"],
                secret_key=config["secret_key"],
            )
        except UserServiceConfig.DoesNotExist:
            project.status = "failed"
            project.error_message = "未配置即梦 API Key"
            project.save(update_fields=["status", "error_message"])
            asyncio.run(push_notification(
                project.user_id, "video_failed",
                {"project_id": project_id, "error": "未配置即梦 API Key"}
            ))
            return

        scene_data = [
            {
                "scene_index": s.scene_index,
                "scene_prompt": s.scene_prompt,
                "narration": s.narration,
                "duration_sec": s.duration_sec,
                "transition": s.transition,
            }
            for s in scenes
        ]

        project.status = "generating"
        project.save(update_fields=["status"])

        # Submit task
        task_id = asyncio.run(client.submit_task(scene_data))
        project.jimeng_task_id = task_id
        project.save(update_fields=["jimeng_task_id"])

        # Poll for completion
        for attempt in range(MAX_POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL_SEC)
            status = asyncio.run(client.poll_status(task_id))

            asyncio.run(push_notification(
                project.user_id, "video_progress",
                {"project_id": project_id, "progress": status.progress}
            ))

            if status.status == "completed":
                # Store clip URLs back to scenes
                for i, url in enumerate(status.clip_urls):
                    if i < len(scenes):
                        scenes[i].jimeng_clip_url = url
                        scenes[i].save(update_fields=["jimeng_clip_url"])

                project.status = "completed"
                project.save(update_fields=["status"])
                asyncio.run(push_notification(
                    project.user_id, "video_completed",
                    {"project_id": project_id, "clip_count": len(status.clip_urls)}
                ))
                return

            if status.status == "failed":
                raise RuntimeError(f"Jimeng 生成失败: {status.error}")

        raise RuntimeError("视频生成超时（超过10分钟）")

    except Exception as exc:
        logger.exception("Video generation failed for project %d", project_id)
        VideoProject.objects.filter(pk=project_id).update(
            status="failed", error_message=str(exc)
        )
        asyncio.run(push_notification(
            VideoProject.objects.get(pk=project_id).user_id,
            "video_failed",
            {"project_id": project_id, "error": str(exc)},
        ))
