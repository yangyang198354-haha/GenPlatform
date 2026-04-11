"""Unit tests for llm_gateway.views — GenerateContentView."""
import json
import pytest
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt
from apps.settings_vault.models import UserServiceConfig

User = get_user_model()

GENERATE_URL = "/api/v1/llm/generate/"


# ── helpers ────────────────────────────────────────────────────────────────

def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


def _create_llm_config(user, api_key="sk-fake"):
    """Create an active DeepSeek config for a user."""
    return UserServiceConfig.objects.create(
        user=user,
        service_type="llm_deepseek",
        encrypted_config=encrypt({"api_key": api_key}),
        is_active=True,
    )


def _collect_sse(response):
    """Collect and parse all SSE events from a StreamingHttpResponse."""
    raw = b"".join(response.streaming_content).decode()
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


# ── test cases ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGenerateContentView:

    def test_generate_requires_auth(self, api_client):
        """Unauthenticated GET must return 401."""
        resp = api_client.get(GENERATE_URL, {"prompt": "hello"})
        assert resp.status_code == 401

    def test_generate_no_llm_config(self, user, db):
        """Authenticated user with no LLM config must receive 400 with error field."""
        client = _auth_client(user)
        resp = client.get(GENERATE_URL, {"prompt": "write something"})
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_generate_empty_prompt(self, user, db):
        """Empty prompt must return 400 even when LLM config exists."""
        # Create a minimal (fake) LLM config so the view doesn't fail on config lookup first
        _create_llm_config(user)
        client = _auth_client(user)
        resp = client.get(GENERATE_URL, {"prompt": "   "})
        assert resp.status_code == 400
        assert "error" in resp.data


# ── Regression: aeb6fe4 — DRF 406 on text/event-stream Accept header ───────

@pytest.mark.django_db
class TestSSEContentNegotiation:
    """
    Regression for aeb6fe4: bypass DRF content negotiation to fix 406.

    DRF's perform_content_negotiation() rejects Accept: text/event-stream
    because text/event-stream is not a registered DRF renderer.
    The fix overrides perform_content_negotiation() to skip the check.
    These tests ensure the 406 never comes back.
    """

    def _fake_provider(self, tokens=("hello", " world")):
        async def _stream(messages, max_tokens=2048):
            for t in tokens:
                yield t

        provider = MagicMock()
        provider.stream_chat = _stream
        return provider

    def test_accept_text_event_stream_returns_200(self, user, db):
        """GET with Accept: text/event-stream must return 200, not 406."""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch("apps.llm_gateway.views.get_provider", return_value=self._fake_provider()):
            resp = client.get(
                GENERATE_URL,
                {"prompt": "write something"},
                HTTP_ACCEPT="text/event-stream",
            )

        assert resp.status_code == 200, (
            f"Expected 200 (SSE), got {resp.status_code}. "
            "Possible regression of aeb6fe4 — DRF 406 on SSE Accept header."
        )

    def test_sse_response_content_type(self, user, db):
        """Streaming response Content-Type must be text/event-stream."""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch("apps.llm_gateway.views.get_provider", return_value=self._fake_provider()):
            resp = client.get(GENERATE_URL, {"prompt": "test"})

        assert "text/event-stream" in resp.get("Content-Type", "")

    def test_sse_response_contains_token_events(self, user, db):
        """Each token from the provider must appear as a data: event with done=False."""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch("apps.llm_gateway.views.get_provider", return_value=self._fake_provider(["tok1", "tok2"])):
            resp = client.get(GENERATE_URL, {"prompt": "test"})

        events = _collect_sse(resp)
        token_events = [e for e in events if not e.get("done", False)]
        tokens = [e["token"] for e in token_events]
        assert "tok1" in tokens
        assert "tok2" in tokens

    def test_sse_last_event_has_done_true(self, user, db):
        """The final SSE event must have done=True to signal stream completion."""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch("apps.llm_gateway.views.get_provider", return_value=self._fake_provider(["x"])):
            resp = client.get(GENERATE_URL, {"prompt": "test"})

        events = _collect_sse(resp)
        assert events, "No SSE events received"
        assert events[-1].get("done") is True, "Last event must have done=True"

    def test_default_accept_header_also_returns_200(self, user, db):
        """Default Accept: */* (DRF default) must also return 200 — no regression."""
        _create_llm_config(user)
        client = _auth_client(user)

        with patch("apps.llm_gateway.views.get_provider", return_value=self._fake_provider()):
            resp = client.get(GENERATE_URL, {"prompt": "hello"})

        assert resp.status_code == 200


