"""
DoubaoImageClient 单元测试。

测试内容：
- generate_images() 成功路径
- _build_request_body() 高级参数过滤（ADR-05）
- _handle_error_response() 各错误码映射（ADR-07）
- tenacity 重试行为（网络错误时重试，4xx 不重试）

所有 httpx.Client 均被 mock，不发起真实 HTTP 请求。
"""
import pytest
from unittest.mock import MagicMock, patch

import httpx

from apps.image_generator.doubao_image_client import (
    ARK_IMAGES_URL,
    MODEL_ADVANCED_PARAMS,
    SUPPORTED_MODELS,
    DoubaoAuthError,
    DoubaoContentFilterError,
    DoubaoImageClient,
    DoubaoQuotaExceededError,
    ImageGenerationResult,
)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _make_client():
    """创建测试用客户端，API Key 不写入日志（NFR-3）。"""
    return DoubaoImageClient(api_key="test-key-do-not-log")


def _mock_response(status_code: int, json_data: dict):
    """构造 mock httpx.Response。"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


# ── 成功路径测试 ──────────────────────────────────────────────────────────────

class TestDoubaoImageClientSuccess:

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_generate_images_single(self, mock_http_class):
        """单张图片生成成功，返回 ImageGenerationResult 含 1 个 URL。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        mock_resp = _mock_response(200, {"data": [{"url": "https://ark.example.com/img1.jpg"}]})
        mock_http.post.return_value = mock_resp

        client = _make_client()
        result = client.generate_images(
            prompt="日落时分的海边灯塔",
            model="doubao-seedream-4-5-251128",
            n=1,
        )

        assert isinstance(result, ImageGenerationResult)
        assert len(result.image_urls) == 1
        assert result.image_urls[0] == "https://ark.example.com/img1.jpg"

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_generate_images_multiple(self, mock_http_class):
        """多张图片（n=4）成功，返回 4 个 URL（ADR-03 优先方案）。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        urls = [f"https://ark.example.com/img{i}.jpg" for i in range(4)]
        mock_resp = _mock_response(200, {"data": [{"url": u} for u in urls]})
        mock_http.post.return_value = mock_resp

        client = _make_client()
        result = client.generate_images(
            prompt="山水画",
            model="doubao-seedream-4-5-251128",
            n=4,
        )

        assert len(result.image_urls) == 4
        assert result.image_urls == urls

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_request_body_contains_bearer_token(self, mock_http_class):
        """HTTP 请求头中必须包含 Bearer Token，且不包含 api_key 明文（NFR-3）。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        mock_resp = _mock_response(200, {"data": [{"url": "https://example.com/img.jpg"}]})
        mock_http.post.return_value = mock_resp

        client = DoubaoImageClient(api_key="my-secret-key")
        client.generate_images(prompt="test", model="doubao-seedream-4-5-251128")

        call_kwargs = mock_http.post.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer my-secret-key"


# ── 各模型版本独立测试（FR-1：三个模型版本均可调用）──────────────────────────

class TestDoubaoImageClientModelVersions:
    """三个豆包模型版本独立生成路径测试（FR-1，ADR-05）。"""

    def _setup_mock(self, mock_http_class, image_count=1):
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http
        urls = [f"https://ark.example.com/img{i}.jpg" for i in range(image_count)]
        mock_resp = _mock_response(200, {"data": [{"url": u} for u in urls]})
        mock_http.post.return_value = mock_resp
        return mock_http

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_generate_with_50_lite_model(self, mock_http_class):
        """doubao-seedream-5-0-260128 模型生成成功（FR-1）。"""
        mock_http = self._setup_mock(mock_http_class)
        client = _make_client()
        result = client.generate_images(
            prompt="测试 5.0-lite", model="doubao-seedream-5-0-260128", n=1
        )
        assert len(result.image_urls) == 1
        # 验证请求体 model 字段正确
        call_kwargs = mock_http.post.call_args[1]
        assert call_kwargs["json"]["model"] == "doubao-seedream-5-0-260128"

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_generate_with_45_model(self, mock_http_class):
        """doubao-seedream-4-5-251128 模型生成成功（FR-1）。"""
        mock_http = self._setup_mock(mock_http_class)
        client = _make_client()
        result = client.generate_images(
            prompt="测试 4.5", model="doubao-seedream-4-5-251128", n=2
        )
        assert len(result.image_urls) == 1  # mock 返回 1 个

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_generate_with_40_model(self, mock_http_class):
        """doubao-seedream-4-0-250828 模型生成成功（FR-1）。"""
        mock_http = self._setup_mock(mock_http_class)
        client = _make_client()
        result = client.generate_images(
            prompt="测试 4.0", model="doubao-seedream-4-0-250828", n=1
        )
        assert len(result.image_urls) == 1
        call_kwargs = mock_http.post.call_args[1]
        assert call_kwargs["json"]["model"] == "doubao-seedream-4-0-250828"


