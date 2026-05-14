"""
Unit tests for settings_vault.views — TestAndSaveView (POST test-and-save/).

覆盖（ADR-10，FR-6.3，US-08 AC-08-3/AC-08-4，OQ-8=A）：
  - 未认证 → 401
  - api_key 为空 → 400
  - service_type 不支持 → 400, error=UNSUPPORTED_SERVICE_TYPE
  - Ark 验证失败 ARK_KEY_INVALID → 400, 不入库
  - Ark 验证失败 ARK_QUOTA_EXCEEDED → 400, 不入库
  - Ark 验证失败 ARK_UNREACHABLE → 400, 不入库
  - Ark 验证通过 → 200, saved=True, 入库且可查到 last_validated_at
  - 重复调用（update_or_create）：第二次调用覆盖已有记录
  - 安全守卫：响应体不含 api_key 内容（write_only 保证）
  - 安全守卫：error detail 不 echo api_key

关联需求：FR-6.3、US-08 AC-08-3/AC-08-4、OQ-8=A、ADR-10
"""
import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import decrypt, encrypt
from apps.settings_vault.models import UserServiceConfig

User = get_user_model()

TEST_AND_SAVE_URL = "/api/v1/settings/users/me/services/doubao_image/test-and-save/"
STATUS_URL = "/api/v1/settings/users/me/services/doubao_image/status/"
CANARY_KEY = "sk-CANARY-DO-NOT-ECHO-99999"


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


def _mock_validate(ok: bool, code: str = ""):
    """patch validate_doubao_key 的快捷方式。"""
    return patch(
        "apps.settings_vault.views.validate_doubao_key",
        return_value=(ok, code),
    )


@pytest.mark.django_db
class TestTestAndSaveViewAuth:

    def test_requires_authentication(self, api_client):
        """未认证 POST → 401。"""
        resp = api_client.post(TEST_AND_SAVE_URL, {"api_key": "somekey"}, format="json")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestTestAndSaveViewValidation:

    def test_empty_api_key_returns_400(self, user):
        """api_key 为空字符串 → 400。"""
        client = _auth_client(user)
        resp = client.post(TEST_AND_SAVE_URL, {"api_key": ""}, format="json")
        assert resp.status_code == 400

    def test_missing_api_key_returns_400(self, user):
        """请求体无 api_key 字段 → 400。"""
        client = _auth_client(user)
        resp = client.post(TEST_AND_SAVE_URL, {}, format="json")
        assert resp.status_code == 400

    def test_unsupported_service_type_returns_400(self, user):
        """不支持的 service_type → 400, error=UNSUPPORTED_SERVICE_TYPE。"""
        client = _auth_client(user)
        url = "/api/v1/settings/users/me/services/llm_volcano/test-and-save/"
        resp = client.post(url, {"api_key": "somekey"}, format="json")
        assert resp.status_code == 400
        assert resp.data["error"] == "UNSUPPORTED_SERVICE_TYPE"


@pytest.mark.django_db
class TestTestAndSaveViewArkErrors:

    def test_ark_key_invalid_returns_400_no_db_write(self, user):
        """Ark 返回 ARK_KEY_INVALID → 400，数据库中无记录写入。"""
        client = _auth_client(user)
        with _mock_validate(False, "ARK_KEY_INVALID"):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": CANARY_KEY}, format="json")
        assert resp.status_code == 400
        assert resp.data["error"] == "ARK_KEY_INVALID"
        # 确认未入库
        assert not UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists()

    def test_ark_quota_exceeded_returns_400_no_db_write(self, user):
        """Ark 返回 ARK_QUOTA_EXCEEDED → 400，数据库中无记录写入。"""
        client = _auth_client(user)
        with _mock_validate(False, "ARK_QUOTA_EXCEEDED"):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": "some-key"}, format="json")
        assert resp.status_code == 400
        assert resp.data["error"] == "ARK_QUOTA_EXCEEDED"
        assert not UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists()

    def test_ark_unreachable_returns_400_no_db_write(self, user):
        """Ark 返回 ARK_UNREACHABLE → 400，数据库中无记录写入。"""
        client = _auth_client(user)
        with _mock_validate(False, "ARK_UNREACHABLE"):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": "some-key"}, format="json")
        assert resp.status_code == 400
        assert resp.data["error"] == "ARK_UNREACHABLE"
        assert not UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists()


@pytest.mark.django_db
class TestTestAndSaveViewSuccess:

    def test_valid_key_saves_and_returns_200(self, user):
        """
        Ark 验证通过 → 200, saved=True, 数据库写入加密配置（OQ-8=A，ADR-10）。
        """
        client = _auth_client(user)
        with _mock_validate(True, ""):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": "valid-key"}, format="json")
        assert resp.status_code == 200
        assert resp.data["saved"] is True
        assert "last_validated_at" in resp.data

        # 确认数据库记录存在
        cfg = UserServiceConfig.objects.get(user=user, service_type="doubao_image")
        assert cfg.is_active is True
        assert cfg.last_validated_at is not None

        # 确认加密存储（解密后可得到 api_key）
        stored = decrypt(bytes(cfg.encrypted_config))
        assert stored["api_key"] == "valid-key"

    def test_second_call_overwrites_existing_record(self, user):
        """
        重复调用（update_or_create）：第二次调用覆盖已有记录，不创建重复行。
        """
        client = _auth_client(user)

        # 第一次配置
        with _mock_validate(True, ""):
            client.post(TEST_AND_SAVE_URL, {"api_key": "first-key"}, format="json")

        # 第二次配置（新 Key）
        with _mock_validate(True, ""):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": "second-key"}, format="json")

        assert resp.status_code == 200
        # 数据库中应只有一条记录
        count = UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).count()
        assert count == 1

        # 最新记录的 Key 应为 second-key
        cfg = UserServiceConfig.objects.get(user=user, service_type="doubao_image")
        stored = decrypt(bytes(cfg.encrypted_config))
        assert stored["api_key"] == "second-key"


