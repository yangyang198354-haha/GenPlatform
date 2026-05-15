"""Sanity / unit tests for apps.llm_gateway.selectors (PR-2).

All tests use unittest.mock — no DB, no network, no Django migrations required.
Run with:
    pytest apps/llm_gateway/tests/test_selectors.py -m "not integration and not django_db" -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Helpers: lightweight fakes (no Django ORM)
# ---------------------------------------------------------------------------

def _make_config(service_type, last_validated_at=None, is_active=True, updated_at=None):
    """Create a fake UserServiceConfig-like object."""
    return SimpleNamespace(
        service_type=service_type,
        is_active=is_active,
        last_validated_at=last_validated_at,
        updated_at=updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        encrypted_config=b"fake",
    )


_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
_OLDER = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Canary guard — whitelist must not drift silently
# ---------------------------------------------------------------------------

class TestWhitelistCanary:
    def test_deepseek_default_is_deepseek_chat(self):
        """Canary: default (first) DeepSeek model must remain deepseek-chat."""
        from apps.llm_gateway.selectors import MODEL_WHITELIST
        assert MODEL_WHITELIST["llm_deepseek"][0]["id"] == "deepseek-chat"

    def test_volcano_default_is_doubao_pro_4k(self):
        """Canary: default (first) Volcano model must remain doubao-pro-4k."""
        from apps.llm_gateway.selectors import MODEL_WHITELIST
        assert MODEL_WHITELIST["llm_volcano"][0]["id"] == "doubao-pro-4k"

    def test_supported_service_types_order(self):
        """Canary: llm_deepseek must come before llm_volcano in the supported list."""
        from apps.llm_gateway.selectors import SUPPORTED_LLM_SERVICE_TYPES
        assert SUPPORTED_LLM_SERVICE_TYPES.index("llm_deepseek") < \
               SUPPORTED_LLM_SERVICE_TYPES.index("llm_volcano")


# ---------------------------------------------------------------------------
# validate_choice
# ---------------------------------------------------------------------------

class TestValidateChoice:

    def _run(self, user, service_type, model, cfg=None):
        """Run validate_choice with _get_user_service_config mocked."""
        from apps.llm_gateway.selectors import validate_choice
        with patch(
            "apps.llm_gateway.selectors._get_user_service_config",
            return_value=cfg,
        ):
            validate_choice(user, service_type, model)

    def test_valid_deepseek_chat(self):
        """Valid deepseek-chat choice must not raise."""
        cfg = _make_config("llm_deepseek")
        self._run(user=MagicMock(), service_type="llm_deepseek", model="deepseek-chat", cfg=cfg)

    def test_valid_volcano_pro4k(self):
        """Valid doubao-pro-4k choice must not raise."""
        cfg = _make_config("llm_volcano")
        self._run(user=MagicMock(), service_type="llm_volcano", model="doubao-pro-4k", cfg=cfg)

    def test_invalid_service_type_raises_invalid_provider(self):
        """Unknown service_type must raise InvalidChoiceError(INVALID_PROVIDER)."""
        from apps.llm_gateway.selectors import InvalidChoiceError
        with pytest.raises(InvalidChoiceError) as exc_info:
            self._run(MagicMock(), "llm_fake", "deepseek-chat")
        assert exc_info.value.code == "INVALID_PROVIDER"

    def test_unconfigured_provider_raises_not_configured(self):
        """Missing config must raise InvalidChoiceError(PROVIDER_NOT_CONFIGURED)."""
        from apps.llm_gateway.selectors import InvalidChoiceError
        with pytest.raises(InvalidChoiceError) as exc_info:
            self._run(MagicMock(), "llm_deepseek", "deepseek-chat", cfg=None)
        assert exc_info.value.code == "PROVIDER_NOT_CONFIGURED"

    def test_invalid_model_raises_invalid_model(self):
        """Non-whitelist model must raise InvalidChoiceError(INVALID_MODEL)."""
        from apps.llm_gateway.selectors import InvalidChoiceError
        cfg = _make_config("llm_deepseek")
        with pytest.raises(InvalidChoiceError) as exc_info:
            self._run(MagicMock(), "llm_deepseek", "gpt-4-malicious", cfg=cfg)
        assert exc_info.value.code == "INVALID_MODEL"


# ---------------------------------------------------------------------------
# resolve_default — decision chain
# ---------------------------------------------------------------------------

class TestResolveDefault:
    """
    Tests for the 4-step decision chain (design.md §4.1 + §7.1):

      1. Valid user preference → returns preference
      2. Preference provider invalid + deepseek valid → returns deepseek-chat
      3. No preference + deepseek valid → returns deepseek-chat
      4. No preference + deepseek invalid + volcano valid → returns volcano fallback
      5. Nothing valid → raises NoAvailableProviderError
    """

    def _make_user(self, preference=None):
        """Return a fake user object whose llm_preference behaves correctly."""
        from apps.llm_gateway.models import UserLLMPreference

        if preference is None:
            class _NoPreferenceUser:
                @property
                def llm_preference(self):
                    raise UserLLMPreference.DoesNotExist
            return _NoPreferenceUser()
        else:
            class _WithPreferenceUser:
                @property
                def llm_preference(self):
                    return preference
            return _WithPreferenceUser()

    def _run(self, configs: list, preference=None):
        """
        Patch DB queries inside resolve_default and call it.

        configs:    list of fake config objects (iterable result of ORM queryset).
        preference: SimpleNamespace(service_type=..., model=...) or None.
        """
        from apps.llm_gateway.selectors import resolve_default

        user = self._make_user(preference)

        fake_qs = MagicMock()
        fake_qs.filter.return_value.order_by.return_value = configs

        with patch("apps.llm_gateway.selectors.UserServiceConfig.objects", fake_qs):
            return resolve_default(user)

    # -- Step 1: valid preference ------------------------------------------

    def test_returns_preference_when_valid(self):
        """Decision chain step 1: valid preference → use it."""
        deepseek_cfg = _make_config("llm_deepseek", last_validated_at=_NOW)
        pref = SimpleNamespace(service_type="llm_deepseek", model="deepseek-reasoner")
        result = self._run(
            configs=[deepseek_cfg],
            preference=pref,
        )
        assert result == ("llm_deepseek", "deepseek-reasoner")

    # -- Step 2: preference invalid, deepseek valid -------------------------

    def test_falls_back_to_deepseek_when_preference_provider_invalid(self):
        """If preference's provider has no valid config, fall back to DeepSeek."""
        deepseek_cfg = _make_config("llm_deepseek", last_validated_at=_NOW)
        # preference points to volcano but volcano is not in config_map (not configured)
        pref = SimpleNamespace(service_type="llm_volcano", model="doubao-pro-4k")
        result = self._run(
            configs=[deepseek_cfg],  # only deepseek in map
            preference=pref,
        )
        assert result == ("llm_deepseek", "deepseek-chat")

    # -- Step 3: no preference, deepseek valid ------------------------------

    def test_defaults_to_deepseek_when_no_preference(self):
        """No preference + DeepSeek valid → deepseek-chat."""
        deepseek_cfg = _make_config("llm_deepseek", last_validated_at=_NOW)
        result = self._run(
            configs=[deepseek_cfg],
            preference=None,
        )
        assert result == ("llm_deepseek", "deepseek-chat")

    # -- Step 4: deepseek invalid, volcano valid ----------------------------

    def test_falls_back_to_volcano_when_deepseek_invalid(self):
        """No deepseek valid → fall back to next provider in SUPPORTED order."""
        volcano_cfg = _make_config("llm_volcano", last_validated_at=_NOW)
        result = self._run(
            configs=[volcano_cfg],
            preference=None,
        )
        assert result == ("llm_volcano", "doubao-pro-4k")

    # -- Step 5: nothing valid ----------------------------------------------

    def test_raises_no_available_provider_when_nothing_valid(self):
        """All providers invalid → NoAvailableProviderError."""
        from apps.llm_gateway.selectors import NoAvailableProviderError
        # deepseek config exists but last_validated_at is None
        deepseek_cfg = _make_config("llm_deepseek", last_validated_at=None)
        with pytest.raises(NoAvailableProviderError):
            self._run(
                configs=[deepseek_cfg],
                preference=None,
            )


