"""Integration tests for Image Generator API views."""
import io
import json
import pytest
from unittest.mock import patch, MagicMock
from rest_framework import status
from apps.image_generator.models import ImageGenerationRequest
from apps.media_library.models import MediaItem


@pytest.mark.django_db
class TestImageGenerationSubmitView:

    def test_submit_valid_prompt(self, auth_client):
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "A beautiful mountain"},
                format="multipart",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data["status"] == "pending"
        assert resp.data["prompt"] == "A beautiful mountain"
        assert ImageGenerationRequest.objects.filter(user=user).count() == 1

    def test_submit_empty_prompt_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.post("/api/v1/image/generate/", {"prompt": ""}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "提示词" in resp.data["error"]

    def test_submit_prompt_too_long_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": "x" * 501},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_submit_with_valid_ref_image(self, auth_client):
        client, user = auth_client
        fake_img = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)  # minimal JPEG magic bytes
        fake_img.name = "ref.jpg"
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "test", "ref_image": fake_img},
                format="multipart",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED

    def test_submit_requires_auth(self, api_client):
        resp = api_client.post("/api/v1/image/generate/", {"prompt": "test"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_submit_triggers_celery_task(self, auth_client):
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            client.post(
                "/api/v1/image/generate/",
                {"prompt": "A forest"},
                format="multipart",
            )
            mock_task.delay.assert_called_once()


@pytest.mark.django_db
class TestImageGenerationStatusView:

    def test_get_status_own_request(self, auth_client):
        client, user = auth_client
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="test", status="processing", progress=50
        )
        resp = client.get(f"/api/v1/image/generate/{req.pk}/status/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "processing"
        assert resp.data["progress"] == 50

    def test_get_status_other_user_returns_404(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2
        req = ImageGenerationRequest.objects.create(user=user2, prompt="other")
        resp = client.get(f"/api/v1/image/generate/{req.pk}/status/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_status_nonexistent_returns_404(self, auth_client):
        client, _ = auth_client
        resp = client.get("/api/v1/image/generate/99999/status/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_status_includes_media_item_id_when_complete(self, auth_client):
        from django.core.files.base import ContentFile
        client, user = auth_client
        media_item = MediaItem(owner=user, media_type="image", source="ai_generated", title="t")
        media_item.file.save("x.jpg", ContentFile(b"d"), save=True)
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="done", status="completed",
            progress=100, media_item=media_item
        )
        resp = client.get(f"/api/v1/image/generate/{req.pk}/status/")
        assert resp.data["media_item_id"] == media_item.pk


@pytest.mark.django_db
class TestImageGenerationListView:

    def test_history_returns_own_requests(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2
        ImageGenerationRequest.objects.create(user=user, prompt="mine")
        ImageGenerationRequest.objects.create(user=user2, prompt="theirs")
        resp = client.get("/api/v1/image/history/")
        assert resp.status_code == status.HTTP_200_OK
        prompts = [r["prompt"] for r in resp.data]
        assert "mine" in prompts
        assert "theirs" not in prompts
