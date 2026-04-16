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
