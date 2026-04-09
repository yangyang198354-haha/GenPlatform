"""Unit tests for image generation Celery tasks."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from apps.image_generator.models import ImageGenerationRequest
from apps.image_generator.jimeng_image_client import ImageTaskStatus
from apps.media_library.models import MediaItem
from core.encryption import encrypt
from apps.settings_vault.models import UserServiceConfig


def _make_jimeng_config(user):
    """Create an active jimeng config for user."""
    cfg = UserServiceConfig.objects.create(
        user=user,
        service_type="jimeng",
        encrypted_config=encrypt({"access_key": "ak", "secret_key": "sk"}),
        is_active=True,
    )
    return cfg


@pytest.mark.django_db
class TestGenerateImageTask:

    def test_task_fails_when_no_jimeng_config(self, user):
        from apps.image_generator.tasks import generate_image_task
        req = ImageGenerationRequest.objects.create(user=user, prompt="test")

        with patch("apps.image_generator.tasks.push_notification_sync"):
            generate_image_task(req.pk)

        req.refresh_from_db()
        assert req.status == "failed"
        assert "API Key" in req.error_message

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.tasks.asyncio.run")
    def test_task_completes_successfully(self, mock_run, mock_create_media, mock_push, user):
        _make_jimeng_config(user)
        req = ImageGenerationRequest.objects.create(user=user, prompt="forest")

        completed_status = ImageTaskStatus(
            task_id="task123",
            status="completed",
            progress=100,
            image_urls=["https://example.com/result.jpg"],
        )
        # asyncio.run call 1: submit_image_task -> returns task_id
        # asyncio.run call 2+: poll_image_status -> returns completed
        mock_run.side_effect = ["task123", completed_status]

        from django.core.files.base import ContentFile
        real_media = MediaItem(owner=user, media_type="image", source="ai_generated",
                               title="result", file_size=100)
        real_media.file.save("test_result.jpg", ContentFile(b"fake"), save=True)
        mock_create_media.return_value = real_media

        from apps.image_generator.tasks import generate_image_task
        generate_image_task(req.pk)

        req.refresh_from_db()
        assert req.status == "completed"
        assert req.jimeng_task_id == "task123"
        assert req.media_item_id == real_media.pk

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.asyncio.run")
    def test_task_fails_on_jimeng_error(self, mock_run, mock_push, user):
        _make_jimeng_config(user)
        req = ImageGenerationRequest.objects.create(user=user, prompt="test")

        failed_status = ImageTaskStatus(
            task_id="task_err",
            status="failed",
            progress=0,
            error="内容违规",
        )
        mock_run.side_effect = ["task_err", failed_status]

        from apps.image_generator.tasks import generate_image_task
        generate_image_task(req.pk)

        req.refresh_from_db()
        assert req.status == "failed"
        assert "内容违规" in req.error_message
