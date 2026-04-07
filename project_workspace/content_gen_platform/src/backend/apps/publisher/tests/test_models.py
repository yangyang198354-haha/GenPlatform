"""Unit tests for publisher models."""
import pytest
from apps.publisher.models import PlatformAccount, PublishTask
from core.encryption import encrypt


@pytest.mark.django_db
class TestPlatformAccountModel:
    def test_create_account(self, user):
        account = PlatformAccount.objects.create(
            user=user,
            platform="weibo",
            display_name="My Weibo",
            auth_type="api_key",
            encrypted_credentials=encrypt({"token": "abc123"}),
            is_active=True,
        )
        assert account.pk is not None
        assert account.is_active is True

    def test_str(self, user):
        account = PlatformAccount.objects.create(
            user=user,
            platform="weibo",
            display_name="My Weibo",
            auth_type="api_key",
            encrypted_credentials=encrypt({"token": "abc"}),
        )
        s = str(account)
        assert "weibo" in s
        assert "My Weibo" in s


@pytest.mark.django_db
class TestPublishTaskModel:
    def test_default_status_is_pending(self, user, confirmed_content, platform_account):
        task = PublishTask.objects.create(
            user=user,
            content=confirmed_content,
            platform_account=platform_account,
        )
        assert task.status == "pending"

    def test_retry_count_default_zero(self, user, confirmed_content, platform_account):
        task = PublishTask.objects.create(
            user=user,
            content=confirmed_content,
            platform_account=platform_account,
        )
        assert task.retry_count == 0

    def test_ordering_newest_first(self, user, confirmed_content, platform_account):
        t1 = PublishTask.objects.create(user=user, content=confirmed_content,
                                        platform_account=platform_account)
        t2 = PublishTask.objects.create(user=user, content=confirmed_content,
                                        platform_account=platform_account)
        tasks = list(PublishTask.objects.filter(user=user))
        assert tasks[0].pk == t2.pk