# ---------------------------------------------------------------------------
# providers.py — get_provider model override (PR-2 §1.1)
# ---------------------------------------------------------------------------

class TestGetProviderModelOverride:
    """Verify the new model= parameter in get_provider."""

    def test_explicit_model_overrides_config(self):
        """Explicit model kwarg must override config['model_name']."""
        from apps.llm_gateway.providers import get_provider, DeepSeekProvider
        config = {"api_key": "sk-test", "model_name": "deepseek-chat"}
        provider = get_provider("llm_deepseek", config, model="deepseek-reasoner")
        assert isinstance(provider, DeepSeekProvider)
        assert provider.model == "deepseek-reasoner"

    def test_none_model_falls_through_to_config(self):
        """model=None must fall through to config['model_name']."""
        from apps.llm_gateway.providers import get_provider
        config = {"api_key": "sk-test", "model_name": "deepseek-reasoner"}
        provider = get_provider("llm_deepseek", config, model=None)
        assert provider.model == "deepseek-reasoner"

    def test_omitted_model_falls_through_to_default(self):
        """model not passed at all must use provider default."""
        from apps.llm_gateway.providers import get_provider, DeepSeekProvider
        config = {"api_key": "sk-test"}
        provider = get_provider("llm_deepseek", config)
        assert isinstance(provider, DeepSeekProvider)
        assert provider.model == "deepseek-chat"

    def test_volcano_explicit_model_override(self):
        """Explicit model for Volcano must override config['model_name']."""
        from apps.llm_gateway.providers import get_provider, VolcanoProvider
        config = {"api_key": "ep-test", "model_name": "doubao-pro-4k"}
        provider = get_provider("llm_volcano", config, model="doubao-pro-32k")
        assert isinstance(provider, VolcanoProvider)
        assert provider.model == "doubao-pro-32k"