# ── 高级参数过滤测试（ADR-05）────────────────────────────────────────────────

class TestDoubaoImageClientAdvancedParams:

    def test_build_request_body_filters_unsupported_params_lite(self):
        """doubao-seedream-5-0-260128 不支持 steps，应被过滤掉（ADR-05）。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-5-0-260128",
            n=1,
            size="2048x2048",
            ref_image_b64=None,
            advanced_params={"seed": 42, "steps": 50, "guidance_scale": 7.5},
        )
        assert "seed" in body
        assert "guidance_scale" in body
        assert "steps" not in body  # 5.0-lite 不支持

    def test_build_request_body_allows_steps_for_45(self):
        """doubao-seedream-4-5-251128 支持 steps，应被保留（ADR-05）。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="2048x2048",
            ref_image_b64=None,
            advanced_params={"seed": 42, "steps": 30},
        )
        assert "steps" in body
        assert body["steps"] == 30

    def test_build_request_body_none_values_excluded(self):
        """None 值的高级参数不应出现在请求体中。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="2048x2048",
            ref_image_b64=None,
            advanced_params={"seed": None, "guidance_scale": 7.5},
        )
        assert "seed" not in body
        assert "guidance_scale" in body

    def test_build_request_body_includes_ref_image(self):
        """图生图时，请求体中应包含 image_url（FR-3）。"""
        client = _make_client()
        ref_b64 = "data:image/jpeg;base64,/9j/test=="
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="2048x2048",
            ref_image_b64=ref_b64,
            advanced_params={},
        )
        assert body["image_url"] == ref_b64

    def test_supported_models_list_completeness(self):
        """SUPPORTED_MODELS 应包含三个豆包 Seedream 版本（FR-1）。"""
        assert "doubao-seedream-5-0-260128" in SUPPORTED_MODELS
        assert "doubao-seedream-4-5-251128" in SUPPORTED_MODELS
        assert "doubao-seedream-4-0-250828" in SUPPORTED_MODELS
        assert len(SUPPORTED_MODELS) == 3

    # ── v1.2 Canary 守卫测试（防止关键参数默认值漂移）──────────────────────────

    def test_canary_model_50_lite_steps_not_in_whitelist(self):
        """
        【Canary 守卫 TC-CLIENT-01】5.0-lite 的 MODEL_ADVANCED_PARAMS 中不含 steps。

        如果有人错误地在白名单中加入 steps，此测试会立即报警。
        """
        params_50_lite = MODEL_ADVANCED_PARAMS.get("doubao-seedream-5-0-260128", set())
        assert "steps" not in params_50_lite, (
            "5.0-lite 不支持 steps，MODEL_ADVANCED_PARAMS 中不应包含，"
            "如需修改请同步更新文档和测试"
        )

    def test_canary_model_45_steps_in_whitelist(self):
        """
        【Canary 守卫 TC-CLIENT-02】4.5 的 MODEL_ADVANCED_PARAMS 应包含 steps。

        如果有人错误地从白名单移除 steps，此测试会立即报警。
        """
        params_45 = MODEL_ADVANCED_PARAMS.get("doubao-seedream-4-5-251128", set())
        assert "steps" in params_45, (
            "4.5 支持 steps，MODEL_ADVANCED_PARAMS 中应包含"
        )

    def test_canary_guidance_scale_in_all_models(self):
        """
        【Canary 守卫 TC-CLIENT-03】guidance_scale 应在所有模型的白名单中。
        """
        for model_id, params in MODEL_ADVANCED_PARAMS.items():
            assert "guidance_scale" in params, (
                f"模型 {model_id} 的 MODEL_ADVANCED_PARAMS 缺少 guidance_scale"
            )

    def test_canary_seed_in_all_models(self):
        """
        【Canary 守卫 TC-CLIENT-04】seed 应在所有模型的白名单中（复现能力守卫）。
        """
        for model_id, params in MODEL_ADVANCED_PARAMS.items():
            assert "seed" in params, (
                f"模型 {model_id} 的 MODEL_ADVANCED_PARAMS 缺少 seed（影响结果复现能力）"
            )

    def test_canary_watermark_in_all_models(self):
        """
        【Canary 守卫 TC-CLIENT-05】watermark 应在所有模型的白名单中。
        """
        for model_id, params in MODEL_ADVANCED_PARAMS.items():
            assert "watermark" in params, (
                f"模型 {model_id} 的 MODEL_ADVANCED_PARAMS 缺少 watermark"
            )

    def test_build_request_body_guidance_scale_passes_through(self):
        """TC-CLIENT-06: guidance_scale=8.0 → 请求体含 'guidance_scale': 8.0。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="2048x2048",
            ref_image_b64=None,
            advanced_params={"guidance_scale": 8.0},
        )
        assert body.get("guidance_scale") == 8.0

    def test_build_request_body_seed_passes_through(self):
        """TC-CLIENT-07: seed=12345 → 请求体含 'seed': 12345（复现能力守卫）。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="2048x2048",
            ref_image_b64=None,
            advanced_params={"seed": 12345},
        )
        assert body.get("seed") == 12345

    def test_build_request_body_watermark_true_passes_through(self):
        """TC-CLIENT-08: watermark=True → 请求体含 'watermark': True。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="2048x2048",
            ref_image_b64=None,
            advanced_params={"watermark": True},
        )
        assert body.get("watermark") is True

    def test_build_request_body_size_field_always_present(self):
        """TC-CLIENT-09: 请求体始终包含 size 字段（PR #7 教训：不能省略）。"""
        client = _make_client()
        body = client._build_request_body(
            prompt="test",
            model="doubao-seedream-4-5-251128",
            n=1,
            size="3840x2160",
            ref_image_b64=None,
            advanced_params={},
        )
        assert body.get("size") == "3840x2160"


