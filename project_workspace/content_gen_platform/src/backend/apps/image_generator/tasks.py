"""Celery tasks for image generation pipeline."""
import asyncio
import logging
import os
import time

from celery import shared_task
from django.contrib.auth import get_user_model

from core.encryption import decrypt
from apps.settings_vault.models import UserServiceConfig
from apps.notifications.service import push_notification_sync
from apps.media_library.service import create_media_item_from_url
from .models import ImageGenerationRequest
from .jimeng_image_client import JimengImageClient

logger = logging.getLogger(__name__)
User = get_user_model()

POLL_INTERVAL_SEC = 10
MAX_POLL_ATTEMPTS = 60  # 10 minutes max


@shared_task(bind=True, max_retries=1)
def generate_image_task(self, request_id: int) -> None:
    """
    Async image generation pipeline:
    1. Load ImageGenerationRequest from DB
    2. Fetch Jimeng credentials from settings_vault
    3. Submit image generation task to Jimeng CVProcess
    4. Poll for completion
    5. Download result and create MediaItem
    6. Notify user via WebSocket
    """
    try:
        req = ImageGenerationRequest.objects.select_related("user").get(pk=request_id)
        user = req.user

        # Get Jimeng credentials
        try:
            jimeng_cfg = UserServiceConfig.objects.get(
                user_id=user.pk, service_type="jimeng", is_active=True
            )
            config = decrypt(bytes(jimeng_cfg.encrypted_config))
            client = JimengImageClient(
                access_key=config["access_key"],
                secret_key=config["secret_key"],
            )
        except UserServiceConfig.DoesNotExist:
            req.status = "failed"
            req.error_message = "未配置即梦 API Key"
            req.save(update_fields=["status", "error_message"])
            push_notification_sync(
                user.pk, "image_failed",
                {"request_id": request_id, "error": "未配置即梦 API Key"},
            )
            return

        req.status = "processing"
        req.save(update_fields=["status"])

        # Submit task
        ref_image_path = req.ref_image_path if req.ref_image_path else None
        task_id = asyncio.run(
            client.submit_image_task(prompt=req.prompt, ref_image_path=ref_image_path)
        )
        req.jimeng_task_id = task_id
        req.save(update_fields=["jimeng_task_id"])

        # Clean up temp reference image
        if ref_image_path and os.path.exists(ref_image_path):
            try:
                os.remove(ref_image_path)
                # Also try to remove parent temp directory if empty
                parent = os.path.dirname(ref_image_path)
                if parent and not os.listdir(parent):
                    os.rmdir(parent)
            except OSError as exc:
                logger.warning("Could not clean up ref image %s: %s", ref_image_path, exc)
        req.ref_image_path = ""
        req.save(update_fields=["ref_image_path"])

        # Poll for completion
        for attempt in range(MAX_POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL_SEC)
            task_status = asyncio.run(client.poll_image_status(task_id))

            # Update progress
            req.progress = task_status.progress
            req.save(update_fields=["progress"])
            push_notification_sync(
                user.pk, "image_progress",
                {"request_id": request_id, "progress": task_status.progress},
            )

            if task_status.status == "completed":
                if not task_status.image_urls:
                    raise RuntimeError("即梦返回完成但无图片 URL")

                result_url = task_status.image_urls[0]
                req.result_image_url = result_url
                req.status = "completed"
                req.progress = 100
                req.save(update_fields=["result_image_url", "status", "progress"])

                # Create MediaItem
                media_item = create_media_item_from_url(
                    user=user,
                    url=result_url,
                    media_type="image",
                    source="ai_generated",
                    title=f"AI图片_{req.prompt[:30]}",
                )
                req.media_item_id = media_item.pk
                req.save(update_fields=["media_item"])

                push_notification_sync(
                    user.pk, "image_completed",
                    {
                        "request_id": request_id,
                        "media_item_id": media_item.pk,
                        "file_url": media_item.file.url,
                    },
                )
                return

            if task_status.status == "failed":
                raise RuntimeError(f"即梦图片生成失败: {task_status.error}")

        raise RuntimeError("图片生成超时（超过10分钟）")

    except Exception as exc:
        logger.exception("Image generation failed for request %d", request_id)
        ImageGenerationRequest.objects.filter(pk=request_id).update(
            status="failed", error_message=str(exc)
        )
        try:
            req_obj = ImageGenerationRequest.objects.get(pk=request_id)
            push_notification_sync(
                req_obj.user_id, "image_failed",
                {"request_id": request_id, "error": str(exc)},
            )
        except Exception:
            pass
