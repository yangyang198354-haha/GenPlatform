"""Unit tests for media_library service functions."""
import pytest
from unittest.mock import patch, MagicMock
from apps.media_library.service import create_media_item_from_url
from apps.media_library.models import MediaItem


@pytest.mark.django_db
class TestCreateMediaItemFromUrl:

    @patch("apps.media_library.service.httpx.get")
    def test_creates_media_item_from_url(self, mock_get, user):
        mock_resp = MagicMock()
        mock_resp.content = b"fake-image-bytes"
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        item = create_media_item_from_url(
            user=user,
            url="https://example.com/img.jpg",
            media_type="image",
            source="ai_generated",
            title="Test Image",
        )

        assert item.pk is not None
        assert item.owner == user
        assert item.media_type == "image"
        assert item.source == "ai_generated"
        assert item.title == "Test Image"
        assert item.file_size == len(b"fake-image-bytes")

    @patch("apps.media_library.service.httpx.get")
    def test_auto_title_when_empty(self, mock_get, user):
        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.headers = {"content-type": "image/png"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        item = create_media_item_from_url(
            user=user,
            url="https://example.com/x.png",
            media_type="image",
            source="ai_generated",
            title="",
        )
        assert item.title.startswith("ai_image_")

    @patch("apps.media_library.service.httpx.get")
    def test_raises_on_http_error(self, mock_get, user):
        import httpx
        mock_get.side_effect = httpx.HTTPError("Connection failed")

        with pytest.raises(RuntimeError, match="下载媒体文件失败"):
            create_media_item_from_url(
                user=user,
                url="https://bad-url.example.com/img.jpg",
                media_type="image",
                source="ai_generated",
            )

    @patch("apps.media_library.service.httpx.get")
    def test_extension_from_url_when_no_content_type(self, mock_get, user):
        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.headers = {}  # no content-type
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        item = create_media_item_from_url(
            user=user,
            url="https://example.com/photo.png",
            media_type="image",
            source="uploaded",
        )
        assert item.file.name.endswith(".png")
