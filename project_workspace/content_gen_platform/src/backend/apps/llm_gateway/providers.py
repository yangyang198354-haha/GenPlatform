"""LLM provider implementations: DeepSeek and Volcano Engine."""
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
VOLCANO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# ---------------------------------------------------------------------------
# 白名单常量（OPEN-02：代码常量，不做 DB 配置表，更新时随发版）
# ModelInfo 结构：{"id": str, "label": str}
# ---------------------------------------------------------------------------

FALLBACK_MODELS: dict[str, list[dict]] = {
    "llm_deepseek": [
        {"id": "deepseek-chat", "label": "DeepSeek V3"},
        {"id": "deepseek-reasoner", "label": "DeepSeek R1"},
    ],
    "llm_volcano": [
        {"id": "doubao-pro-4k", "label": "豆包 Pro-4K"},
        {"id": "doubao-pro-32k", "label": "豆包 Pro-32K"},
        {"id": "doubao-pro-128k", "label": "豆包 Pro-128K"},
        {"id": "doubao-1-5-pro-32k-250115", "label": "豆包 1.5 Pro-32K"},
    ],
}


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class ProviderListModelsError(Exception):
    """Raised when a provider fails to list available models.

    Attributes:
        provider: service_type string, e.g. "llm_deepseek"
        reason:   human-readable error description
    """

    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(f"[{provider}] list_models failed: {reason}")


class BaseLLMProvider(ABC):
    @abstractmethod
    async def stream_chat(
        self, messages: list[dict], max_tokens: int = 2048
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they arrive from the LLM."""
        ...


def _deepseek_label(model_id: str) -> str:
    """Map DeepSeek model id to a human-readable label."""
    _map = {
        "deepseek-chat": "DeepSeek V3",
        "deepseek-reasoner": "DeepSeek R1",
    }
    return _map.get(model_id, model_id)


def _volcano_label(model_id: str) -> str:
    """Map Volcano/Doubao model id to a human-readable label."""
    _map = {
        "doubao-pro-4k": "豆包 Pro-4K",
        "doubao-pro-32k": "豆包 Pro-32K",
        "doubao-pro-128k": "豆包 Pro-128K",
        "doubao-1-5-pro-32k-250115": "豆包 1.5 Pro-32K",
    }
    return _map.get(model_id, model_id)


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

    def list_models(self) -> list[dict]:
        """Fetch available DeepSeek models from /v1/models.

        Returns a list of ModelInfo dicts (id, label), filtered to ids that
        start with "deepseek-".

        HTTP timeout is 800 ms (connect + read combined).

        Raises:
            ProviderListModelsError: on timeout, network error, or non-2xx response.
        """
        try:
            with httpx.Client(timeout=0.8) as client:
                resp = client.get(
                    f"{DEEPSEEK_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    {"id": m["id"], "label": _deepseek_label(m["id"])}
                    for m in data.get("data", [])
                    if m.get("id", "").startswith("deepseek-")
                ]
        except httpx.TimeoutException as exc:
            raise ProviderListModelsError("llm_deepseek", f"timeout: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderListModelsError(
                "llm_deepseek", f"HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderListModelsError("llm_deepseek", f"network error: {exc}") from exc

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

    def list_models(self) -> list[dict]:
        """Fetch Volcano (Ark) models and return the intersection with the whitelist.

        RISK-01 対策：Ark /v3/models may return model ids that are not actually
        usable via the chat completions endpoint (false positives).  We therefore
        treat the Ark response only as a *liveness check* for the whitelist:
        return only those whitelist ids that Ark confirms still exist.

        HTTP timeout is 800 ms (connect + read combined).

        Raises:
            ProviderListModelsError: on timeout, network error, or non-2xx response.
        """
        whitelist_ids = {m["id"] for m in FALLBACK_MODELS["llm_volcano"]}
        try:
            with httpx.Client(timeout=0.8) as client:
                resp = client.get(
                    f"{VOLCANO_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                ark_ids = {m["id"] for m in data.get("data", []) if "id" in m}
                # intersection: only whitelist ids confirmed by Ark
                confirmed_ids = whitelist_ids & ark_ids
                # preserve whitelist order
                return [
                    {"id": m["id"], "label": _volcano_label(m["id"])}
                    for m in FALLBACK_MODELS["llm_volcano"]
                    if m["id"] in confirmed_ids
                ]
        except httpx.TimeoutException as exc:
            raise ProviderListModelsError("llm_volcano", f"timeout: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderListModelsError(
                "llm_volcano", f"HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderListModelsError("llm_volcano", f"network error: {exc}") from exc

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


def get_provider(
    service_type: str,
    config: dict,
    model: str | None = None,
) -> BaseLLMProvider:
    """Factory: return the appropriate LLM provider from decrypted config.

    Args:
        service_type: one of "llm_deepseek", "llm_volcano"
        config:       decrypted config dict (must contain "api_key")
        model:        optional explicit model override.  When provided, takes
                      precedence over config["model_name"] and the provider's
                      built-in default.  Pass None to use the config / default.

    Returns:
        A concrete BaseLLMProvider instance.

    Raises:
        ValueError: if service_type is not recognised.
    """
    if service_type == "llm_deepseek":
        effective_model = model or config.get("model_name", "deepseek-chat")
        return DeepSeekProvider(
            api_key=config["api_key"],
            model=effective_model,
            temperature=float(config.get("temperature", 1.0)),
            max_tokens=int(config.get("max_tokens", 4096)),
        )
    if service_type == "llm_volcano":
        effective_model = model or config.get("model_name", "doubao-pro-4k")
        return VolcanoProvider(
            api_key=config["api_key"],
            model=effective_model,
            temperature=float(config.get("temperature", 0.7)),
            max_tokens=int(config.get("max_tokens", 2048)),
        )
    raise ValueError(f"Unknown LLM service type: {service_type}")
