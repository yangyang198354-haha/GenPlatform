"""Unit tests for settings_vault.views — ServiceConfigListView / ServiceConfigDetailView."""
import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt, decrypt
from apps.settings_vault.models import UserServiceConfig

User = get_user_model()

SERVICES_LIST_URL = "/api/v1/settings/services/"


def _url_detail(service_type):
    return f"/api/v1/settings/services/{service_type}/"


def _url_test(service_type):
    return f"/api/v1/settings/services/{service_type}/test/"


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
        # 自 INC-2026-05-15 修复起，PUT 内部会调 _test_connection 探活，避免真实 HTTP 必须 mock
        with patch(
            "apps.settings_vault.views._test_connection",
            return_value={"success": True, "message": "ok"},
        ):
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


@pytest.mark.django_db
class TestLastValidatedAtWriteback:
    """
    INC-2026-05-15 回归 + Canary：保存/测试 LLM 配置必须正确写入 last_validated_at。

    背景：原实现 PUT 与 TestView 都不写 last_validated_at，导致 selectors.last_test_ok
    永远为 False，LlmSelector 永远置灰。本类锁死该字段的写入语义防回归。
    """

    def test_save_llm_with_passing_test_sets_last_validated_at(self, user, db):
        """PUT + 探活成功 → last_validated_at 非空（让 LlmSelector 解灰）。"""
        client = _auth_client(user)
        with patch(
            "apps.settings_vault.views._test_connection",
            return_value={"success": True, "message": "ok"},
        ):
            resp = client.put(
                _url_detail("llm_deepseek"),
                {"api_key": "sk-test"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["test_passed"] is True
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        assert cfg.last_validated_at is not None, (
            "test_passed 时必须写 last_validated_at，否则 LlmSelector 仍灰色（INC-2026-05-15）"
        )

    def test_save_llm_with_failing_test_keeps_last_validated_at_null(self, user, db):
        """PUT + 探活失败 → 仍保存配置，但 last_validated_at 为 None（前端 tooltip 提示）。"""
        client = _auth_client(user)
        with patch(
            "apps.settings_vault.views._test_connection",
            return_value={"success": False, "message": "HTTP 401"},
        ):
            resp = client.put(
                _url_detail("llm_deepseek"),
                {"api_key": "sk-bad"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["test_passed"] is False
        assert "test_warning" in resp.data
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        assert cfg.is_active is True
        assert cfg.last_validated_at is None

    def test_save_llm_update_with_failing_test_clears_previously_valid_timestamp(self, user, db):
        """更新 key 时探活失败 → 旧的 last_validated_at 必须被清空（防止 UI 误导）。"""
        from django.utils import timezone
        UserServiceConfig.objects.create(
            user=user,
            service_type="llm_deepseek",
            encrypted_config=encrypt({"api_key": "sk-old"}),
            is_active=True,
            last_validated_at=timezone.now(),
        )
        client = _auth_client(user)
        with patch(
            "apps.settings_vault.views._test_connection",
            return_value={"success": False, "message": "HTTP 401"},
        ):
            resp = client.put(
                _url_detail("llm_deepseek"),
                {"api_key": "sk-new-bad"},
                format="json",
            )
        assert resp.status_code == 200
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        assert cfg.last_validated_at is None, (
            "更新失败时旧的 validated 时间戳必须清空，否则 selector 误认为新 key 已验证"
        )

    def test_test_view_success_writes_last_validated_at(self, user, db):
        """POST /test/ 探活成功 → 回写 last_validated_at（让已存 key 的老用户解灰）。"""
        UserServiceConfig.objects.create(
            user=user,
            service_type="llm_deepseek",
            encrypted_config=encrypt({"api_key": "sk-test"}),
            is_active=True,
            last_validated_at=None,
        )
        client = _auth_client(user)
        with patch(
            "apps.settings_vault.views._test_connection",
            return_value={"success": True, "message": "ok"},
        ):
            resp = client.post(_url_test("llm_deepseek"))
        assert resp.status_code == 200
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        assert cfg.last_validated_at is not None, (
            "测试成功必须回写 last_validated_at，否则 LlmSelector 仍灰色（INC-2026-05-15）"
        )

    def test_test_view_failure_does_not_touch_last_validated_at(self, user, db):
        """POST /test/ 探活失败 → 不改 last_validated_at（保留原值，无论是 None 还是有值）。"""
        from django.utils import timezone
        prior = timezone.now()
        UserServiceConfig.objects.create(
            user=user,
            service_type="llm_deepseek",
            encrypted_config=encrypt({"api_key": "sk-test"}),
            is_active=True,
            last_validated_at=prior,
        )
        client = _auth_client(user)
        with patch(
            "apps.settings_vault.views._test_connection",
            return_value={"success": False, "message": "HTTP 401"},
        ):
            resp = client.post(_url_test("llm_deepseek"))
        assert resp.status_code == 200
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        # 失败时保留原值（这里是 prior 时间戳；若原本是 None 则保持 None）
        assert cfg.last_validated_at == prior, (
            "测试失败时不应覆盖原 last_validated_at"
        )
