"""Unit tests for settings_vault.views — ServiceConfigListView / ServiceConfigDetailView."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt, decrypt
from apps.settings_vault.models import UserServiceConfig

User = get_user_model()

SERVICES_LIST_URL = "/api/v1/settings/services/"


def _url_detail(service_type):
    return f"/api/v1/settings/services/{service_type}/"


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ── test cases ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestServiceConfigListView:

    def test_get_settings_requires_auth(self, api_client):
        """Unauthenticated GET /settings/services/ must return 401."""
        resp = api_client.get(SERVICES_LIST_URL)
        assert resp.status_code == 401

    def test_list_services_returns_all_service_types(self, user, db):
        """Authenticated GET must return all SERVICE_CHOICES, at minimum the unconfigured ones."""
        client = _auth_client(user)
        resp = client.get(SERVICES_LIST_URL)
        assert resp.status_code == 200
        service_types = {item["service_type"] for item in resp.data}
        # All declared service choices must appear in the response
        for choice_value, _ in UserServiceConfig.SERVICE_CHOICES:
            assert choice_value in service_types, (
                f"service_type '{choice_value}' missing from list response"
            )

    def test_list_services_shows_configured_entry(self, user, db):
        """A previously saved config must appear as is_configured=True."""
        UserServiceConfig.objects.create(
            user=user,
            service_type="llm_deepseek",
            encrypted_config=encrypt({"api_key": "sk-test"}),
            is_active=True,
        )
        client = _auth_client(user)
        resp = client.get(SERVICES_LIST_URL)
        assert resp.status_code == 200
        deepseek_entry = next(
            (item for item in resp.data if item["service_type"] == "llm_deepseek"), None
        )
        assert deepseek_entry is not None
        assert deepseek_entry["is_configured"] is True


@pytest.mark.django_db
class TestServiceConfigDetailView:

    def test_save_llm_config_creates_encrypted_record(self, user, db):
        """PUT /settings/services/llm_deepseek/ must create an encrypted UserServiceConfig row."""
        client = _auth_client(user)
        resp = client.put(
            _url_detail("llm_deepseek"),
            {"api_key": "sk-real-key-test"},
            format="json",
        )
        assert resp.status_code == 200
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        assert cfg.is_active is True
        # Decrypt and verify the stored value
        stored = decrypt(bytes(cfg.encrypted_config))
        assert stored["api_key"] == "sk-real-key-test"

    def test_save_llm_config_requires_auth(self, api_client):
        """PUT without auth must return 401."""
        resp = api_client.put(
            _url_detail("llm_deepseek"),
            {"api_key": "sk-test"},
            format="json",
        )
        assert resp.status_code == 401

    def test_save_invalid_service_type_returns_400(self, user, db):
        """PUT with an unrecognised service_type must return 400."""
        client = _auth_client(user)
        resp = client.put(
            _url_detail("llm_nonexistent"),
            {"api_key": "sk-test"},
            format="json",
        )
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_save_missing_required_key_returns_400(self, user, db):
        """PUT llm_deepseek without api_key must return 400."""
        client = _auth_client(user)
        resp = client.put(
            _url_detail("llm_deepseek"),
            {},
            format="json",
        )
        assert resp.status_code == 400
        assert "error" in resp.data
