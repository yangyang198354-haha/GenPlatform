"""Celery tasks for async content publishing."""
import asyncio
import logging
from django.utils import timezone
from celery import shared_task

from core.encryption import decrypt
from .models import PublishTask
from .publishers import get_publisher
from apps.notifications.service import push_notification

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def execute_publish_task(self, task_id: int) -> None:
    """Execute a single publish task: call platform API and update status."""
    try:
        task = PublishTask.objects.select_related("content", "platform_account").get(pk=task_id)
    except PublishTask.DoesNotExist:
        logger.error("PublishTask %d not found", task_id)
        return

    task.status = "publishing"
    task.save(update_fields=["status"])

    try:
        credentials = decrypt(bytes(task.platform_account.encrypted_credentials))
        publisher = get_publisher(task.platform_account.platform)

        result = asyncio.run(
            publisher.publish(
                title=task.content.title,
                body=task.content.body,
                credentials=credentials,
            )
        )

        if result.success:
            task.status = "success"
            task.published_at = timezone.now()
            task.platform_post_id = result.post_id
            task.platform_post_url = result.post_url
        else:
            task.status = "failed"
            task.error_message = result.error or "未知错误"
            task.retry_count += 1

        task.save(update_fields=[
            "status", "published_at", "platform_post_id",
            "platform_post_url", "error_message", "retry_count",
        ])

        # Push WebSocket notification
        asyncio.run(push_notification(
            user_id=task.user_id,
            event_type="publish_status",
            payload={
                "task_id": task_id,
                "platform": task.platform_account.platform,
                "status": task.status,
                "post_url": task.platform_post_url,
            },
        ))

    except Exception as exc:
        logger.exception("Publish task %d failed", task_id)
        PublishTask.objects.filter(pk=task_id).update(
            status="failed", error_message=str(exc)
        )
        raise self.retry(exc=exc)
