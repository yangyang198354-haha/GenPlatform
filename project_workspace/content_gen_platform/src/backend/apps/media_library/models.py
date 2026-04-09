"""Media Library models — stores all user media assets (images, videos, audio)."""
import os
from django.db import models
from django.conf import settings
from apps.accounts.models import User


def _upload_to(instance, filename):
    """Route uploads to typed subdirectories: media/{type}s/{user_id}/{filename}."""
    return f"{instance.media_type}s/{instance.owner_id}/{filename}"


def _thumbnail_upload_to(instance, filename):
    return f"thumbnails/{instance.owner_id}/{filename}"


class MediaItem(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("image", "图片"),
        ("video", "视频"),
        ("audio", "音频"),
    ]
    SOURCE_CHOICES = [
        ("ai_generated", "AI 生成"),
        ("uploaded", "用户上传"),
    ]

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="media_items"
    )
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    file = models.FileField(upload_to=_upload_to)
    thumbnail = models.FileField(upload_to=_thumbnail_upload_to, blank=True, null=True)
    title = models.CharField(max_length=255)
    file_size = models.BigIntegerField(default=0)  # bytes
    duration_sec = models.FloatField(null=True, blank=True)  # for video/audio
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "media_item"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.owner.email} — {self.title} ({self.media_type})"

    def delete(self, *args, **kwargs):
        """Override delete to also remove files from disk."""
        # Delete main file
        if self.file:
            file_path = self.file.path
            if os.path.exists(file_path):
                os.remove(file_path)
        # Delete thumbnail
        if self.thumbnail:
            thumb_path = self.thumbnail.path
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        super().delete(*args, **kwargs)
