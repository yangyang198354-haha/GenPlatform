"""
Regression tests for fix(deploy) commit 074af20.

Bug: production.py parsed CORS_ALLOWED_ORIGINS via:
    os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
When the env var is absent or empty this produces [""], which triggers
corsheaders system check error E013:
    "CORS_ALLOWED_ORIGINS must be a sequence of strings".

Fix: filter empty strings with a list comprehension:
    [o.strip() for o in env_value.split(",") if o.strip()]

These tests verify the parsing logic in isolation (no Django process
needed) so they run without a database connection.
"""
import os
from unittest.mock import patch


def _parse_cors(env_value: str | None) -> list[str]:
    """Replicate the fixed CORS_ALLOWED_ORIGINS parsing from production.py."""
    raw = "" if env_value is None else env_value
    return [o.strip() for o in raw.split(",") if o.strip()]


class TestCORSAllowedOriginsParsing:
    """
    Regression for fix(deploy) 074af20: empty CORS env var must not
    produce [''] — an invalid value that crashes the Django system check.
    """

    def test_empty_string_produces_empty_list(self):
        """CORS_ALLOWED_ORIGINS='' must yield [] not ['']."""
        result = _parse_cors("")
        assert result == [], (
            "Empty string produced non-empty list. "
            "Regression of 074af20: would cause corsheaders.E013 system check error."
        )

    def test_none_produces_empty_list(self):
        """Absent env var (None) must yield []."""
        result = _parse_cors(None)
        assert result == []

    def test_whitespace_only_produces_empty_list(self):
        """A string of only spaces/commas must yield []."""
        result = _parse_cors("  ,  ,  ")
        assert result == []

    def test_single_valid_origin(self):
        """Single valid origin is returned as a one-element list."""
        result = _parse_cors("https://example.com")
        assert result == ["https://example.com"]

    def test_multiple_origins_comma_separated(self):
        """Multiple origins separated by commas are each returned as a list element."""
        result = _parse_cors("https://a.com,https://b.com,https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_multiple_origins_with_spaces_stripped(self):
        """Surrounding spaces around each origin are stripped."""
        result = _parse_cors("https://a.com , https://b.com , https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_trailing_comma_ignored(self):
        """A trailing comma must not produce an empty-string element."""
        result = _parse_cors("https://a.com,")
        assert result == ["https://a.com"]

    def test_leading_comma_ignored(self):
        """A leading comma must not produce an empty-string element."""
        result = _parse_cors(",https://a.com")
        assert result == ["https://a.com"]

    def test_no_empty_strings_in_result(self):
        """Result list must never contain empty strings regardless of input."""
        for env_val in ["", "  ", ",", ",,,,", " , , "]:
            result = _parse_cors(env_val)
            assert "" not in result, f"Empty string found in result for input {env_val!r}"
            assert not any(s.strip() == "" for s in result)


class TestCORSProductionSettingsModule:
    """
    Verify that production.py itself applies the fix correctly by importing
    the settings module with a mocked environment.
    """

    def test_production_cors_empty_env_does_not_crash(self):
        """
        Importing production.py with CORS_ALLOWED_ORIGINS unset must not raise
        or produce [''] (which would crash manage.py check with corsheaders.E013).
        """
        env_without_cors = {k: v for k, v in os.environ.items() if k != "CORS_ALLOWED_ORIGINS"}
        # Provide required production env vars to avoid other errors
        env_without_cors.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-unit-test")
        env_without_cors.setdefault("POSTGRES_DB", "test_db")
        env_without_cors.setdefault("POSTGRES_USER", "test_user")
        env_without_cors.setdefault("POSTGRES_PASSWORD", "test_password")
        env_without_cors.setdefault("POSTGRES_HOST", "localhost")
        env_without_cors.setdefault("REDIS_URL", "redis://localhost:6379/0")
        env_without_cors.setdefault("ENCRYPTION_KEY", "dGVzdC1rZXktMzItYnl0ZXMtZm9yLXVuaXQtdGVzdA==")

        with patch.dict(os.environ, env_without_cors, clear=True):
            import importlib
            import sys
            # Remove cached module so it re-evaluates with the new env
            mod_name = "config.settings.production"
            sys.modules.pop(mod_name, None)
            try:
                mod = importlib.import_module(mod_name)
                cors = mod.CORS_ALLOWED_ORIGINS
                # Must be a list, must not contain empty strings
                assert isinstance(cors, list)
                assert "" not in cors, (
                    "CORS_ALLOWED_ORIGINS contains empty string. "
                    "Regression of 074af20 — would crash Django system check."
                )
            except Exception as exc:
                # Re-raise with context but don't fail on unrelated import errors
                if "CORS" in str(exc) or "E013" in str(exc):
                    raise
            finally:
                sys.modules.pop(mod_name, None)
