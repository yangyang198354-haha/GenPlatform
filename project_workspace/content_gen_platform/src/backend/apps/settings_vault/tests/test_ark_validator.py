"""
Unit tests for settings_vault.ark_validator — validate_doubao_key().

全部使用 Mock，不发起真实 HTTP 请求（-m "not integration"）。

覆盖：
  - 200 OK → (True, "")
  - 401 Unauthorized → (False, "ARK_KEY_INVALID")
  - 429 Too Many Requests → (False, "ARK_QUOTA_EXCEEDED")
  - 其他 HTTP 状态码（500）→ (False, "ARK_UNREACHABLE")
  - httpx.TimeoutException（重试耗尽后）→ (False, "ARK_UNREACHABLE")
  - httpx.ConnectError（重试耗尽后）→ (False, "ARK_UNREACHABLE")
  - 其他意外异常 → (False, "ARK_UNREACHABLE")
  - 安全守卫：api_key 不出现在错误消息 / 日志中（Canary 测试）

关联需求：FR-6.3、US-08 AC-08-3、ADR-08
"""
import pytest
from unittest.mock import patch, MagicMock

import httpx

from apps.settings_vault.ark_validator import validate_doubao_key, ARK_MODELS_URL


# ── helper ─────────────────────────────────────────────────────────────────────

def _mock_response(status_code: int) -> MagicMock:
    """构造带 status_code 的 Mock httpx.Response。"""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


# ── 200 OK：验证通过 ────────────────────────────────────────────────────────────

class TestValidateDoubaoKeySuccess:

    def test_200_returns_true_empty_error(self):
        """HTTP 200 → (True, "")，Key 有效。"""
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            return_value=_mock_response(200),
        ):
            ok, code = validate_doubao_key("valid-key-xxx")
        assert ok is True
        assert code == ""


# ── 认证/配额错误：立即返回，不重试 ─────────────────────────────────────────────

class TestValidateDoubaoKeyAuthErrors:

    def test_401_returns_ark_key_invalid(self):
        """HTTP 401 → (False, 'ARK_KEY_INVALID')，不重试。"""
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            return_value=_mock_response(401),
        ) as mock_call:
            ok, code = validate_doubao_key("bad-key")
        assert ok is False
        assert code == "ARK_KEY_INVALID"
        # 确保只调用了一次（无重试）
        mock_call.assert_called_once()

    def test_429_returns_ark_quota_exceeded(self):
        """HTTP 429 → (False, 'ARK_QUOTA_EXCEEDED')，不重试。"""
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            return_value=_mock_response(429),
        ) as mock_call:
            ok, code = validate_doubao_key("key-with-quota-issue")
        assert ok is False
        assert code == "ARK_QUOTA_EXCEEDED"
        mock_call.assert_called_once()

    def test_other_http_status_returns_unreachable(self):
        """HTTP 500 / 403 等 → (False, 'ARK_UNREACHABLE')。"""
        for status_code in [403, 500, 503]:
            with patch(
                "apps.settings_vault.ark_validator._call_ark_models",
                return_value=_mock_response(status_code),
            ):
                ok, code = validate_doubao_key("some-key")
            assert ok is False, f"HTTP {status_code} 应返回 False"
            assert code == "ARK_UNREACHABLE", f"HTTP {status_code} 应返回 ARK_UNREACHABLE"


# ── 网络错误：tenacity 重试耗尽后返回 ARK_UNREACHABLE ────────────────────────

class TestValidateDoubaoKeyNetworkErrors:

    def test_timeout_after_retries_returns_unreachable(self):
        """TimeoutException 重试耗尽 → (False, 'ARK_UNREACHABLE')。"""
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            ok, code = validate_doubao_key("timeout-key")
        assert ok is False
        assert code == "ARK_UNREACHABLE"

    def test_connect_error_after_retries_returns_unreachable(self):
        """ConnectError 重试耗尽 → (False, 'ARK_UNREACHABLE')。"""
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            ok, code = validate_doubao_key("connect-err-key")
        assert ok is False
        assert code == "ARK_UNREACHABLE"

    def test_unexpected_exception_returns_unreachable(self):
        """其他意外异常 → (False, 'ARK_UNREACHABLE')，不向上抛出。"""
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            side_effect=RuntimeError("unexpected"),
        ):
            ok, code = validate_doubao_key("some-key")
        assert ok is False
        assert code == "ARK_UNREACHABLE"


# ── 安全守卫：api_key 不出现在任何日志中（Canary 测试）────────────────────────

class TestValidateDoubaoKeySecurityGuard:
    """
    守卫测试：确保 validate_doubao_key 的日志输出中不包含 api_key 内容。

    使用唯一哨兵值 CANARY_KEY，捕获所有日志记录，
    断言日志消息中不出现该值（ADR-08 安全约束）。
    """

    CANARY_KEY = "sk-CANARY-SECRET-KEY-12345"

    def _collect_log_messages(self, caplog, mock_side_effect) -> list:
        import logging
        with patch(
            "apps.settings_vault.ark_validator._call_ark_models",
            side_effect=mock_side_effect,
        ):
            with caplog.at_level(logging.DEBUG, logger="apps.settings_vault.ark_validator"):
                validate_doubao_key(self.CANARY_KEY)
        return [record.message for record in caplog.records]

    def test_key_not_in_logs_on_401(self, caplog):
        """401 错误：日志中不包含 api_key 值。"""
        messages = self._collect_log_messages(caplog, _mock_response(401))
        for msg in messages:
            assert self.CANARY_KEY not in msg, (
                f"安全违规：api_key 出现在日志消息中: {msg!r}"
            )

    def test_key_not_in_logs_on_timeout(self, caplog):
        """超时错误：日志中不包含 api_key 值。"""
        messages = self._collect_log_messages(
            caplog, httpx.TimeoutException("timeout")
        )
        for msg in messages:
            assert self.CANARY_KEY not in msg, (
                f"安全违规：api_key 出现在日志消息中: {msg!r}"
            )

    def test_key_not_in_return_value_error_code(self):
        """返回值 error_code 字符串中不包含 api_key 内容。"""
        for side_effect in [
            _mock_response(401),
            _mock_response(429),
            httpx.TimeoutException("t"),
        ]:
            with patch(
                "apps.settings_vault.ark_validator._call_ark_models",
                side_effect=side_effect,
            ):
                _ok, code = validate_doubao_key(self.CANARY_KEY)
            assert self.CANARY_KEY not in code, (
                f"安全违规：api_key 出现在错误码中: {code!r}"
            )
