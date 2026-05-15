"""Business-logic selectors for LLM provider / model selection.

This module is the single source of truth for:
  - listing available providers and their model sets   (list_available_providers)
  - resolving the effective provider+model for a user  (resolve_default)
  - validating a user-supplied provider+model choice   (validate_choice)

Design constraints (from design.md §4.1):
  - Views remain thin: they parse HTTP, call one selector, build response.
  - Providers remain pure: they talk to LLM APIs, nothing else.
  - Selectors own all "read + decide" logic; they do NOT raise DRF exceptions.
    (views are responsible for mapping selector exceptions to HTTP status codes)
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.llm_gateway.models import UserLLMPreference
from apps.llm_gateway.providers import (
    FALLBACK_MODELS,
    ProviderListModelsError,
    get_provider,
)
from apps.settings_vault.models import UserServiceConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Ordered list of service_types that are treated as LLM providers.
SUPPORTED_LLM_SERVICE_TYPES: list[str] = ["llm_deepseek", "llm_volcano"]

# Human-readable labels for each provider (used in the API response).
PROVIDER_LABELS: dict[str, str] = {
    "llm_deepseek": "DeepSeek",
    "llm_volcano": "火山引擎豆包",
}

# MODEL_WHITELIST mirrors FALLBACK_MODELS but lives here so selectors.py is
# the authoritative layer for whitelist lookups; providers.py owns the constant.
MODEL_WHITELIST = FALLBACK_MODELS


# ---------------------------------------------------------------------------
# Exceptions (pure Python, no DRF dependency)
# ---------------------------------------------------------------------------

class NoAvailableProviderError(Exception):
    """Raised when no valid LLM provider can be resolved for a user."""


class InvalidChoiceError(Exception):
    """Raised when a user-supplied provider/model combination is invalid.

    Attributes:
        code:    machine-readable error code string
        message: human-readable description
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_user_service_config(user, service_type):
    """Return the most-recently-updated active UserServiceConfig, or None."""
    return (
        UserServiceConfig.objects.filter(
            user=user,
            service_type=service_type,
            is_active=True,
        )
        .order_by("-updated_at")
        .first()
    )


def _fetch_models_for_config(cfg) -> tuple[list[dict], str, str | None]:
    """Fetch models for a single UserServiceConfig.

    Returns:
        (models, models_source, warning_message_or_None)

    Only attempts a live fetch when the config has been validated at least
    once (last_validated_at IS NOT NULL).  Otherwise falls back immediately.

    Does NOT catch arbitrary exceptions — only ProviderListModelsError is
    handled here.  Other exceptions propagate to the caller (ThreadPoolExecutor
    future.result() will re-raise them).
    """
    from core.encryption import decrypt  # local import to avoid top-level Django app init order issues

    service_type = cfg.service_type
    label = PROVIDER_LABELS.get(service_type, service_type)

    last_test_ok = cfg.last_validated_at is not None
    if not last_test_ok:
        # Not safe to call a live endpoint without a successful prior test.
        return MODEL_WHITELIST.get(service_type, []), "fallback", None

    try:
        config = decrypt(bytes(cfg.encrypted_config))
        provider_instance = get_provider(service_type, config)
        models = provider_instance.list_models()
        return models, "dynamic", None
    except ProviderListModelsError as exc:
        logger.warning(
            "list_models failed for %s: %s — using fallback whitelist",
            service_type,
            exc.reason,
        )
        warning = f"{label}模型列表加载失败，使用默认列表"
        return MODEL_WHITELIST.get(service_type, []), "fallback", warning


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_available_providers(user) -> dict:
    """Build the ProvidersPayload for GET /api/v1/llm/providers/.

    Returns a dict with keys: default, user_preference, providers, warnings.

    Implementation notes:
      - Uses ThreadPoolExecutor to issue list_models() calls concurrently.
      - Only queries providers in SUPPORTED_LLM_SERVICE_TYPES (ordered).
      - A provider entry is included even if unconfigured, so the frontend
        can show "configure this provider" guidance.
      - user_preference is validated at call time; invalid preferences are
        returned as None (see RISK-02 in design.md §8).
    """
    # --- 1. Collect active configs keyed by service_type -------------------
    all_configs = UserServiceConfig.objects.filter(
        user=user,
        service_type__in=SUPPORTED_LLM_SERVICE_TYPES,
        is_active=True,
    ).order_by("-updated_at")

    config_map: dict[str, object] = {}
    for cfg in all_configs:
        # order_by ensures we keep the most-recent one per service_type
        if cfg.service_type not in config_map:
            config_map[cfg.service_type] = cfg

    # --- 2. Parallel model fetching ----------------------------------------
    # Submit one task per *configured* provider (unconfigured ones skip fetch).
    fetch_results: dict[str, tuple[list[dict], str, str | None]] = {}

    configured_types = [st for st in SUPPORTED_LLM_SERVICE_TYPES if st in config_map]
    if configured_types:
        max_workers = max(len(configured_types), 1)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_type = {
                pool.submit(_fetch_models_for_config, config_map[st]): st
                for st in configured_types
            }
            for future in as_completed(future_to_type):
                st = future_to_type[future]
                # _fetch_models_for_config only raises on unexpected errors;
                # we let those propagate (do NOT swallow arbitrary exceptions).
                fetch_results[st] = future.result()

    # --- 3. Build providers list (preserving SUPPORTED_LLM_SERVICE_TYPES order) ---
    providers_payload: list[dict] = []
    warnings: list[str] = []

    for service_type in SUPPORTED_LLM_SERVICE_TYPES:
        cfg = config_map.get(service_type)
        configured = cfg is not None
        last_test_ok = bool(cfg and cfg.last_validated_at is not None)

        if service_type in fetch_results:
            models, models_source, warn = fetch_results[service_type]
            if warn:
                warnings.append(warn)
        else:
            # Not configured or fetch not attempted — use fallback silently.
            models = MODEL_WHITELIST.get(service_type, [])
            models_source = "fallback"

        providers_payload.append(
            {
                "service_type": service_type,
                "label": PROVIDER_LABELS.get(service_type, service_type),
                "configured": configured,
                "last_test_ok": last_test_ok,
                "models_source": models_source,
                "models": models,
            }
        )

    # --- 4. Resolve user_preference ----------------------------------------
    user_preference = _resolve_user_preference(user, config_map)

    # --- 5. Compute system default -----------------------------------------
    default = _compute_system_default(config_map)

    return {
        "default": default,
        "user_preference": user_preference,
        "providers": providers_payload,
        "warnings": warnings,
    }


