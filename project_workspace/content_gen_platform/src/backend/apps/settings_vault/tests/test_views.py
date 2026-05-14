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


@pytest.mark.django_db
class TestJimengV12Cleanup:
    """
    v1.2 即梦清理验证测试（AC-08-2, AC-08-4）。

    验证：
    - jimeng 枚举值在 SERVICE_CHOICES 中仍存在（DB 兼容，不删历史数据）
    - 历史 jimeng 记录可以通过 DB 正常创建和查询（历史数据保留）
    - 前端 API 不提供 jimeng 图片专属路由（AC-08-4 — 在 URL 层验证）
    """

    def test_jimeng_service_type_still_in_service_choices_canary(self):
        """
        【Canary 守卫 AC-08-2】jimeng 仍在 SERVICE_CHOICES 中。

        若此测试失败，说明有人删除了 jimeng 枚举，可能导致历史数据迁移问题。
        """
        choices = dict(UserServiceConfig.SERVICE_CHOICES)
        assert "jimeng" in choices, (
            "jimeng 必须保留在 SERVICE_CHOICES 中以兼容历史数据（AC-08-2）"
        )

    def test_jimeng_historical_record_can_be_created_and_queried(self, user, db):
        """
        AC-08-2：历史 jimeng 类型的 UserServiceConfig 记录仍可正常写入和查询。
        """
        cfg = UserServiceConfig.objects.create(
            user=user,
            service_type="jimeng",
            encrypted_config=encrypt({"access_key": "legacy-key"}),
            is_active=True,
        )
        fetched = UserServiceConfig.objects.get(pk=cfg.pk)
        assert fetched.service_type == "jimeng"
        assert fetched.is_active is True

    def test_image_generator_urls_have_no_jimeng_routes(self):
        """
        AC-08-4：image_generator URL 中无专属即梦图片路由。

        通过检查 urls.py 中无 jimeng 关键词验证（不依赖 DB）。
        """
        import importlib
        import apps.image_generator.urls as img_urls_module
        # 检查路由列表中无 jimeng 相关 pattern
        url_patterns = getattr(img_urls_module, 'urlpatterns', [])
        for pattern in url_patterns:
            pattern_str = str(pattern.pattern)
            assert 'jimeng' not in pattern_str.lower(), (
                f"image_generator URL 中发现 jimeng 相关路由：{pattern_str}（AC-08-4）"
            )
