"""Integration tests for publisher API views."""
import pytest
from unittest.mock import patch
from rest_framework import status
from apps.publisher.models import PlatformAccount, PublishTask
from core.encryption import encrypt

ACCOUNTS_URL = "/api/v1/publisher/accounts/"
TASKS_URL = "/api/v1/publisher/tasks/"


def _bind_url(platform):
    return f"{ACCOUNTS_URL}{platform}/bind/"


def _account_url(pk):
    return f"{ACCOUNTS_URL}{pk}/"


def _retry_url(pk):
    return f"{TASKS_URL}{pk}/retry/"


@pytest.mark.django_db
class TestPlatformAccountBindView:
    def test_bind_success(self, auth_client):
        client, user = auth_client
        resp = client.post(
            _bind_url("weibo"),
            {"credentials": "my-api-key", "display_name": "My Weibo"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert PlatformAccount.objects.filter(user=user, platform="weibo").exists()

    def test_bind_dict_credentials(self, auth_client):
        client, _ = auth_client
        resp = client.post(
            _bind_url("xiaohongshu"),
            {"credentials": {"access_token": "tok", "secret": "sec"}, "display_name": "XHS"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_bind_invalid_platform(self, auth_client):
        client, _ = auth_client
        resp = client.post(
            _bind_url("twitter"),
            {"credentials": "key", "display_name": "Twitter"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "不支持的平台" in resp.data["error"]

    def test_bind_missing_credentials(self, auth_client):
        client, _ = auth_client
        resp = client.post(_bind_url("weibo"), {"display_name": "Weibo"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_bind_missing_display_name(self, auth_client):
        client, _ = auth_client
        resp = client.post(_bind_url("weibo"), {"credentials": "key"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_bind_updates_existing_account(self, auth_client, user):
        client, _ = auth_client
        # First bind
        client.post(_bind_url("weibo"), {"credentials": "old-key", "display_name": "Old"},
                    format="json")
        # Rebind with new credentials
        resp = client.post(_bind_url("weibo"), {"credentials": "new-key", "display_name": "New"},
                           format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        # Should still be only one account for this user+platform
        assert PlatformAccount.objects.filter(user=user, platform="weibo").count() == 1
        assert PlatformAccount.objects.get(user=user, platform="weibo").display_name == "New"

    def test_unauthenticated_cannot_bind(self, api_client):
        resp = api_client.post(_bind_url("weibo"),
                               {"credentials": "k", "display_name": "n"}, format="json")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPlatformAccountListView:
    def test_list_active_accounts_only(self, auth_client, user):
        client, _ = auth_client
        PlatformAccount.objects.create(
            user=user, platform="weibo", display_name="Active",
            auth_type="api_key", encrypted_credentials=encrypt({"token": "a"}), is_active=True,
        )
        PlatformAccount.objects.create(
            user=user, platform="toutiao", display_name="Inactive",
            auth_type="api_key", encrypted_credentials=encrypt({"token": "b"}), is_active=False,
        )
        resp = client.get(ACCOUNTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        assert len(results) == 1
        assert results[0]["platform"] == "weibo"

    def test_list_own_accounts_only(self, auth_client, auth_client2, user, user2):
        client1, _ = auth_client
        PlatformAccount.objects.create(
            user=user, platform="weibo", display_name="U1",
            auth_type="api_key", encrypted_credentials=encrypt({"token": "a"}),
        )
        PlatformAccount.objects.create(
            user=user2, platform="weibo", display_name="U2",
            auth_type="api_key", encrypted_credentials=encrypt({"token": "b"}),
        )
        resp = client1.get(ACCOUNTS_URL)
        results = resp.data.get("results", resp.data)
        assert len(results) == 1
        assert results[0]["display_name"] == "U1"


@pytest.mark.django_db
class TestPlatformAccountDeleteView:
    def test_soft_delete_account(self, auth_client, platform_account):
        client, _ = auth_client
        resp = client.delete(_account_url(platform_account.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        platform_account.refresh_from_db()
        assert platform_account.is_active is False
        # Record still exists in DB
        assert PlatformAccount.objects.filter(pk=platform_account.pk).exists()

    def test_delete_nonexistent_returns_404(self, auth_client):
        client, _ = auth_client
        resp = client.delete(_account_url(99999))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_delete_other_users_account(self, auth_client2, platform_account):
        client2, _ = auth_client2
        resp = client2.delete(_account_url(platform_account.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        platform_account.refresh_from_db()
        assert platform_account.is_active is True


@pytest.mark.django_db
class TestPublishTaskListCreateView:
    @patch("apps.publisher.views.execute_publish_task")
    def test_create_tasks_success(self, mock_task, auth_client, confirmed_content, platform_account):
        client, _ = auth_client
        resp = client.post(
            TASKS_URL,
            {"content_id": confirmed_content.pk, "platform_account_ids": [platform_account.pk]},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data) == 1
        assert resp.data[0]["status"] == "pending"
        mock_task.delay.assert_called_once()

    @patch("apps.publisher.views.execute_publish_task")
    def test_create_tasks_multiple_accounts(self, mock_task, auth_client, user,
                                            confirmed_content, platform_account):
        client, _ = auth_client
        account2 = PlatformAccount.objects.create(
            user=user, platform="xiaohongshu", display_name="XHS",
            auth_type="api_key", encrypted_credentials=encrypt({"token": "x"}),
        )
        resp = client.post(
            TASKS_URL,
            {"content_id": confirmed_content.pk,
             "platform_account_ids": [platform_account.pk, account2.pk]},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data) == 2
        assert mock_task.delay.call_count == 2

    def test_create_task_requires_confirmed_content(self, auth_client, draft_content, platform_account):
        client, _ = auth_client
        resp = client.post(
            TASKS_URL,
            {"content_id": draft_content.pk, "platform_account_ids": [platform_account.pk]},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "已确认状态" in resp.data["error"]

    def test_create_task_missing_content_id(self, auth_client, platform_account):
        client, _ = auth_client
        resp = client.post(TASKS_URL, {"platform_account_ids": [platform_account.pk]},
                           format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_task_invalid_account(self, auth_client, confirmed_content):
        client, _ = auth_client
        resp = client.post(
            TASKS_URL,
            {"content_id": confirmed_content.pk, "platform_account_ids": [99999]},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.publisher.views.execute_publish_task")
    def test_scheduled_publish_uses_apply_async(self, mock_task, auth_client,
                                                confirmed_content, platform_account):
        client, _ = auth_client
        resp = client.post(
            TASKS_URL,
            {
                "content_id": confirmed_content.pk,
                "platform_account_ids": [platform_account.pk],
                "scheduled_at": "2030-01-01T10:00:00Z",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        mock_task.apply_async.assert_called_once()
        mock_task.delay.assert_not_called()

    def test_list_own_tasks_only(self, auth_client, auth_client2, user, user2,
                                 confirmed_content, platform_account):
        client1, _ = auth_client
        PublishTask.objects.create(user=user, content=confirmed_content,
                                   platform_account=platform_account)
        resp = client1.get(TASKS_URL)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        for task_data in results:
            # Tasks in response must belong to user1
            assert PublishTask.objects.get(pk=task_data["id"]).user == user


@pytest.mark.django_db
class TestPublishTaskRetryView:
    @patch("apps.publisher.views.execute_publish_task")
    def test_retry_failed_task(self, mock_task, auth_client, publish_task):
        publish_task.status = "failed"
        publish_task.save()

        client, _ = auth_client
        resp = client.post(_retry_url(publish_task.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert "重试" in resp.data["message"]
        publish_task.refresh_from_db()
        assert publish_task.status == "pending"
        mock_task.delay.assert_called_once_with(publish_task.pk)

    def test_retry_non_failed_task_returns_404(self, auth_client, publish_task):
        publish_task.status = "success"
        publish_task.save()

        client, _ = auth_client
        resp = client.post(_retry_url(publish_task.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_retry_pending_task_returns_404(self, auth_client, publish_task):
        client, _ = auth_client
        resp = client.post(_retry_url(publish_task.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_retry_other_users_task_returns_404(self, auth_client2, publish_task):
        publish_task.status = "failed"
        publish_task.save()

        client2, _ = auth_client2
        resp = client2.post(_retry_url(publish_task.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
