"""Unit tests for ImageGenerationRequest model."""
import pytest
from apps.image_generator.models import ImageGenerationRequest


@pytest.mark.django_db
class TestImageGenerationRequestModel:

    def test_create_request(self, user):
        req = ImageGenerationRequest.objects.create(
            user=user,
            prompt="A sunset over the ocean",
            status="pending",
        )
        assert req.pk is not None
        assert req.status == "pending"
        assert req.progress == 0
        assert req.jimeng_task_id == ""
        assert req.media_item is None

    def test_default_status_is_pending(self, user):
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="test"
        )
        assert req.status == "pending"

    def test_str_representation(self, user):
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="test prompt", status="processing"
        )
        s = str(req)
        assert str(req.pk) in s
        assert "processing" in s

    def test_ordering_newest_first(self, user):
        r1 = ImageGenerationRequest.objects.create(user=user, prompt="first")
        r2 = ImageGenerationRequest.objects.create(user=user, prompt="second")
        qs = list(ImageGenerationRequest.objects.filter(user=user).order_by("-pk"))
        assert qs[0].pk == r2.pk

    def test_media_item_fk_nullable(self, user):
        req = ImageGenerationRequest.objects.create(user=user, prompt="test")
        assert req.media_item is None
