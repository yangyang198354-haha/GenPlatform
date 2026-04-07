"""Unit tests for the User model."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = User.objects.create_user(
            username="alice", email="alice@example.com", password="Secure123!"
        )
        assert user.pk is not None
        assert user.email == "alice@example.com"
        assert user.check_password("Secure123!")

    def test_username_field_is_email(self):
        assert User.USERNAME_FIELD == "email"

    def test_default_storage_quota(self):
        user = User.objects.create_user(
            username="bob", email="bob@example.com", password="Secure123!"
        )
        assert user.storage_quota_bytes == 2 * 1024**3  # 2 GB

    def test_default_used_storage(self):
        user = User.objects.create_user(
            username="carol", email="carol@example.com", password="Secure123!"
        )
        assert user.used_storage_bytes == 0

    def test_has_storage_quota_sufficient(self, user):
        assert user.has_storage_quota(1024) is True

    def test_has_storage_quota_exact_limit(self, user):
        # Exactly at limit should be allowed
        assert user.has_storage_quota(user.storage_quota_bytes) is True

    def test_has_storage_quota_insufficient(self, user):
        # Artificially fill quota
        user.used_storage_bytes = user.storage_quota_bytes
        user.save()
        assert user.has_storage_quota(1) is False

    def test_consume_storage(self, user):
        user.consume_storage(1024)
        user.refresh_from_db()
        assert user.used_storage_bytes == 1024

    def test_consume_storage_accumulates(self, user):
        user.consume_storage(500)
        user.consume_storage(300)
        user.refresh_from_db()
        assert user.used_storage_bytes == 800

    def test_release_storage(self, user):
        user.used_storage_bytes = 2048
        user.save()
        user.release_storage(1024)
        user.refresh_from_db()
        assert user.used_storage_bytes == 1024

    def test_has_quota_after_consume(self, user):
        large = user.storage_quota_bytes - 100
        user.consume_storage(large)
        user.refresh_from_db()
        # 100 bytes left — should accept 100 but not 101
        assert user.has_storage_quota(100) is True
        assert user.has_storage_quota(101) is False
