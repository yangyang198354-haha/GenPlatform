"""
Unit tests for settings_vault.views — ServiceStatusView (GET status/).

覆盖（ADR-09，FR-7.1，US-08 AC-08-1/AC-08-4）：
  - 未认证 → 401
  - 已认证，服务未配置 → 200, is_configured=False
  - 已认证，服务已配置（is_active=True）→ 200, is_configured=True
  - 已认证，服务已配置（is_active=False）→ 200, is_configured=False（已停用不算配置）
  - 安全守卫：响应体不含 api_key 字段

关联需求：FR-7.1、US-08 AC-08-1/AC-08-4、ADR-09
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt
from apps.settings_vault.models import UserServiceConfig

User = get_user_model()


def _url_status(service_type="doubao_image"):
    return f"/api/v1/settings/users/me/services/{service_type}/status/"


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.mark.django_db
class TestServiceStatusView:

    def test_requires_authentication(self, api_client):
        """未认证 GET → 401。"""
        resp = api_client.get(_url_status())
        assert resp.status_code == 401

    def test_returns_not_configured_when_no_record(self, user):
        """无配置记录 → is_configured=False, last_validated_at=null。"""
        client = _auth_client(user)
        resp = client.get(_url_status())
        assert resp.status_code == 200
        assert resp.data["is_configured"] is False
        assert resp.data["last_validated_at"] is None

    def test_returns_configured_when_active_record_exists(self, user):
        """存在 is_active=True 记录 → is_configured=True。"""
        UserServiceConfig.objects.create(
            user=user,
            service_type="doubao_image",
            encrypted_config=encrypt({"api_key": "test-key"}),
            is_active=True,
        )
        client = _auth_client(user)
        resp = client.get(_url_status())
        assert resp.status_code == 200
        assert resp.data["is_configured"] is True

    def test_returns_not_configured_when_inactive_record(self, user):
        """存在 is_active=False 记录 → is_configured=False（已停用不算配置）。"""
        UserServiceConfig.objects.create(
            user=user,
            service_type="doubao_image",
            encrypted_config=encrypt({"api_key": "test-key"}),
            is_active=False,
        )
        client = _auth_client(user)
        resp = client.get(_url_status())
        assert resp.status_code == 200
        assert resp.data["is_configured"] is False

    def test_returns_last_validated_at_when_set(self, user):
        """last_validated_at 字段有值时，应出现在响应中。"""
        from django.utils import timezone
        now = timezone.now()
        UserServiceConfig.objects.create(
            user=user,
            service_type="doubao_image",
            encrypted_config=encrypt({"api_key": "test-key"}),
            is_active=True,
            last_validated_at=now,
        )
        client = _auth_client(user)
        resp = client.get(_url_status())
        assert resp.status_code == 200
        assert resp.data["is_configured"] is True
        assert resp.data["last_validated_at"] is not None

    def test_response_does_not_contain_api_key(self, user):
        """
        安全守卫：响应体不包含 api_key 字段或任何 Key 派生信息（ADR-09）。
        """
        UserServiceConfig.objects.create(
            user=user,
            service_type="doubao_image",
            encrypted_config=encrypt({"api_key": "sk-CANARY-SECRET"}),
            is_active=True,
        )
        client = _auth_client(user)
        resp = client.get(_url_status())
        assert resp.status_code == 200
        # 响应字段必须只有 is_configured 和 last_validated_at
        assert set(resp.data.keys()) == {"is_configured", "last_validated_at"}, (
            f"响应包含额外字段（安全违规）: {set(resp.data.keys())}"
        )
        # 确保 CANARY 字符串不在响应中
        response_str = str(resp.data)
        assert "sk-CANARY-SECRET" not in response_str, (
            "安全违规：响应体中包含 api_key 内容"
        )

    def test_status_is_user_scoped(self, user, user2):
        """用户 A 的配置对用户 B 不可见（权限隔离）。"""
        UserServiceConfig.objects.create(
            user=user,
            service_type="doubao_image",
            encrypted_config=encrypt({"api_key": "user1-key"}),
            is_active=True,
        )
        # user2 查询应返回未配置
        client2 = _auth_client(user2)
        resp = client2.get(_url_status())
        assert resp.status_code == 200
        assert resp.data["is_configured"] is False

    def test_invalid_service_type_returns_400_canary_guard(self, user):
        """
        Canary 守卫：未知 service_type 必须 400 拒绝，避免泄露系统支持的服务集合语义。

        关联：TODO-03 修复（service_type 白名单校验）。
        """
        client = _auth_client(user)
        resp = client.get(_url_status(service_type="hacker_probe_unknown"))
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_SERVICE_TYPE"