# ---------------------------------------------------------------------------
# providers.py — list_models fallback / error path
# ---------------------------------------------------------------------------

class TestListModels:

    def test_deepseek_list_models_timeout_raises_error(self):
        """Timeout inside DeepSeekProvider.list_models() must raise ProviderListModelsError."""
        import httpx
        from apps.llm_gateway.providers import DeepSeekProvider, ProviderListModelsError

        provider = DeepSeekProvider(api_key="sk-fake")
        # Patch httpx.Client in the providers module namespace (where it is imported).
        with patch("apps.llm_gateway.providers.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(ProviderListModelsError) as exc_info:
                provider.list_models()
        assert exc_info.value.provider == "llm_deepseek"
        assert "timeout" in exc_info.value.reason

    def test_volcano_list_models_returns_whitelist_intersection(self):
        """VolcanoProvider.list_models() must return only whitelist IDs confirmed by Ark."""
        from apps.llm_gateway.providers import VolcanoProvider

        ark_response = {
            "data": [
                {"id": "doubao-pro-4k"},
                {"id": "doubao-pro-32k"},
                {"id": "some-unknown-new-model"},  # NOT in whitelist — must be excluded
            ]
        }
        provider = VolcanoProvider(api_key="fake-key")
        with patch("apps.llm_gateway.providers.httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.json.return_value = ark_response
            mock_resp.raise_for_status = MagicMock()
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp

            result = provider.list_models()

        result_ids = [m["id"] for m in result]
        assert "doubao-pro-4k" in result_ids
        assert "doubao-pro-32k" in result_ids
        # Unknown model from Ark must NOT appear (RISK-01 対策)
        assert "some-unknown-new-model" not in result_ids

    def test_volcano_list_models_network_error_raises_error(self):
        """Network error in VolcanoProvider.list_models() must raise ProviderListModelsError."""
        import httpx
        from apps.llm_gateway.providers import VolcanoProvider, ProviderListModelsError

        provider = VolcanoProvider(api_key="fake-key")
        with patch("apps.llm_gateway.providers.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            with pytest.raises(ProviderListModelsError) as exc_info:
                provider.list_models()
        assert exc_info.value.provider == "llm_volcano"
