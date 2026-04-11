"""Integration tests for Media Library API views."""
import io
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework import status
from apps.media_library.models import MediaItem


_EXT = {"image": "jpg", "video": "mp4", "audio": "mp3"}

def make_item(user, media_type="image", source="uploaded", title="Test"):
    ext = _EXT.get(media_type, "bin")
    item = MediaItem(owner=user, media_type=media_type, source=source, title=title)
    item.file.save(f"test.{ext}", ContentFile(b"data"), save=True)
    return item


@pytest.mark.django_db
class TestMediaItemListView:

    def test_list_returns_only_own_items(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2

        make_item(user, title="Mine")
        make_item(user2, title="Theirs")

        resp = client.get("/api/v1/media/")
        assert resp.status_code == status.HTTP_200_OK
        titles = [r["title"] for r in resp.data["results"]]
        assert "Mine" in titles
        assert "Theirs" not in titles

    def test_list_filter_by_media_type(self, auth_client):
        client, user = auth_client
        make_item(user, media_type="image", title="Img")
        make_item(user, media_type="video", title="Vid")

        resp = client.get("/api/v1/media/", {"media_type": "image"})
        assert resp.status_code == status.HTTP_200_OK
        titles = [r["title"] for r in resp.data["results"]]
        assert "Img" in titles
        assert "Vid" not in titles

    def test_list_filter_by_source(self, auth_client):
        client, user = auth_client
        make_item(user, source="ai_generated", title="AI")
        make_item(user, source="uploaded", title="Uploaded")

        resp = client.get("/api/v1/media/", {"source": "ai_generated"})
        assert resp.status_code == status.HTTP_200_OK
        titles = [r["title"] for r in resp.data["results"]]
        assert "AI" in titles
        assert "Uploaded" not in titles

    def test_list_unauthenticated_returns_401(self, api_client):
        resp = api_client.get("/api/v1/media/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_response_shape(self, auth_client):
        client, user = auth_client
        make_item(user)
        resp = client.get("/api/v1/media/")
        item = resp.data["results"][0]
        assert "id" in item
        assert "media_type" in item
        assert "source" in item
        assert "title" in item
        assert "file_url" in item
        assert "file_size" in item
        assert "created_at" in item


@pytest.mark.django_db
class TestMediaItemUploadView:

    def _make_upload(self, name="test.jpg", content=b"fake", mime="image/jpeg"):
        return io.BytesIO(content), name, mime

    def test_upload_image_success(self, auth_client):
        client, user = auth_client
        img_file = io.BytesIO(b"fake-jpeg-content")
        img_file.name = "test.jpg"
        resp = client.post(
            "/api/v1/media/upload/",
            {"file": img_file, "media_type": "image"},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["media_type"] == "image"
        assert resp.data["source"] == "uploaded"
        assert MediaItem.objects.filter(owner=user).count() == 1

    def test_upload_missing_file_returns_400(self, auth_client):
        client, _ = auth_client
        resp = client.post("/api/v1/media/upload/", {"media_type": "image"}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_invalid_media_type_returns_400(self, auth_client):
        client, _ = auth_client
        img = io.BytesIO(b"data")
        img.name = "file.jpg"
        resp = client.post(
            "/api/v1/media/upload/",
            {"file": img, "media_type": "document"},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_title_defaults_to_filename(self, auth_client):
        client, user = auth_client
        img = io.BytesIO(b"fake")
        img.name = "my_photo.jpg"
        resp = client.post(
            "/api/v1/media/upload/",
            {"file": img, "media_type": "image"},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        item = MediaItem.objects.get(owner=user)
        assert "my_photo" in item.title

    def test_upload_requires_auth(self, api_client):
        resp = api_client.post("/api/v1/media/upload/", {}, format="multipart")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestMediaItemDeleteView:

    def test_delete_own_item(self, auth_client):
        client, user = auth_client
        item = make_item(user)
        resp = client.delete(f"/api/v1/media/{item.pk}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not MediaItem.objects.filter(pk=item.pk).exists()

    def test_delete_other_user_item_returns_403(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2
        item = make_item(user2)
        resp = client.delete(f"/api/v1/media/{item.pk}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert MediaItem.objects.filter(pk=item.pk).exists()

    def test_delete_nonexistent_returns_404(self, auth_client):
        client, _ = auth_client
        resp = client.delete("/api/v1/media/99999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_requires_auth(self, api_client, user):
        item = make_item(user)
        resp = api_client.delete(f"/api/v1/media/{item.pk}/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestMediaItemDownloadView:

    def test_download_redirects_to_file_url(self, auth_client):
        client, user = auth_client
        item = make_item(user)
        resp = client.get(f"/api/v1/media/{item.pk}/download/")
        # Should redirect (302) to the file URL
        assert resp.status_code in (status.HTTP_302_FOUND, status.HTTP_301_MOVED_PERMANENTLY)

    def test_download_other_user_returns_403(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2
        item = make_item(user2)
        resp = client.get(f"/api/v1/media/{item.pk}/download/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
