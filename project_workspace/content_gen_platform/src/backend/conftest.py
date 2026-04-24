"""Global pytest fixtures shared across all test modules."""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt
from apps.content.models import Content
from apps.publisher.models import PlatformAccount, PublishTask
from apps.video_generator.models import VideoProject, Scene
from apps.media_library.models import MediaItem
from apps.image_generator.models import ImageGenerationRequest

User = get_user_model()


@pytest.fixture(autouse=True)
def disable_throttling(monkeypatch):
    """Disable all throttling for every test.

    ``test.py`` sets ``DEFAULT_THROTTLE_CLASSES = []``, which disables the
    *global* DRF throttle.  However, views that declare their own
    ``throttle_classes`` at the class level — currently ``MediaItemListView``
    (scope "media_list", 300/min) and ``DocumentDetailView`` (scope
    "document_status", 120/min) — are not affected by that setting; they
    continue to write per-user counters into the shared LocMemCache.

    Because LocMemCache is process-local and does *not* participate in
    database transactions, those counters survive test teardown and can
    accumulate if the same user PK is reused across tests (e.g. between
    separate local test-session runs).

    This fixture has two complementary effects:
      1. It patches the view-level ``throttle_classes`` to ``[]``, so the
         throttle check is bypassed entirely for both views.
      2. It clears the cache before each test as a belt-and-suspenders guard
         against any other cached state interfering with throttle logic.
    """
    # Belt-and-suspenders: clear any leftover throttle counters from previous
    # test runs (or from the same session if PKs happen to be reused).
    cache.clear()

    # Patch view-level throttle_classes so they don't bypass the global [] override.
    # Use try/except for knowledge_base in case the app is excluded from
    # INSTALLED_APPS (e.g. local SQLite runs via local_test.py that strip
    # apps.knowledge_base because pgvector is unavailable on SQLite).
    monkeypatch.setattr(
        "apps.media_library.views.MediaItemListView.throttle_classes", []
    )
    try:
        monkeypatch.setattr(
            "apps.knowledge_base.views.DocumentDetailView.throttle_classes", []
        )
    except Exception:
        pass  # knowledge_base may be unavailable in SQLite-only local runs
    yield


# ── Users ──────────────────────────────────────────────────────────────────

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="TestPass123!",
    )


@pytest.fixture
def user2(db):
    return User.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="TestPass123!",
    )


# ── API clients ────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(user):
    """Return (APIClient, user) authenticated as `user`."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client, user


@pytest.fixture
def auth_client2(user2):
    """Return (APIClient, user2) authenticated as `user2`."""
    client = APIClient()
    refresh = RefreshToken.for_user(user2)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client, user2


# ── Content helpers ────────────────────────────────────────────────────────

@pytest.fixture
def draft_content(user):
    return Content.objects.create(
        user=user,
        title="Test Title",
        body="Test body text for content.",
        platform_type="general",
        style="professional",
        status="draft",
    )


@pytest.fixture
def confirmed_content(user):
    from django.utils import timezone
    return Content.objects.create(
        user=user,
        title="Confirmed Title",
        body="Confirmed body text.",
        platform_type="weibo",
        style="casual",
        status="confirmed",
        confirmed_at=timezone.now(),
    )


# ── Publisher helpers ──────────────────────────────────────────────────────

@pytest.fixture
def platform_account(user):
    return PlatformAccount.objects.create(
        user=user,
        platform="weibo",
        display_name="My Weibo",
        auth_type="api_key",
        encrypted_credentials=encrypt({"token": "fake-token-123"}),
        is_active=True,
    )


@pytest.fixture
def publish_task(user, confirmed_content, platform_account):
    return PublishTask.objects.create(
        user=user,
        content=confirmed_content,
        platform_account=platform_account,
        status="pending",
    )


# ── Video helpers ──────────────────────────────────────────────────────────

@pytest.fixture
def video_project(user, confirmed_content):
    return VideoProject.objects.create(
        user=user,
        content=confirmed_content,
        status="draft",
    )


@pytest.fixture
def scene(video_project):
    return Scene.objects.create(
        video_project=video_project,
        scene_index=0,
        scene_prompt="A person walking in a park, wide shot, golden hour.",
        narration="这是一个美好的早晨。",
        voice_style={"speed": "normal", "emotion": "neutral", "voice_id": "zh_female_1"},
        duration_sec=5,
        transition="cut",
    )


# ── Media Library helpers ──────────────────────────────────────────────────

@pytest.fixture
def media_item(user):
    from django.core.files.base import ContentFile
    item = MediaItem(
        owner=user,
        media_type="image",
        source="uploaded",
        title="Test Media Item",
        file_size=1024,
    )
    item.file.save("fixture_test.jpg", ContentFile(b"fake-jpg-content"), save=True)
    return item


@pytest.fixture
def ai_media_item(user):
    from django.core.files.base import ContentFile
    item = MediaItem(
        owner=user,
        media_type="image",
        source="ai_generated",
        title="AI Generated Image",
        file_size=2048,
    )
    item.file.save("ai_fixture.jpg", ContentFile(b"fake-ai-content"), save=True)
    return item


# ── Image Generator helpers ────────────────────────────────────────────────

@pytest.fixture
def image_request(user):
    return ImageGenerationRequest.objects.create(
        user=user,
        prompt="A serene lake at dawn",
        status="pending",
    )


@pytest.fixture
def completed_image_request(user, ai_media_item):
    return ImageGenerationRequest.objects.create(
        user=user,
        prompt="A mountain at golden hour",
        status="completed",
        jimeng_task_id="task_abc123",
        result_image_url="https://example.com/result.jpg",
        media_item=ai_media_item,
        progress=100,
    )
