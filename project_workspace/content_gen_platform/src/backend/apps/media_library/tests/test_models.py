"""Unit tests for MediaItem model."""
import os
import pytest
from django.core.files.base import ContentFile
from apps.media_library.models import MediaItem


@pytest.mark.django_db
class TestMediaItemModel:

    def test_create_media_item_image(self, user):
        item = MediaItem(
            owner=user,
            media_type="image",
            source="uploaded",
            title="Test Image",
            file_size=1024,
        )
        item.file.save("test.jpg", ContentFile(b"fake-jpeg-data"), save=True)

        assert item.pk is not None
        assert item.media_type == "image"
        assert item.source == "uploaded"
        assert item.title == "Test Image"
        assert item.file_size == 1024
        assert item.duration_sec is None
        assert str(user.pk) in item.file.name  # path contains user_id

    def test_upload_to_path_image(self, user):
        """Files are stored under images/{user_id}/."""
        item = MediaItem(owner=user, media_type="image", source="uploaded", title="t")
        item.file.save("photo.png", ContentFile(b"data"), save=True)
        assert item.file.name.startswith(f"images/{user.pk}/")

    def test_upload_to_path_video(self, user):
        item = MediaItem(owner=user, media_type="video", source="ai_generated", title="v")
        item.file.save("clip.mp4", ContentFile(b"data"), save=True)
        assert item.file.name.startswith(f"videos/{user.pk}/")

    def test_upload_to_path_audio(self, user):
        item = MediaItem(owner=user, media_type="audio", source="uploaded", title="a")
        item.file.save("track.mp3", ContentFile(b"data"), save=True)
        assert item.file.name.startswith(f"audios/{user.pk}/")

    def test_default_ordering_newest_first(self, user):
        """Items are ordered by -created_at."""
        item1 = MediaItem(owner=user, media_type="image", source="uploaded", title="first")
        item1.file.save("a.jpg", ContentFile(b"x"), save=True)
        item2 = MediaItem(owner=user, media_type="image", source="uploaded", title="second")
        item2.file.save("b.jpg", ContentFile(b"y"), save=True)

        items = list(MediaItem.objects.filter(owner=user))
        assert items[0].pk == item2.pk  # newest first

    def test_delete_removes_file(self, user, tmp_path, settings):
        """Model delete() should remove the file from disk."""
        settings.MEDIA_ROOT = str(tmp_path)
        item = MediaItem(owner=user, media_type="image", source="uploaded", title="del")
        item.file.save("deleteme.jpg", ContentFile(b"to-delete"), save=True)
        file_path = item.file.path
        assert os.path.exists(file_path)

        item.delete()
        assert not os.path.exists(file_path)

    def test_str_representation(self, user):
        item = MediaItem(owner=user, media_type="image", source="uploaded", title="Banner")
        assert user.email in str(item)
        assert "Banner" in str(item)
        assert "image" in str(item)
