"""Unit tests for publisher Celery tasks."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from apps.publisher.models import PublishTask
from apps.publisher.tasks import execute_publish_task


@pytest.mark.django_db
class TestExecutePublishTask:
    @patch("apps.publisher.tasks.push_notification", new_callable=AsyncMock)
    @patch("apps.publisher.tasks.get_publisher")
    def test_task_success(self, mock_get_publisher, mock_notify, publish_task):
        mock_publisher = MagicMock()
        mock_result = MagicMock(success=True, post_id="post_123",
                                post_url="https://weibo.com/post/123", error=None)
        mock_publisher.publish = AsyncMock(return_value=mock_result)
        mock_get_publisher.return_value = mock_publisher

        execute_publish_task(publish_task.pk)

        publish_task.refresh_from_db()
        assert publish_task.status == "success"
        assert publish_task.platform_post_id == "post_123"
        assert publish_task.platform_post_url == "https://weibo.com/post/123"
        assert publish_task.published_at is not None

    @patch("apps.publisher.tasks.push_notification", new_callable=AsyncMock)
    @patch("apps.publisher.tasks.get_publisher")
    def test_task_failure_sets_error(self, mock_get_publisher, mock_notify, publish_task):
        mock_publisher = MagicMock()
        mock_result = MagicMock(success=False, post_id=None,
                                post_url=None, error="API quota exceeded")
        mock_publisher.publish = AsyncMock(return_value=mock_result)
        mock_get_publisher.return_value = mock_publisher

        execute_publish_task(publish_task.pk)

        publish_task.refresh_from_db()
        assert publish_task.status == "failed"
        assert "API quota exceeded" in publish_task.error_message
        assert publish_task.retry_count == 1

    @patch("apps.publisher.tasks.push_notification", new_callable=AsyncMock)
    @patch("apps.publisher.tasks.get_publisher")
    def test_task_sends_notification(self, mock_get_publisher, mock_notify, publish_task):
        mock_publisher = MagicMock()
        mock_result = MagicMock(success=True, post_id="p1",
                                post_url="http://example.com", error=None)
        mock_publisher.publish = AsyncMock(return_value=mock_result)
        mock_get_publisher.return_value = mock_publisher

        execute_publish_task(publish_task.pk)

        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert call_kwargs[1]["event_type"] == "publish_status" or \
               call_kwargs[0][1] == "publish_status"

    def test_task_nonexistent_id_does_not_raise(self):
        # Should log and return gracefully
        execute_publish_task(99999)

    @patch("apps.publisher.tasks.push_notification", new_callable=AsyncMock)
    @patch("apps.publisher.tasks.get_publisher")
    def test_task_sets_publishing_state(self, mock_get_publisher, mock_notify, publish_task):
        """Verify status is set to 'publishing' before calling the platform API."""
        statuses_seen = []

        def side_effect(platform):
            publish_task.refresh_from_db()
            statuses_seen.append(publish_task.status)
            mock_publisher = MagicMock()
            mock_result = MagicMock(success=True, post_id="x", post_url="http://x.com", error=None)
            mock_publisher.publish = AsyncMock(return_value=mock_result)
            return mock_publisher

        mock_get_publisher.side_effect = side_effect
        execute_publish_task(publish_task.pk)
        assert "publishing" in statuses_seen
