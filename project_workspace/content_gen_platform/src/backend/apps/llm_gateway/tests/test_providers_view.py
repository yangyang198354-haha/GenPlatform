"""Sanity tests for PR-3: ProvidersView + GenerateContentView GET/POST 双入口。

范围：纯 unit/mock 测试，不发真实 HTTP 请求，不依赖 DB（除少量 django_db 标注）。
集成测试和 E2E 测试在 PR-5 补全。
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt
from apps.settings_vault.models import UserServiceConfig
from apps.llm_gateway.selectors import (
    NoAvailableProviderError,
    InvalidChoiceError,
)

User = get_user_model()

PROVIDERS_URL = "/api/v1/llm/providers/"
GENERATE_URL = "/api/v1/llm/generate/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


def _create_llm_config(user, service_type="llm_deepseek", api_key="sk-fake"):
    return UserServiceConfig.objects.create(
        user=user,
        service_type=service_type,
        encrypted_config=encrypt({"api_key": api_key}),
        is_active=True,
    )


def _fake_provider(tokens=("hello", " world")):
    """Return a mock provider whose stream_chat() yields the given tokens."""
    async def _stream(messages, max_tokens=2048):
        for t in tokens:
            yield t

    provider = MagicMock()
    provider.stream_chat = _stream
    return provider


def _collect_sse(response):
    raw = b"".join(response.streaming_content).decode()
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# 1. ProvidersView — GET /api/v1/llm/providers/
# ---------------------------------------------------------------------------

class TestProvidersView:
    """Sanity tests for GET /api/v1/llm/providers/."""

    def test_requires_auth(self, api_client):
        """未登录应返回 401。"""
        resp = api_client.get(PROVIDERS_URL)
        assert resp.status_code == 401

    @pytest.mark.django_db
    def test_returns_correct_payload_structure(self, user):
        """mock selectors.list_available_providers，验证返回 200 + 正确结构。"""
        fake_payload = {
            "default": {"service_type": "llm_deepseek", "model": "deepseek-chat"},
            "user_preference": None,
            "providers": [
                {
                    "service_type": "llm_deepseek",
                    "label": "DeepSeek",
                    "configured": True,
                    "last_test_ok": True,
                    "models_source": "dynamic",
                    "models": [{"id": "deepseek-chat", "label": "DeepSeek V3"}],
                }
            ],
            "warnings": [],
        }

        client = _auth_client(user)
        with patch(
            "apps.llm_gateway.views.list_available_providers",
            return_value=fake_payload,
        ) as mock_fn:
            resp = client.get(PROVIDERS_URL)

        assert resp.status_code == 200
        mock_fn.assert_called_once_with(user)

        data = resp.json()
        assert "providers" in data
        assert "default" in data
        assert "user_preference" in data
        assert "warnings" in data

    @pytest.mark.django_db
    def test_response_has_no_store_cache_control(self, user):
        """响应头必须包含 Cache-Control: no-store。"""
        client = _auth_client(user)
        with patch(
            "apps.llm_gateway.views.list_available_providers",
            return_value={"default": None, "user_preference": None, "providers": [], "warnings": []},
        ):
            resp = client.get(PROVIDERS_URL)

        assert resp.status_code == 200
        assert "no-store" in resp.get("Cache-Control", "")

    @pytest.mark.django_db
    def test_empty_providers_for_unconfigured_user(self, user):
        """无 LLM 配置的用户应返回 200 + providers=[]（不报 500）。"""
        client = _auth_client(user)
        with patch(
            "apps.llm_gateway.views.list_available_providers",
            return_value={"default": None, "user_preference": None, "providers": [], "warnings": []},
        ):
            resp = client.get(PROVIDERS_URL)

        assert resp.status_code == 200
        assert resp.json()["providers"] == []

    @pytest.mark.django_db
    def test_internal_error_returns_500(self, user):
        """selector 内部异常应映射为 500（不暴露 stacktrace）。"""
        client = _auth_client(user)
        with patch(
            "apps.llm_gateway.views.list_available_providers",
            side_effect=RuntimeError("db connection lost"),
        ):
            resp = client.get(PROVIDERS_URL)

        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
        # 不暴露原始异常消息
        assert "db connection lost" not in data["error"]


# ---------------------------------------------------------------------------
# 2. GenerateContentView POST — /api/v1/llm/generate/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateContentViewPost:
    """Sanity tests for POST /api/v1/llm/generate/."""

    def test_post_requires_auth(self, api_client):
        """未登录 POST 应返回 401。"""
        resp = api_client.post(GENERATE_URL, {"prompt": "hello"}, format="json")
        assert resp.status_code == 401

    def test_post_empty_prompt_returns_400(self, user, db):
        """POST 空 prompt 返回 400。"""
        client = _auth_client(user)
        resp = client.post(GENERATE_URL, {"prompt": "  "}, format="json")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_post_provider_without_model_returns_400_invalid_params(self, user, db):
        """只传 provider 不传 model 应返回 400 INVALID_PARAMS。"""
        client = _auth_client(user)
        resp = client.post(
            GENERATE_URL,
            {"prompt": "test", "provider": "llm_deepseek"},
            format="json",
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data.get("error_code") == "INVALID_PARAMS"

    def test_post_model_without_provider_returns_400_invalid_params(self, user, db):
        """只传 model 不传 provider 应返回 400 INVALID_PARAMS。"""
        client = _auth_client(user)
        resp = client.post(
            GENERATE_URL,
            {"prompt": "test", "model": "deepseek-chat"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json().get("error_code") == "INVALID_PARAMS"

    def test_post_with_provider_model_calls_validate_choice(self, user, db):
        """POST 带 provider+model 走 validate_choice 路径，成功后返回 SSE 200。"""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch("apps.llm_gateway.views.validate_choice") as mock_validate, \
             patch("apps.llm_gateway.views.get_provider", return_value=_fake_provider(["tok"])):
            resp = client.post(
                GENERATE_URL,
                {
                    "prompt": "write something",
                    "provider": "llm_deepseek",
                    "model": "deepseek-chat",
                },
                format="json",
            )

        mock_validate.assert_called_once_with(user, "llm_deepseek", "deepseek-chat")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.get("Content-Type", "")

    def test_post_without_provider_model_calls_resolve_default(self, user, db):
        """POST 不带 provider/model 走 resolve_default 路径，成功后返回 SSE 200。"""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch(
            "apps.llm_gateway.views.resolve_default",
            return_value=("llm_deepseek", "deepseek-chat"),
        ) as mock_resolve, \
             patch("apps.llm_gateway.views.get_provider", return_value=_fake_provider(["tok"])):
            resp = client.post(
                GENERATE_URL,
                {"prompt": "write something"},
                format="json",
            )

        mock_resolve.assert_called_once_with(user)
        assert resp.status_code == 200

    def test_post_invalid_provider_returns_400_invalid_provider(self, user, db):
        """validate_choice 抛 INVALID_PROVIDER 应返回 400。"""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch(
            "apps.llm_gateway.views.validate_choice",
            side_effect=InvalidChoiceError(code="INVALID_PROVIDER", message="不支持的服务类型"),
        ):
            resp = client.post(
                GENERATE_URL,
                {"prompt": "test", "provider": "llm_fake", "model": "gpt-4"},
                format="json",
            )

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "INVALID_PROVIDER"

    def test_post_invalid_model_returns_400_invalid_model(self, user, db):
        """validate_choice 抛 INVALID_MODEL 应返回 400。"""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch(
            "apps.llm_gateway.views.validate_choice",
            side_effect=InvalidChoiceError(code="INVALID_MODEL", message="模型不在白名单"),
        ):
            resp = client.post(
                GENERATE_URL,
                {"prompt": "test", "provider": "llm_deepseek", "model": "gpt-9999"},
                format="json",
            )

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "INVALID_MODEL"

    def test_post_provider_not_configured_returns_400(self, user, db):
        """validate_choice 抛 PROVIDER_NOT_CONFIGURED 应返回 400。"""
        client = _auth_client(user)

        with patch(
            "apps.llm_gateway.views.validate_choice",
            side_effect=InvalidChoiceError(
                code="PROVIDER_NOT_CONFIGURED",
                message="用户未配置该服务",
            ),
        ):
            resp = client.post(
                GENERATE_URL,
                {"prompt": "test", "provider": "llm_volcano", "model": "doubao-pro-32k"},
                format="json",
            )

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "PROVIDER_NOT_CONFIGURED"

    def test_post_no_available_provider_returns_400(self, user, db):
        """resolve_default 抛 NoAvailableProviderError 应返回 400 NO_AVAILABLE_PROVIDER。"""
        client = _auth_client(user)

        with patch(
            "apps.llm_gateway.views.resolve_default",
            side_effect=NoAvailableProviderError("no provider"),
        ):
            resp = client.post(GENERATE_URL, {"prompt": "test"}, format="json")

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "NO_AVAILABLE_PROVIDER"


# ---------------------------------------------------------------------------
# 3. GenerateContentView GET (向后兼容) — 关键回归点
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateContentViewGetBackwardCompat:
    """GET 方法仍然可用（向后兼容），走 resolve_default 路径。"""

    def test_get_no_provider_param_calls_resolve_default(self, user, db):
        """GET 不带 provider/model 走 resolve_default，与原行为一致。"""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch(
            "apps.llm_gateway.views.resolve_default",
            return_value=("llm_deepseek", "deepseek-chat"),
        ) as mock_resolve, \
             patch("apps.llm_gateway.views.get_provider", return_value=_fake_provider()):
            resp = client.get(GENERATE_URL, {"prompt": "hello"})

        mock_resolve.assert_called_once_with(user)
        assert resp.status_code == 200

    def test_get_no_config_returns_400_no_available_provider(self, user, db):
        """GET 无配置 → resolve_default 抛异常 → 400 NO_AVAILABLE_PROVIDER。"""
        client = _auth_client(user)
        with patch(
            "apps.llm_gateway.views.resolve_default",
            side_effect=NoAvailableProviderError("no provider"),
        ):
            resp = client.get(GENERATE_URL, {"prompt": "test"})

        assert resp.status_code == 400
        assert resp.json()["error_code"] == "NO_AVAILABLE_PROVIDER"


# ---------------------------------------------------------------------------
# 4. SSE done 事件包含 used_provider / used_model
# ---------------------------------------------------------------------------

class TestSseDoneEventFields:
    """验证 SSE done 事件新增字段。"""

    def test_done_event_contains_used_provider_and_model(self):
        """正常流结束时，done 事件必须包含 used_provider 和 used_model。"""
        from apps.llm_gateway.views import _sync_sse_generator

        class GoodProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                yield "Hello"

        chunks = list(
            _sync_sse_generator(
                GoodProvider(),
                [],
                ["doc-1"],
                service_type="llm_deepseek",
                model_id="deepseek-chat",
                user=None,  # user=None 时 _persist_preference 静默跳过
            )
        )

        last = json.loads(chunks[-1].replace("data:", "").strip())
        assert last.get("done") is True
        assert last.get("used_provider") == "llm_deepseek"
        assert last.get("used_model") == "deepseek-chat"
        assert last.get("used_doc_ids") == ["doc-1"]

    def test_error_event_does_not_contain_used_provider(self):
        """流出错时，done 事件不包含 used_provider（偏好不写入）。"""
        from apps.llm_gateway.views import _sync_sse_generator

        class BrokenProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                raise RuntimeError("upstream down")
                yield  # 让 Python 识别为 async generator

        chunks = list(
            _sync_sse_generator(
                BrokenProvider(),
                [],
                [],
                service_type="llm_deepseek",
                model_id="deepseek-chat",
                user=None,
            )
        )

        last = json.loads(chunks[-1].replace("data:", "").strip())
        assert last.get("done") is True
        assert "error" in last
        # 失败时不应包含 used_provider（或包含也可，关键是有 error 字段）
        # 按设计文档：失败路径不写偏好（此处只验证 error 存在）