def _resolve_user_preference(user, config_map: dict) -> dict | None:
    """Return validated user_preference dict, or None if preference is invalid."""
    try:
        pref = user.llm_preference  # OneToOneField reverse accessor
    except UserLLMPreference.DoesNotExist:
        return None

    cfg = config_map.get(pref.service_type)
    pref_valid = cfg is not None and cfg.last_validated_at is not None
    if not pref_valid:
        return None

    return {"service_type": pref.service_type, "model": pref.model}


def _compute_system_default(config_map: dict) -> dict | None:
    """Compute the system-level default provider+model (ignores user preference).

    Decision chain (design.md §4.1):
      1. DeepSeek, if configured + last_validated_at IS NOT NULL
      2. Any other provider with last_validated_at IS NOT NULL, ordered by -updated_at
      3. None
    """
    # Priority 1: DeepSeek
    deepseek_cfg = config_map.get("llm_deepseek")
    if deepseek_cfg and deepseek_cfg.last_validated_at is not None:
        return {"service_type": "llm_deepseek", "model": "deepseek-chat"}

    # Priority 2: any validated provider (iterate in SUPPORTED order for determinism)
    for st in SUPPORTED_LLM_SERVICE_TYPES:
        cfg = config_map.get(st)
        if cfg and cfg.last_validated_at is not None:
            first_model = MODEL_WHITELIST.get(st, [{}])[0].get("id", "")
            return {"service_type": st, "model": first_model}

    return None


def resolve_default(user) -> tuple[str, str]:
    """Resolve the effective (service_type, model) for a user.

    Decision chain:
      1. Valid user preference (preference provider is configured + last_validated_at set)
      2. DeepSeek, if configured + validated
      3. Any other validated provider (SUPPORTED order)
      4. Raise NoAvailableProviderError

    Raises:
        NoAvailableProviderError: if no usable provider is found.
    """
    # Build config_map once (mirrors list_available_providers logic)
    all_configs = UserServiceConfig.objects.filter(
        user=user,
        service_type__in=SUPPORTED_LLM_SERVICE_TYPES,
        is_active=True,
    ).order_by("-updated_at")

    config_map: dict[str, object] = {}
    for cfg in all_configs:
        if cfg.service_type not in config_map:
            config_map[cfg.service_type] = cfg

    # Step 1: user preference
    try:
        pref = user.llm_preference  # OneToOneField reverse accessor (raises DoesNotExist if unset)
        pref_cfg = config_map.get(pref.service_type)
        if pref_cfg and pref_cfg.last_validated_at is not None:
            return (pref.service_type, pref.model)
    except UserLLMPreference.DoesNotExist:
        pass

    # Step 2: DeepSeek
    deepseek_cfg = config_map.get("llm_deepseek")
    if deepseek_cfg and deepseek_cfg.last_validated_at is not None:
        return ("llm_deepseek", "deepseek-chat")

    # Step 3: any other validated provider (SUPPORTED order)
    for st in SUPPORTED_LLM_SERVICE_TYPES:
        cfg = config_map.get(st)
        if cfg and cfg.last_validated_at is not None:
            first_model = MODEL_WHITELIST.get(st, [{}])[0].get("id", "")
            return (st, first_model)

    # Step 4: nothing available
    raise NoAvailableProviderError(
        "No usable LLM provider found for this user. "
        "Please configure and test an LLM API key in Settings."
    )


def validate_choice(user, service_type: str, model: str) -> None:  # noqa: D401
    """Validate a user-supplied (service_type, model) pair.

    Checks:
      1. service_type is in SUPPORTED_LLM_SERVICE_TYPES
      2. user has an active config for that service_type
      3. model is in the whitelist for that service_type

    Model validation uses only the whitelist (not a live API call) to avoid
    adding latency on the critical generate path.  This is the intended design
    (design.md §4.1 validate_choice note).

    Raises:
        InvalidChoiceError: with code INVALID_PROVIDER, PROVIDER_NOT_CONFIGURED,
                            or INVALID_MODEL.
    """
    # Guard 1: known service_type
    if service_type not in SUPPORTED_LLM_SERVICE_TYPES:
        raise InvalidChoiceError(
            code="INVALID_PROVIDER",
            message=f"不支持的 LLM 服务类型：{service_type}",
        )

    # Guard 2: user has an active config
    cfg = _get_user_service_config(user, service_type)
    if cfg is None:
        raise InvalidChoiceError(
            code="PROVIDER_NOT_CONFIGURED",
            message=f"用户未配置服务 {service_type}，请先在设置页面保存并测试 API Key",
        )

    # Guard 3: model in whitelist
    valid_model_ids = [m["id"] for m in MODEL_WHITELIST.get(service_type, [])]
    if model not in valid_model_ids:
        raise InvalidChoiceError(
            code="INVALID_MODEL",
            message=f"模型 {model!r} 不在 {service_type} 的可用列表中",
        )
