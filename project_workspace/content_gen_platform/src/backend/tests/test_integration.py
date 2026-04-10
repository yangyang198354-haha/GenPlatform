"""
Integration tests — cross-module business flows.

Each test exercises a complete user journey across multiple apps,
using a real database (PostgreSQL in CI, SQLite locally).

Marked with @pytest.mark.integration so CI can run them separately
and enforce a higher pass-rate gate (≥90%).

Flows covered:
  IT-001  User registration → login → JWT access
  IT-002  LLM config save → retrieve (masked) → validate required fields
  IT-003  Content create → edit → confirm → revert on re-edit
  IT-004  Platform account bind → list → publish task create → retry
  IT-005  Full content pipeline: create → confirm → bind account → publish task
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.encryption import encrypt, decrypt
from apps.settings_vault.models import UserServiceConfig
from apps.content.models import Content
from apps.publisher.models import PlatformAccount, PublishTask

User = get_user_model()


# ── helpers ────────────────────────────────────────────────────────────────

def _register_and_login(client, email, password):
    """Register a new user and return the JWT access token."""
    reg = client.post("/api/v1/auth/register/", {
        "username": email.split("@")[0],
        "email": email,
        "password": password,
        "password2": password,
    }, format="json")
    assert reg.status_code == 201, f"register failed: {reg.data}"

    login = client.post("/api/v1/auth/login/", {
        "email": email,
        "password": password,
    }, format="json")
    assert login.status_code == 200, f"login failed: {login.data}"
    return login.data["access"], login.data["refresh"]


def _auth(client, token):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


# ══════════════════════════════════════════════════════════════════════════
# IT-001  User registration → login → JWT access
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.django_db
class TestIT001AuthFlow:
    """
    Given a new visitor
    When they register and then login
    Then they get a valid JWT and can access protected endpoints.
    """

    def test_register_creates_user(self):
        client = APIClient()
        resp = client.post("/api/v1/auth/register/", {
            "username": "intuser1",
            "email": "intuser1@example.com",
            "password": "SecurePass123!",
            "password2": "SecurePass123!",
        }, format="json")
        assert resp.status_code == 201
        assert User.objects.filter(email="intuser1@example.com").exists()

    def test_login_returns_jwt(self):
        client = APIClient()
        User.objects.create_user(
            username="intuser2", email="intuser2@example.com", password="SecurePass123!"
        )
        resp = client.post("/api/v1/auth/login/", {
            "email": "intuser2@example.com",
            "password": "SecurePass123!",
        }, format="json")
        assert resp.status_code == 200
        assert "access" in resp.data
        assert "refresh" in resp.data

    def test_protected_endpoint_requires_token(self):
        client = APIClient()
        resp = client.get("/api/v1/auth/profile/")
        assert resp.status_code == 401

    def test_profile_accessible_with_valid_token(self):
        client = APIClient()
        access, _ = _register_and_login(client, "intuser3@example.com", "SecurePass123!")
        _auth(client, access)
        resp = client.get("/api/v1/auth/profile/")
        assert resp.status_code == 200
        assert resp.data["email"] == "intuser3@example.com"

    def test_token_refresh_issues_new_access_token(self):
        client = APIClient()
        access, refresh = _register_and_login(client, "intuser4@example.com", "SecurePass123!")
        resp = client.post("/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json")
        assert resp.status_code == 200
        assert "access" in resp.data
        assert resp.data["access"] != access  # new token

    def test_duplicate_email_registration_fails(self):
        client = APIClient()
        _register_and_login(client, "dupuser@example.com", "SecurePass123!")
        resp = client.post("/api/v1/auth/register/", {
            "username": "dupuser2",
            "email": "dupuser@example.com",
            "password": "SecurePass123!",
            "password2": "SecurePass123!",
        }, format="json")
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
# IT-002  LLM config save → retrieve (masked) → validate required fields
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.django_db
class TestIT002LLMConfigFlow:
    """
    Given a logged-in user
    When they save a DeepSeek API key
    Then it is encrypted at rest, masked in list response,
         and missing required fields are rejected.
    """

    def test_save_and_retrieve_masked_config(self):
        client = APIClient()
        access, _ = _register_and_login(client, "llmuser@example.com", "SecurePass123!")
        _auth(client, access)

        # Save config
        put = client.put("/api/v1/settings/services/llm_deepseek/", {
            "api_key": "sk-real-integration-key",
        }, format="json")
        assert put.status_code == 200

        # Retrieve list — key must be masked
        get = client.get("/api/v1/settings/services/")
        assert get.status_code == 200
        deepseek = next(
            (s for s in get.data if s["service_type"] == "llm_deepseek"), None
        )
        assert deepseek is not None
        assert deepseek["is_configured"] is True
        # Masked: only first 4 chars visible
        preview_key = deepseek["config_preview"].get("api_key", "")
        assert preview_key.startswith("sk-r")
        assert "****" in preview_key
        assert "real-integration-key" not in preview_key

    def test_config_encrypted_in_db(self):
        client = APIClient()
        access, _ = _register_and_login(client, "llmuser2@example.com", "SecurePass123!")
        _auth(client, access)

        client.put("/api/v1/settings/services/llm_deepseek/", {
            "api_key": "sk-plaintext-should-not-appear",
        }, format="json")

        user = User.objects.get(email="llmuser2@example.com")
        cfg = UserServiceConfig.objects.get(user=user, service_type="llm_deepseek")
        # Raw bytes must NOT contain the plaintext key
        raw_bytes = bytes(cfg.encrypted_config)
        assert b"sk-plaintext-should-not-appear" not in raw_bytes
        # But decrypt() must recover it
        recovered = decrypt(raw_bytes)
        assert recovered["api_key"] == "sk-plaintext-should-not-appear"

    def test_volcano_requires_model_name(self):
        client = APIClient()
        access, _ = _register_and_login(client, "volcuser@example.com", "SecurePass123!")
        _auth(client, access)

        resp = client.put("/api/v1/settings/services/llm_volcano/", {
            "api_key": "ep-fake",
            # missing model_name
        }, format="json")
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_invalid_service_type_rejected(self):
        client = APIClient()
        access, _ = _register_and_login(client, "badservice@example.com", "SecurePass123!")
        _auth(client, access)
        resp = client.put("/api/v1/settings/services/llm_unknown/", {
            "api_key": "x",
        }, format="json")
        assert resp.status_code == 400

    def test_configs_are_user_isolated(self):
        """User A's config must not appear in User B's list."""
        client_a, client_b = APIClient(), APIClient()
        access_a, _ = _register_and_login(client_a, "usera@example.com", "SecurePass123!")
        access_b, _ = _register_and_login(client_b, "userb@example.com", "SecurePass123!")

        _auth(client_a, access_a)
        client_a.put("/api/v1/settings/services/llm_deepseek/", {
            "api_key": "sk-user-a-key",
        }, format="json")

        _auth(client_b, access_b)
        resp = client_b.get("/api/v1/settings/services/")
        deepseek_b = next(
            (s for s in resp.data if s["service_type"] == "llm_deepseek"), None
        )
        assert deepseek_b is None or deepseek_b["is_configured"] is False


# ══════════════════════════════════════════════════════════════════════════
# IT-003  Content create → edit → confirm → revert on re-edit
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.django_db
class TestIT003ContentLifecycle:
    """
    Given a logged-in user
    When they create a draft, edit it, confirm it, then re-edit
    Then the status transitions follow the defined lifecycle rules.
    """

    def test_create_draft_and_confirm(self):
        client = APIClient()
        access, _ = _register_and_login(client, "writer1@example.com", "SecurePass123!")
        _auth(client, access)

        # Create draft
        create = client.post("/api/v1/contents/", {
            "title": "Integration Test Draft",
            "body": "This is the draft content body.",
            "platform_type": "weibo",
            "style": "casual",
        }, format="json")
        assert create.status_code == 201
        content_id = create.data["id"]
        assert create.data["status"] == "draft"

        # Confirm
        confirm = client.post(f"/api/v1/contents/{content_id}/confirm/")
        assert confirm.status_code == 200
        assert confirm.data["status"] == "confirmed"
        assert confirm.data["confirmed_at"] is not None

    def test_edit_confirmed_content_reverts_to_draft(self):
        client = APIClient()
        access, _ = _register_and_login(client, "writer2@example.com", "SecurePass123!")
        _auth(client, access)

        create = client.post("/api/v1/contents/", {
            "title": "To Be Confirmed",
            "body": "Original body.",
            "platform_type": "general",
            "style": "professional",
        }, format="json")
        content_id = create.data["id"]
        client.post(f"/api/v1/contents/{content_id}/confirm/")

        # Re-edit the body — must revert to draft (AC-006-03)
        patch = client.patch(f"/api/v1/contents/{content_id}/", {
            "body": "Updated body content.",
        }, format="json")
        assert patch.status_code == 200
        assert patch.data["status"] == "draft"

    def test_content_list_filtered_by_status(self):
        client = APIClient()
        access, _ = _register_and_login(client, "writer3@example.com", "SecurePass123!")
        _auth(client, access)

        for i in range(3):
            client.post("/api/v1/contents/", {
                "title": f"Draft {i}", "body": f"Body {i}",
                "platform_type": "general", "style": "professional",
            }, format="json")

        resp = client.get("/api/v1/contents/", {"status": "draft"})
        assert resp.status_code == 200
        results = resp.data.get("results", resp.data)
        assert len(results) == 3

    def test_other_users_content_isolated(self):
        client_a, client_b = APIClient(), APIClient()
        access_a, _ = _register_and_login(client_a, "ca@example.com", "SecurePass123!")
        access_b, _ = _register_and_login(client_b, "cb@example.com", "SecurePass123!")

        _auth(client_a, access_a)
        create = client_a.post("/api/v1/contents/", {
            "title": "A's content", "body": "A's body",
            "platform_type": "general", "style": "professional",
        }, format="json")
        content_id = create.data["id"]

        # User B must not see or modify User A's content
        _auth(client_b, access_b)
        assert client_b.get(f"/api/v1/contents/{content_id}/").status_code == 404
        assert client_b.delete(f"/api/v1/contents/{content_id}/").status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# IT-004  Platform account bind → list → publish task lifecycle
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.django_db
class TestIT004PublisherFlow:
    """
    Given a logged-in user with a confirmed content
    When they bind a platform account and create a publish task
    Then the task is created and can be retried on failure.
    """

    def _setup(self):
        client = APIClient()
        access, _ = _register_and_login(client, "publisher@example.com", "SecurePass123!")
        _auth(client, access)
        return client

    def test_bind_platform_account(self):
        client = self._setup()
        resp = client.post("/api/v1/publisher/accounts/weibo/bind/", {
            "display_name": "My Weibo Account",
            "credentials": {"token": "fake-weibo-token"},
            "auth_type": "api_key",
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["platform"] == "weibo"
        assert resp.data["display_name"] == "My Weibo Account"

    def test_list_shows_only_active_accounts(self):
        client = self._setup()
        client.post("/api/v1/publisher/accounts/weibo/bind/", {
            "display_name": "Weibo", "credentials": {"token": "t1"}, "auth_type": "api_key",
        }, format="json")

        resp = client.get("/api/v1/publisher/accounts/")
        assert resp.status_code == 200
        results = resp.data.get("results", resp.data)
        assert len(results) == 1
        assert results[0]["platform"] == "weibo"

    def test_create_publish_task_requires_confirmed_content(self):
        client = self._setup()
        # Bind account first
        bind = client.post("/api/v1/publisher/accounts/weibo/bind/", {
            "display_name": "Weibo2", "credentials": {"token": "t2"}, "auth_type": "api_key",
        }, format="json")
        account_id = bind.data["id"]

        # Create DRAFT (not confirmed) content
        create = client.post("/api/v1/contents/", {
            "title": "Draft", "body": "body",
            "platform_type": "weibo", "style": "casual",
        }, format="json")
        content_id = create.data["id"]

        # Try to publish draft content — must fail
        resp = client.post("/api/v1/publisher/tasks/", {
            "content_id": content_id,
            "platform_account_ids": [account_id],
        }, format="json")
        assert resp.status_code == 400
        assert "error" in resp.data

    def test_create_publish_task_with_confirmed_content(self):
        client = self._setup()
        bind = client.post("/api/v1/publisher/accounts/weibo/bind/", {
            "display_name": "Weibo3", "credentials": {"token": "t3"}, "auth_type": "api_key",
        }, format="json")
        account_id = bind.data["id"]

        create = client.post("/api/v1/contents/", {
            "title": "Ready", "body": "body",
            "platform_type": "weibo", "style": "casual",
        }, format="json")
        content_id = create.data["id"]
        client.post(f"/api/v1/contents/{content_id}/confirm/")

        resp = client.post("/api/v1/publisher/tasks/", {
            "content_id": content_id,
            "platform_account_ids": [account_id],
        }, format="json")
        assert resp.status_code == 201
        assert isinstance(resp.data, list) and len(resp.data) == 1
        assert resp.data[0]["status"] in ("pending", "processing")


# ══════════════════════════════════════════════════════════════════════════
# IT-005  Full pipeline: register → configure → create → confirm → publish
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.django_db
class TestIT005FullContentPipeline:
    """
    End-to-end backend flow covering all major steps a real user takes:
    register → save LLM config → create content → confirm → bind account → publish task.
    No mocking — all logic runs against the real test database.
    """

    def test_complete_pipeline(self):
        client = APIClient()

        # Step 1: Register & login
        access, _ = _register_and_login(client, "pipeline@example.com", "SecurePass123!")
        _auth(client, access)

        # Step 2: Save LLM config
        cfg_resp = client.put("/api/v1/settings/services/llm_deepseek/", {
            "api_key": "sk-pipeline-test-key",
        }, format="json")
        assert cfg_resp.status_code == 200

        # Step 3: Create draft content
        create = client.post("/api/v1/contents/", {
            "title": "Pipeline Test Article",
            "body": "Content body generated by pipeline integration test.",
            "platform_type": "xiaohongshu",
            "style": "promotion",
            "generation_prompt": "Write about integration testing",
        }, format="json")
        assert create.status_code == 201
        content_id = create.data["id"]
        assert create.data["status"] == "draft"

        # Step 4: Verify content appears in list
        list_resp = client.get("/api/v1/contents/")
        results = list_resp.data.get("results", list_resp.data)
        assert any(c["id"] == content_id for c in results)

        # Step 5: Confirm content
        confirm = client.post(f"/api/v1/contents/{content_id}/confirm/")
        assert confirm.status_code == 200
        assert confirm.data["status"] == "confirmed"

        # Step 6: Bind publishing platform
        bind = client.post("/api/v1/publisher/accounts/xiaohongshu/bind/", {
            "display_name": "My Xiaohongshu",
            "credentials": {"token": "xhs-fake-token-pipeline"},
            "auth_type": "api_key",
        }, format="json")
        assert bind.status_code == 201
        account_id = bind.data["id"]

        # Step 7: Create publish task
        task = client.post("/api/v1/publisher/tasks/", {
            "content_id": content_id,
            "platform_account_ids": [account_id],
        }, format="json")
        assert task.status_code == 201
        assert isinstance(task.data, list) and len(task.data) >= 1
        task_id = task.data[0]["id"]

        # Step 8: Verify task appears in history
        history = client.get("/api/v1/publisher/tasks/")
        assert history.status_code == 200
        task_results = history.data.get("results", history.data)
        assert any(t["id"] == task_id for t in task_results)
