"""
Ark API Key 有效性验证模块。

安全约束（ADR-08，FR-6.3）：
  - api_key 参数禁止出现在任何日志语句中。
  - 异常消息禁止包含 api_key 内容。
  - 本模块不做任何持久化操作（单一职责：仅验证）。
  - 重试策略：仅对网络错误（超时/连接失败）重试，认证/配额错误立即返回。

关联需求：FR-6.3、US-08 AC-08-3、ADR-08
"""
import logging
from typing import Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

ARK_MODELS_URL = "https://ark.cn-beijing.volces.com/api/v3/models"
VALIDATE_TIMEOUT = 10.0  # 秒，防止 Ark 不可达时长时阻塞

# 仅对网络层错误重试（最多 2 次额外尝试，共 3 次）
# 认证错误（401/403）不在重试范围内，调用 validate_doubao_key 前已处理
_NETWORK_ERRORS = (httpx.TimeoutException, httpx.ConnectError)


@retry(
    retry=retry_if_exception_type(_NETWORK_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)
def _call_ark_models(api_key: str) -> httpx.Response:
    """
    发送 GET /api/v3/models 请求并返回原始 Response 对象。

    仅对网络错误（TimeoutException / ConnectError）触发 tenacity 重试。
    HTTP 4xx/5xx 不重试，由调用方根据状态码决策。

    安全约束：api_key 不出现在任何异常或日志消息中。
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    return httpx.get(ARK_MODELS_URL, headers=headers, timeout=VALIDATE_TIMEOUT)


def validate_doubao_key(api_key: str) -> Tuple[bool, str]:
    """
    调用 Ark GET /api/v3/models 接口验证 API Key 有效性。

    参数：
        api_key: 待验证的 Ark API Key（来自 settings_vault 解密或用户输入；禁止记录到日志）

    返回：
        Tuple[bool, str]
            - (True, "")                     — Key 有效
            - (False, "ARK_KEY_INVALID")     — HTTP 401，Key 无效或已吊销
            - (False, "ARK_QUOTA_EXCEEDED")  — HTTP 429，账号超配额或受限
            - (False, "ARK_UNREACHABLE")     — 网络错误、超时、其他 HTTP 错误

    说明：
        本函数不抛出异常，所有错误均映射为返回值元组。
        重试策略：网络层错误（超时/连接失败）最多重试 2 次，共 3 次调用。
        认证错误（401）和配额错误（429）不重试，直接返回对应错误码。
        关联 ADR-08 中的错误映射表。
    """
    try:
        response = _call_ark_models(api_key)

        if response.status_code == 200:
            logger.info("Ark key validation succeeded")
            return True, ""

        if response.status_code == 401:
            # 认证失败：Key 无效或已吊销，不重试
            logger.info("Ark key validation failed: 401 Unauthorized (key invalid or revoked)")
            return False, "ARK_KEY_INVALID"

        if response.status_code == 429:
            # 配额超限：不重试（重试无意义）
            logger.info("Ark key validation failed: 429 Too Many Requests (quota exceeded)")
            return False, "ARK_QUOTA_EXCEEDED"

        # 其他状态码（403/5xx 等）映射为 ARK_UNREACHABLE
        logger.warning("Ark key validation failed: HTTP %d", response.status_code)
        return False, "ARK_UNREACHABLE"

    except _NETWORK_ERRORS as exc:
        # tenacity 重试耗尽后仍抛出的网络错误（reraise=True）
        # 安全约束：只记录异常类型，不记录 api_key
        logger.warning(
            "Ark key validation: network error after retries: %s",
            type(exc).__name__,
        )
        return False, "ARK_UNREACHABLE"

    except Exception as exc:  # noqa: BLE001
        # 其他意外错误（如 httpx 内部错误），只记录类型名，不记录 Key
        logger.error(
            "Ark key validation: unexpected error: %s",
            type(exc).__name__,
        )
        return False, "ARK_UNREACHABLE"