@pytest.mark.django_db
class TestTestAndSaveViewSecurityGuard:

    def test_response_does_not_echo_api_key_on_success(self, user):
        """
        安全守卫：成功响应体中不包含 api_key 值（write_only=True，ADR-10）。
        """
        client = _auth_client(user)
        with _mock_validate(True, ""):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": CANARY_KEY}, format="json")
        assert resp.status_code == 200
        response_str = str(resp.data)
        assert CANARY_KEY not in response_str, (
            f"安全违规：api_key 出现在成功响应体中: {response_str!r}"
        )
        # 成功响应仅含 saved 和 last_validated_at
        assert "api_key" not in resp.data, (
            "安全违规：响应体中存在 api_key 字段"
        )

    def test_error_detail_does_not_echo_api_key(self, user):
        """
        安全守卫：失败时的 error detail 不 echo api_key 内容（ADR-10）。
        """
        client = _auth_client(user)
        with _mock_validate(False, "ARK_KEY_INVALID"):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": CANARY_KEY}, format="json")
        assert resp.status_code == 400
        response_str = str(resp.data)
        assert CANARY_KEY not in response_str, (
            f"安全违规：api_key 出现在错误响应体中: {response_str!r}"
        )

    def test_user_isolation(self, user, user2):
        """
        用户 A 的配置对用户 B 不可见（权限隔离）。
        """
        client1 = _auth_client(user)
        client2 = _auth_client(user2)

        with _mock_validate(True, ""):
            client1.post(TEST_AND_SAVE_URL, {"api_key": "user1-key"}, format="json")

        # user2 查询 status 应返回未配置
        resp = client2.get(STATUS_URL)
        assert resp.status_code == 200
        assert resp.data["is_configured"] is False


@pytest.mark.django_db(transaction=True)
class TestTestAndSaveViewAtomicity:
    """
    原子性守卫：验证 transaction.atomic() 保证——验证通过才写库，中途抛异常不留脏记录。

    关联需求：ADR-10、OQ-8=A
    """

    def test_db_write_occurs_on_success(self, user):
        """
        Ark 验证通过后 DB 应有新记录（正向原子路径）。
        """
        client = _auth_client(user)
        assert not UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists(), "前置条件：DB 中应无记录"

        with _mock_validate(True, ""):
            resp = client.post(TEST_AND_SAVE_URL, {"api_key": "atomic-valid-key"}, format="json")

        assert resp.status_code == 200
        assert UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists(), "验证通过后 DB 应有记录"

    def test_no_db_write_when_ark_validation_fails(self, user):
        """
        Ark 验证失败时 DB 不应有任何新增记录（原子保障：先验证再入库）。

        设计说明：TestAndSaveView 实现中，validate_doubao_key 返回 False
        时直接 return 400，不进入 transaction.atomic() 块，因此 DB 保持干净。
        """
        client = _auth_client(user)

        for error_code in ["ARK_KEY_INVALID", "ARK_QUOTA_EXCEEDED", "ARK_UNREACHABLE"]:
            # 确保每次测试前 DB 无记录
            UserServiceConfig.objects.filter(user=user, service_type="doubao_image").delete()

            with _mock_validate(False, error_code):
                resp = client.post(
                    TEST_AND_SAVE_URL, {"api_key": "some-key"}, format="json"
                )
            assert resp.status_code == 400, f"{error_code} 应返回 400"
            assert not UserServiceConfig.objects.filter(
                user=user, service_type="doubao_image"
            ).exists(), f"{error_code} 验证失败时不应有 DB 记录"

    def test_db_write_rolled_back_if_encrypt_raises(self, user):
        """
        transaction.atomic() 块内抛出异常时，DB 不留脏记录。

        模拟 encrypt() 函数在 atomic 块内部抛出异常（模拟写入失败场景），
        验证 DB 无残留记录（ADR-10 原子性保证）。

        实现说明：
          - Django/DRF TestClient 默认 raise_request_exception=True，未捕获异常
            会向上抛出；但 DRF exception handler 会将 Exception（非 APIException）
            映射为 500。
          - 因此验证方式：断言响应码为 500（或捕获 RuntimeError），
            并断言 DB 中无新增记录（回滚验证）。
          - 使用 raise_request_exception=False 让客户端静默处理 500，
            专注于断言 DB 状态。
        """
        from rest_framework.test import APIClient as _APIClient
        from rest_framework_simplejwt.tokens import RefreshToken as _RT

        # 构造不抛出异常的客户端（只关心 DB 副作用）
        silent_client = _APIClient(raise_request_exception=False)
        refresh = _RT.for_user(user)
        silent_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        assert not UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists(), "前置条件：DB 中应无记录"

        with _mock_validate(True, ""):
            with patch(
                "apps.settings_vault.views.encrypt",
                side_effect=RuntimeError("模拟加密失败"),
            ):
                resp = silent_client.post(
                    TEST_AND_SAVE_URL, {"api_key": "atomic-key"}, format="json"
                )

        # encrypt 抛出异常 → 视图返回 500
        assert resp.status_code == 500, (
            f"encrypt 异常应触发 500，实际: {resp.status_code}"
        )
        # 事务回滚，DB 中不应有新记录
        assert not UserServiceConfig.objects.filter(
            user=user, service_type="doubao_image"
        ).exists(), "atomic() 块内异常应回滚，DB 不应有脏记录"
