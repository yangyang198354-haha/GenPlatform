"""
豆包 Ark 图片生成客户端。

协议：OpenAI 兼容的 HTTP POST，Bearer Token 认证。
接口：https://ark.cn-beijing.volces.com/api/v3/images/generations

设计原则：
- 认证 Key 由调用方（Celery task）从 settings_vault 解密后传入，本模块不接触加密存储
- 所有日志语句中严禁记录 API Key 任何形式（NFR-3）
- 网络错误使用 tenacity 自动重试一次（ADR-07）
- 高级参数按 MODEL_ADVANCED_PARAMS 白名单过滤（ADR-05）

关联需求：FR-2、FR-3、NFR-3、NFR-5、ADR-01、ADR-05、ADR-07
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

logger = logging.getLogger(__name__)

# Ark 图片生成接口端点（固定，不从环境变量覆盖，以防误配置）
ARK_IMAGES_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

# HTTP 请求超时（秒）：豆包同步接口最长约数十秒，设置为 120 秒保守值
ARK_TIMEOUT_SECONDS = 120

# 各模型支持的高级参数白名单（ADR-05，按官方文档维护）
# 未来新增模型版本只需更新本常量，核心逻辑不变（NFR-5）
MODEL_ADVANCED_PARAMS: dict[str, set[str]] = {
    "Doubao-Seedream-5.0-lite": {"seed", "guidance_scale", "negative_prompt", "watermark"},
    "Doubao-Seedream-4.5": {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
    "Doubao-Seedream-4.0": {"seed", "guidance_scale", "negative_prompt", "steps", "watermark"},
}

# 支持的模型列表（与 MODEL_ADVANCED_PARAMS 保持同步）
SUPPORTED_MODELS: list[str] = list(MODEL_ADVANCED_PARAMS.keys())


@dataclass
class ImageGenerationResult:
    """Ark 图片生成调用的返回结果。"""

    image_urls: list[str] = field(default_factory=list)


# ── 自定义异常（ADR-07）────────────────────────────────────────────────────────

class DoubaoContentFilterError(Exception):
    """内容审核拒绝（Ark 返回 400 且 error.code 含 content_filter / sensitive）。"""


class DoubaoQuotaExceededError(Exception):
    """API 配额耗尽（Ark 返回 HTTP 429）。"""


class DoubaoAuthError(Exception):
    """认证失败（Ark 返回 HTTP 401）。"""


# ── 客户端主类 ─────────────────────────────────────────────────────────────────

class DoubaoImageClient:
    """
    豆包 Ark 图片生成客户端（OpenAI 兼容协议）。

    使用方式（在 Celery task 中）：
        client = DoubaoImageClient(api_key=decrypted_key)
        result = client.generate_images(
            prompt="日落时分的海边灯塔",
            model="Doubao-Seedream-4.5",
            n=2,
        )
        for url in result.image_urls:
            ...

    注意：
        - api_key 必须是已解密的明文字符串，由调用方从 settings_vault 获取
        - 禁止在任何地方将 api_key 写入日志
    """

    def __init__(self, api_key: str) -> None:
        # 仅存储，不记录日志
        self._api_key = api_key

    def generate_images(
        self,
        prompt: str,
        model: str,
        n: int = 1,
        size: str = "1024x1024",
        ref_image_b64: Optional[str] = None,
        advanced_params: Optional[dict] = None,
    ) -> ImageGenerationResult:
        """
        调用 Ark 接口生成图片（同步调用，Ark 直接返回结果 URL，无需轮询）。

        参数：
            prompt: 提示词（1-500 字符，调用方负责校验）
            model: 豆包模型版本（须在 SUPPORTED_MODELS 内，调用方负责校验）
            n: 生成张数（1-4，调用方负责校验）
            size: 图片尺寸，如 "1024x1024"、"1280x720"、"720x1280"
            ref_image_b64: base64 编码的参考图（图生图），格式 "data:image/jpeg;base64,..."
            advanced_params: 高级参数字典（函数内部按 MODEL_ADVANCED_PARAMS 白名单过滤）

        返回：
            ImageGenerationResult，其中 image_urls 为生成图片的 URL 列表

        异常：
            DoubaoContentFilterError: 内容审核拒绝
            DoubaoQuotaExceededError: API 配额耗尽
            DoubaoAuthError: API Key 无效
            RuntimeError: 其他 HTTP 错误或响应格式异常
        """
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            ref_image_b64=ref_image_b64,
            advanced_params=advanced_params or {},
        )

        # 记录调用信息（不含 Key，不含完整请求体中的 api_key 字段）
        logger.info(
            "调用豆包 Ark 图片生成接口：model=%s n=%d size=%s is_img2img=%s",
            model,
            n,
            size,
            ref_image_b64 is not None,
        )

        raw_response = self._post_with_retry(body)
        image_urls = self._parse_response(raw_response)

        logger.info("豆包 Ark 返回 %d 张图片 URL", len(image_urls))
        return ImageGenerationResult(image_urls=image_urls)

    def _build_request_body(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str,
        ref_image_b64: Optional[str],
        advanced_params: dict,
    ) -> dict:
        """
        组装 Ark 接口请求体。

        按 MODEL_ADVANCED_PARAMS 白名单过滤高级参数，
        仅传入目标模型实际支持的字段（ADR-05）。
        """
        body: dict = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "response_format": "url",
        }

        # 图生图：添加参考图 base64（data URI 格式）
        if ref_image_b64:
            body["image_url"] = ref_image_b64

        # 高级参数过滤（按当前模型支持的白名单）
        allowed_keys = MODEL_ADVANCED_PARAMS.get(model, set())
        for key, value in advanced_params.items():
            if key in allowed_keys and value is not None:
                body[key] = value

        return body

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(5),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    def _post_with_retry(self, body: dict) -> dict:
        """
        执行 HTTP POST 到 Ark 接口。

        网络超时或连接失败时，tenacity 自动等待 5 秒后重试一次（ADR-07）。
        其他错误（4xx、5xx）不触发重试，由 _handle_error_response 处理。
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=ARK_TIMEOUT_SECONDS) as client:
            resp = client.post(ARK_IMAGES_URL, json=body, headers=headers)

        if resp.status_code != 200:
            self._handle_error_response(resp)

        return resp.json()

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """
        将 Ark HTTP 错误响应映射为对应异常类型（ADR-07）。

        错误分类：
        - 401 → DoubaoAuthError
        - 429 → DoubaoQuotaExceededError
        - 400 且含 content_filter/sensitive → DoubaoContentFilterError
        - 其他 → RuntimeError（含状态码和响应摘要）
        """
        status_code = resp.status_code
        # 尝试解析响应体，获取错误详情
        try:
            error_data = resp.json()
            error_code = error_data.get("error", {}).get("code", "")
            error_message = error_data.get("error", {}).get("message", "")
        except Exception:
            error_code = ""
            error_message = resp.text[:200]

        if status_code == 401:
            raise DoubaoAuthError("豆包 API Key 无效，请重新配置")

        if status_code == 429:
            raise DoubaoQuotaExceededError("豆包 API 配额已耗尽，请检查账户余额")

        if status_code == 400:
            # 判断是否为内容审核拒绝
            content_filter_signals = ("content_filter", "sensitive", "审核", "违规")
            is_content_filter = any(
                s in error_code.lower() or s in error_message.lower()
                for s in content_filter_signals
            )
            if is_content_filter:
                raise DoubaoContentFilterError("提示词包含不允许的内容，请修改后重试")
            raise RuntimeError(f"请求参数有误，请检查输入（{status_code}: {error_message}）")

        # 5xx 或其他错误
        raise RuntimeError(
            f"豆包服务暂时不可用，请稍后重试（HTTP {status_code}: {error_message}）"
        )

    def _parse_response(self, data: dict) -> list[str]:
        """
        从 Ark 响应体中解析图片 URL 列表。

        Ark 响应格式（OpenAI 兼容）：
        {
            "data": [{"url": "https://..."}, {"url": "https://..."}, ...]
        }
        """
        items = data.get("data", [])
        urls = [item.get("url") for item in items if item.get("url")]
        if not urls:
            raise RuntimeError(f"豆包 Ark 返回了空的图片列表，原始响应：{str(data)[:200]}")
        return urls
