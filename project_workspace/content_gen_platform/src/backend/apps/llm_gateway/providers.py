"""LLM provider implementations: DeepSeek and Volcano Engine."""
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
VOLCANO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


class BaseLLMProvider(ABC):
    @abstractmethod
    async def stream_chat(
        self, messages: list[dict], max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they arrive from the LLM."""
        ...


class DeepSeekProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        temperature: float = 1.0,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def stream_chat(
        self, messages: list[dict], max_tokens: int | None = None
    ) -> AsyncGenerator[str, None]:
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": effective_max_tokens,
                    "temperature": self.temperature,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    import json
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


class VolcanoProvider(BaseLLMProvider):
    """Volcano Engine (Doubao) uses OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-pro-4k",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def stream_chat(
        self, messages: list[dict], max_tokens: int | None = None
    ) -> AsyncGenerator[str, None]:
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{VOLCANO_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": effective_max_tokens,
                    "temperature": self.temperature,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    import json
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


def get_provider(service_type: str, config: dict) -> BaseLLMProvider:
    """Factory: return the appropriate LLM provider from decrypted config."""
    if service_type == "llm_deepseek":
        return DeepSeekProvider(
            api_key=config["api_key"],
            model=config.get("model_name", "deepseek-chat"),
            temperature=float(config.get("temperature", 1.0)),
            max_tokens=int(config.get("max_tokens", 4096)),
        )
    if service_type == "llm_volcano":
        return VolcanoProvider(
            api_key=config["api_key"],
            model=config.get("model_name", "doubao-pro-4k"),
            temperature=float(config.get("temperature", 0.7)),
            max_tokens=int(config.get("max_tokens", 2048)),
        )
    raise ValueError(f"Unknown LLM service type: {service_type}")
