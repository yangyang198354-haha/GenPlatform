"""Integration tests for content API views."""
import pytest
from django.utils import timezone
from rest_framework import status
from apps.content.models import Content

CONTENTS_URL = "/api/v1/contents/"


def _detail_url(pk):
    return f"{CONTENTS_URL}{pk}/"


def _confirm_url(pk):
    return f"{CONTENTS_URL}{pk}/confirm/"


@pytest.mark.django_db
class TestContentListCreateView:
    def test_create_content(self, auth_client):
        client, user = auth_client
        payload = {
            "title": "My Post",
            "body": "Great content here.",
            "platform_type": "weibo",
            "style": "casual",
        }
        resp = client.post(CONTENTS_URL, payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == "draft"
        assert resp.data["title"] == "My Post"
        assert Content.objects.filter(user=user).count() == 1

    def test_create_content_minimal(self, auth_client):
        client, _ = auth_client
        resp = client.post(CONTENTS_URL, {"body": "just body"}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

    def test_list_own_content_only(self, auth_client, auth_client2):
        client1, user1 = auth_client
        client2, user2 = auth_client2

        Content.objects.create(user=user1, body="user1 content")
        Content.objects.create(user=user2, body="user2 content")

        resp = client1.get(CONTENTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["body"] == "user1 content"

    def test_filter_by_status_draft(self, auth_client, user):
        client, _ = auth_client
        Content.objects.create(user=user, body="draft one", status="draft")
        Content.objects.create(user=user, body="confirmed one", status="confirmed",
                               confirmed_at=timezone.now())

        resp = client.get(CONTENTS_URL + "?status=draft")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["status"] == "draft"

    def test_filter_by_status_confirmed(self, auth_client, user):
        client, _ = auth_client
        Content.objects.create(user=user, body="draft one", status="draft")
        Content.objects.create(user=user, body="confirmed one", status="confirmed",
                               confirmed_at=timezone.now())

        resp = client.get(CONTENTS_URL + "?status=confirmed")
        assert len(resp.data) == 1
        assert resp.data[0]["status"] == "confirmed"

    def test_unauthenticated_cannot_list(self, api_client):
        resp = api_client.get(CONTENTS_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_word_count_field(self, auth_client):
        client, _ = auth_client
        resp = client.post(CONTENTS_URL, {"body": "hello world"}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["word_count"] == len("hello world")


@pytest.mark.django_db
class TestContentDetailView:
    def test_get_content(self, auth_client, draft_content):
        client, _ = auth_client
        resp = client.get(_detail_url(draft_content.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["id"] == draft_content.pk

    def test_update_draft_content(self, auth_client, draft_content):
        client, _ = auth_client
        resp = client.patch(_detail_url(draft_content.pk), {"body": "updated body"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        draft_content.refresh_from_db()
        assert draft_content.body == "updated body"
        assert draft_content.status == "draft"  # remains draft

    def test_editing_confirmed_body_reverts_to_draft(self, auth_client, confirmed_content):
        client, _ = auth_client
        resp = client.patch(
            _detail_url(confirmed_content.pk),
            {"body": "edited body"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        confirmed_content.refresh_from_db()
        assert confirmed_content.status == "draft"
        assert confirmed_content.confirmed_at is None

    def test_editing_confirmed_title_does_not_revert(self, auth_client, confirmed_content):
        client, _ = auth_client
        resp = client.patch(
            _detail_url(confirmed_content.pk),
            {"title": "new title"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        confirmed_content.refresh_from_db()
        assert confirmed_content.status == "confirmed"  # not reverted

    def test_delete_content(self, auth_client, draft_content):
        client, _ = auth_client
        resp = client.delete(_detail_url(draft_content.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not Content.objects.filter(pk=draft_content.pk).exists()

    def test_other_user_cannot_get(self, auth_client2, draft_content):
        client2, _ = auth_client2
        resp = client2.get(_detail_url(draft_content.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_other_user_cannot_delete(self, auth_client2, draft_content):
        client2, _ = auth_client2
        resp = client2.delete(_detail_url(draft_content.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert Content.objects.filter(pk=draft_content.pk).exists()


@pytest.mark.django_db
class TestContentConfirmView:
    def test_confirm_draft_content(self, auth_client, draft_content):
        client, _ = auth_client
        resp = client.post(_confirm_url(draft_content.pk))
        assert resp.status_code == status.HTTP_200_OK
        draft_content.refresh_from_db()
        assert draft_content.status == "confirmed"
        assert draft_content.confirmed_at is not None

    def test_confirm_already_confirmed_returns_message(self, auth_client, confirmed_content):
        client, _ = auth_client
        resp = client.post(_confirm_url(confirmed_content.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert "已处于确认状态" in resp.data["message"]

    def test_confirm_nonexistent_returns_404(self, auth_client):
        client, _ = auth_client
        resp = client.post(_confirm_url(99999))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_confirm_other_users_content_returns_404(self, auth_client2, draft_content):
        client2, _ = auth_client2
        resp = client2.post(_confirm_url(draft_content.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        draft_content.refresh_from_db()
        assert draft_content.status == "draft"  # unchanged