# ── 错误处理测试（ADR-07）───────────────────────────────────────────────────

class TestDoubaoImageClientErrorHandling:

    def test_handle_401_raises_auth_error(self):
        """401 响应应抛出 DoubaoAuthError（ADR-07）。"""
        client = _make_client()
        resp = _mock_response(401, {"error": {"code": "auth_failed", "message": "Unauthorized"}})
        with pytest.raises(DoubaoAuthError):
            client._handle_error_response(resp)

    def test_handle_429_raises_quota_error(self):
        """429 响应应抛出 DoubaoQuotaExceededError（ADR-07）。"""
        client = _make_client()
        resp = _mock_response(429, {"error": {"code": "rate_limit", "message": "Too Many Requests"}})
        with pytest.raises(DoubaoQuotaExceededError):
            client._handle_error_response(resp)

    def test_handle_400_content_filter_raises_content_filter_error(self):
        """400 + content_filter 错误码应抛出 DoubaoContentFilterError（ADR-07）。"""
        client = _make_client()
        resp = _mock_response(400, {
            "error": {"code": "content_filter", "message": "Prompt contains sensitive content"}
        })
        with pytest.raises(DoubaoContentFilterError):
            client._handle_error_response(resp)

    def test_handle_400_sensitive_in_message_raises_content_filter_error(self):
        """400 + 消息含 'sensitive' 也应识别为内容审核拒绝。"""
        client = _make_client()
        resp = _mock_response(400, {
            "error": {"code": "invalid_request", "message": "sensitive content detected"}
        })
        with pytest.raises(DoubaoContentFilterError):
            client._handle_error_response(resp)

    def test_handle_400_param_error_raises_runtime_error(self):
        """400 + 非内容审核原因应抛出 RuntimeError（ADR-07）。"""
        client = _make_client()
        resp = _mock_response(400, {
            "error": {"code": "invalid_param", "message": "Bad parameter"}
        })
        with pytest.raises(RuntimeError) as exc_info:
            client._handle_error_response(resp)
        assert "参数" in str(exc_info.value)

    def test_handle_403_raises_runtime_error(self):
        """403 权限拒绝应抛出 RuntimeError（ADR-07，非 401/429 的 4xx 走通用错误路径）。"""
        client = _make_client()
        resp = _mock_response(403, {"error": {"code": "forbidden", "message": "Permission denied"}})
        with pytest.raises(RuntimeError):
            client._handle_error_response(resp)

    def test_handle_500_raises_runtime_error(self):
        """500 服务端错误应抛出 RuntimeError（ADR-07）。"""
        client = _make_client()
        resp = _mock_response(500, {"error": {"code": "server_error", "message": "Internal Error"}})
        with pytest.raises(RuntimeError) as exc_info:
            client._handle_error_response(resp)
        assert "服务" in str(exc_info.value)

    def test_handle_503_raises_runtime_error(self):
        """503 服务不可用应抛出 RuntimeError（ADR-07，5xx 统一处理）。"""
        client = _make_client()
        resp = _mock_response(503, {"error": {"code": "service_unavailable", "message": "Service Unavailable"}})
        with pytest.raises(RuntimeError) as exc_info:
            client._handle_error_response(resp)
        assert "服务" in str(exc_info.value)

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_empty_data_raises_runtime_error(self, mock_http_class):
        """Ark 返回空 data 数组时应抛出 RuntimeError。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        mock_resp = _mock_response(200, {"data": []})  # 空数组
        mock_http.post.return_value = mock_resp

        client = _make_client()
        with pytest.raises(RuntimeError) as exc_info:
            client.generate_images(prompt="test", model="doubao-seedream-4-5-251128")
        assert "空" in str(exc_info.value) or "URL" in str(exc_info.value)


# ── tenacity 重试行为测试（ADR-07）──────────────────────────────────────────

class TestDoubaoImageClientRetry:

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_retry_on_network_error_eventually_succeeds(self, mock_http_class):
        """网络错误重试一次后成功（tenacity，ADR-07）。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        success_resp = _mock_response(200, {"data": [{"url": "https://example.com/img.jpg"}]})
        # 第一次超时，第二次成功
        mock_http.post.side_effect = [
            httpx.TimeoutException("timeout"),
            success_resp,
        ]

        client = _make_client()
        # tenacity wait_fixed(5) 在测试中会真实等待，使用 patch 跳过等待
        with patch("time.sleep", return_value=None):
            result = client.generate_images(prompt="test", model="doubao-seedream-4-5-251128")

        assert len(result.image_urls) == 1

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_no_retry_on_auth_error(self, mock_http_class):
        """认证失败不触发 tenacity 重试（4xx 不在重试条件中，ADR-07）。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        auth_resp = _mock_response(401, {"error": {"code": "auth_failed", "message": ""}})
        mock_http.post.return_value = auth_resp

        client = _make_client()
        with pytest.raises(DoubaoAuthError):
            client.generate_images(prompt="test", model="doubao-seedream-4-5-251128")

        # 只调用了一次，没有重试
        assert mock_http.post.call_count == 1

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_retry_on_connect_error_eventually_succeeds(self, mock_http_class):
        """网络连接错误重试一次后成功（ConnectError，ADR-07）。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        success_resp = _mock_response(200, {"data": [{"url": "https://example.com/img.jpg"}]})
        mock_http.post.side_effect = [
            httpx.ConnectError("connection refused"),
            success_resp,
        ]

        client = _make_client()
        with patch("time.sleep", return_value=None):
            result = client.generate_images(prompt="test", model="doubao-seedream-4-0-250828")

        assert len(result.image_urls) == 1
        assert mock_http.post.call_count == 2

    @patch("apps.image_generator.doubao_image_client.httpx.Client")
    def test_retry_exhausted_raises_timeout(self, mock_http_class):
        """连续两次超时后 tenacity 耗尽，应抛出 httpx.TimeoutException（ADR-07 重试停止）。"""
        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http_class.return_value = mock_http

        mock_http.post.side_effect = httpx.TimeoutException("timeout")

        client = _make_client()
        with patch("time.sleep", return_value=None):
            with pytest.raises(httpx.TimeoutException):
                client.generate_images(prompt="test", model="doubao-seedream-4-5-251128")

        # tenacity stop_after_attempt(2)：共调用 2 次
        assert mock_http.post.call_count == 2
