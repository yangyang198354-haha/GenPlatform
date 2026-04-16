"""Unit tests for llm_gateway.providers — get_provider factory."""
import pytest

from apps.llm_gateway.providers import (
    DeepSeekProvider,
    VolcanoProvider,
    get_provider,
)


class TestGetProvider:

    def test_get_deepseek_provider(self):
        """get_provider('llm_deepseek', ...) must return a DeepSeekProvider."""
        config = {"api_key": "sk-test-deepseek", "model_name": "deepseek-chat"}
        provider = get_provider("llm_deepseek", config)
        assert isinstance(provider, DeepSeekProvider)
        assert provider.api_key == "sk-test-deepseek"
        assert provider.model == "deepseek-chat"

    def test_get_volcano_provider(self):
        """get_provider('llm_volcano', ...) must return a VolcanoProvider."""
        config = {"api_key": "ep-fake-volcano", "model_name": "doubao-pro-4k"}
        provider = get_provider("llm_volcano", config)
        assert isinstance(provider, VolcanoProvider)
        assert provider.api_key == "ep-fake-volcano"
        assert provider.model == "doubao-pro-4k"

    def test_get_unknown_provider_raises(self):
        """Unknown service_type must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM service type"):
            get_provider("llm_unknown", {"api_key": "xxx"})

    def test_get_deepseek_provider_with_temperature_and_max_tokens(self):
        """get_provider for DeepSeek must read temperature and max_tokens from config."""
        config = {
            "api_key": "sk-test",
            "model_name": "deepseek-reasoner",
            "temperature": 0.5,
            "max_tokens": 2048,
        }
        provider = get_provider("llm_deepseek", config)
        assert isinstance(provider, DeepSeekProvider)
        assert provider.model == "deepseek-reasoner"
        assert provider.temperature == 0.5
        assert provider.max_tokens == 2048

    def test_get_deepseek_provider_defaults(self):
        """DeepSeek provider defaults: temperature=1.0, max_tokens=4096."""
        config = {"api_key": "sk-test"}
        provider = get_provider("llm_deepseek", config)
        assert provider.model == "deepseek-chat"
        assert provider.temperature == 1.0
        assert provider.max_tokens == 4096

    def test_get_volcano_provider_with_temperature_and_max_tokens(self):
        """get_provider for Volcano must read temperature and max_tokens from config."""
        config = {
            "api_key": "sk-volcano",
            "model_name": "ep-20240101-abc",
            "temperature": 0.8,
            "max_tokens": 2000,
        }
        provider = get_provider("llm_volcano", config)
        assert isinstance(provider, VolcanoProvider)
        assert provider.temperature == 0.8
        assert provider.max_tokens == 2000

    def test_get_volcano_provider_defaults(self):
        """Volcano provider defaults: temperature=0.7, max_tokens=2048."""
        config = {"api_key": "sk-volcano", "model_name": "ep-test"}
        provider = get_provider("llm_volcano", config)
        assert provider.temperature == 0.7
        assert provider.max_tokens == 2048

    def test_get_deepseek_provider_string_temperature_coerced(self):
        """temperature and max_tokens stored as strings must be coerced to correct types."""
        config = {
            "api_key": "sk-test",
            "temperature": "0.5",
            "max_tokens": "2048",
        }
        provider = get_provider("llm_deepseek", config)
        assert isinstance(provider.temperature, float)
        assert isinstance(provider.max_tokens, int)
        assert provider.temperature == 0.5
        assert provider.max_tokens == 2048