# ── Regression: a70b0d2 — SSE stream never resolving on exception ──────────

class TestSSEStreamErrorHandling:
    """
    Regression for a70b0d2: _sync_sse_generator must always terminate.

    Before the fix, an exception inside _run() async generator caused the
    SSE stream to close without sending a final {done:true} event.  The
    frontend would stay permanently in the "生成中" state.

    Fix: wrap the async for loop in try/except and yield a
    {done:true, error:<message>} event before exiting.
    """

    def test_provider_exception_yields_done_error_event(self):
        """When stream_chat raises, the last SSE event must have done=True and error field."""
        from apps.llm_gateway.views import _sync_sse_generator

        class BrokenProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                raise RuntimeError("upstream API is down")
                yield  # make it a proper async generator

        chunks = list(_sync_sse_generator(BrokenProvider(), [{"role": "user", "content": "hi"}], []))

        assert chunks, "_sync_sse_generator must yield at least one chunk even on error"
        last = json.loads(chunks[-1].replace("data:", "").strip())
        assert last.get("done") is True, "Last event must have done=True"
        assert "error" in last, "Error event must contain 'error' field"

    def test_provider_exception_error_contains_message(self):
        """The error field must contain the exception message string."""
        from apps.llm_gateway.views import _sync_sse_generator

        class BrokenProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                raise ValueError("quota exceeded")
                yield

        chunks = list(_sync_sse_generator(BrokenProvider(), [], []))
        last = json.loads(chunks[-1].replace("data:", "").strip())
        assert "quota exceeded" in last.get("error", "")

    def test_normal_stream_ends_with_done_true_and_used_doc_ids(self):
        """Happy-path stream must end with {done:true, used_doc_ids:[...]}."""
        from apps.llm_gateway.views import _sync_sse_generator

        class GoodProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                yield "Hello"
                yield " world"

        used_doc_ids = ["doc-abc", "doc-xyz"]
        chunks = list(_sync_sse_generator(GoodProvider(), [], used_doc_ids))

        last = json.loads(chunks[-1].replace("data:", "").strip())
        assert last.get("done") is True
        assert last.get("used_doc_ids") == used_doc_ids

    def test_normal_stream_token_events_have_done_false(self):
        """All intermediate events must have done=False."""
        from apps.llm_gateway.views import _sync_sse_generator

        class GoodProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                yield "A"
                yield "B"

        chunks = list(_sync_sse_generator(GoodProvider(), [], []))
        intermediate = [json.loads(c.replace("data:", "").strip()) for c in chunks[:-1]]
        assert all(e.get("done") is False for e in intermediate)

    def test_mid_stream_exception_still_yields_done(self):
        """Exception raised after some tokens must still send a final done event."""
        from apps.llm_gateway.views import _sync_sse_generator

        class PartialProvider:
            async def stream_chat(self, messages, max_tokens=2048):
                yield "first token"
                raise ConnectionError("connection dropped")

        chunks = list(_sync_sse_generator(PartialProvider(), [], []))
        assert len(chunks) >= 2, "Should have at least the token + the error event"
        last = json.loads(chunks[-1].replace("data:", "").strip())
        assert last.get("done") is True
        assert "error" in last
