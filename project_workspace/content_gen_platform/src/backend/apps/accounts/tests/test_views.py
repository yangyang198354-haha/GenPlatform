"""Integration tests for accounts API views."""
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

User = get_user_model()

REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
REFRESH_URL = "/api/v1/auth/token/refresh/"
PROFILE_URL = "/api/v1/auth/profile/"


@pytest.mark.django_db
class TestRegisterView:
    def test_register_success(self, api_client):
        payload = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        resp = api_client.post(REGISTER_URL, payload)
        assert resp.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="new@example.com").exists()

    def test_register_password_mismatch(self, api_client):
        payload = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPass123!",
            "password2": "DifferentPass!",
        }
        resp = api_client.post(REGISTER_URL, payload)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, user):
        payload = {
            "username": "another",
            "email": user.email,  # already taken
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        resp = api_client.post(REGISTER_URL, payload)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_missing_email(self, api_client):
        payload = {
            "username": "newuser",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        resp = api_client.post(REGISTER_URL, payload)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_invalid_email(self, api_client):
        payload = {
            "username": "newuser",
            "email": "not-an-email",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        resp = api_client.post(REGISTER_URL, payload)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestRegisterPasswordValidation:
    """
    Regression tests for fix(register) commit ba99fe3.

    Before the fix the serializer did not include a password2 field in the
    proper write_only manner; mismatched passwords or missing password2 could
    either crash or silently succeed.  Also validates that Django's built-in
    password validators (CommonPasswordValidator, NumericPasswordValidator)
    are wired in via validate_password.
    """

    def test_missing_password2_returns_400(self, api_client):
        """Omitting password2 entirely must be rejected with 400."""
        resp = api_client.post(REGISTER_URL, {
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPass123!",
            # password2 intentionally absent
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_all_numeric_password_rejected(self, api_client):
        """Django NumericPasswordValidator must reject all-digit passwords."""
        resp = api_client.post(REGISTER_URL, {
            "username": "numericuser",
            "email": "numeric@example.com",
            "password": "12345678",
            "password2": "12345678",
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_too_short_password_rejected(self, api_client):
        """Password shorter than 8 characters must be rejected."""
        resp = api_client.post(REGISTER_URL, {
            "username": "shortpass",
            "email": "short@example.com",
            "password": "Ab1!",
            "password2": "Ab1!",
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_password2_not_returned_in_response(self, api_client):
        """password and password2 are write_only — they must never appear in response."""
        resp = api_client.post(REGISTER_URL, {
            "username": "safeuser",
            "email": "safe@example.com",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        assert "password" not in resp.data
        assert "password2" not in resp.data

    def test_password_mismatch_error_key_is_password(self, api_client):
        """Mismatch error must be keyed under 'password' (not 'non_field_errors')."""
        resp = api_client.post(REGISTER_URL, {
            "username": "mismatch",
            "email": "mismatch@example.com",
            "password": "StrongPass123!",
            "password2": "Different123!",
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        # Error must be keyed under 'password' per the serializer validate() impl
        assert "password" in resp.data


@pytest.mark.django_db
class TestLoginView:
    def test_login_success(self, api_client, user):
        resp = api_client.post(LOGIN_URL, {"email": user.email, "password": "TestPass123!"})
        assert resp.status_code == status.HTTP_200_OK
        assert "access" in resp.data
        assert "refresh" in resp.data

    def test_login_wrong_password(self, api_client, user):
        resp = api_client.post(LOGIN_URL, {"email": user.email, "password": "WrongPassword!"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        resp = api_client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "anything"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_fields(self, api_client):
        resp = api_client.post(LOGIN_URL, {"email": "test@example.com"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTokenRefreshView:
    def test_refresh_success(self, api_client, user):
        refresh = RefreshToken.for_user(user)
        resp = api_client.post(REFRESH_URL, {"refresh": str(refresh)})
        assert resp.status_code == status.HTTP_200_OK
        assert "access" in resp.data

    def test_refresh_invalid_token(self, api_client):
        resp = api_client.post(REFRESH_URL, {"refresh": "not.a.valid.token"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserProfileView:
    def test_get_profile_authenticated(self, auth_client):
        client, user = auth_client
        resp = client.get(PROFILE_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["email"] == user.email
        assert resp.data["username"] == user.username
        assert "storage_used_mb" in resp.data
        assert "storage_quota_mb" in resp.data

    def test_get_profile_unauthenticated(self, api_client):
        resp = api_client.get(PROFILE_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_profile_storage_values(self, auth_client):
        client, user = auth_client
        resp = client.get(PROFILE_URL)
        assert resp.data["storage_used_mb"] == 0.0
        assert resp.data["storage_quota_mb"] == round(2 * 1024**3 / 1024**2, 2)

    def test_update_username(self, auth_client):
        client, user = auth_client
        resp = client.patch(PROFILE_URL, {"username": "updated_name"})
        assert resp.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.username == "updated_name"

    def test_email_is_read_only(self, auth_client):
        client, user = auth_client
        original_email = user.email
        resp = client.patch(PROFILE_URL, {"email": "new@example.com"})
        # Should succeed but email must not change
        assert resp.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.email == original_email
