"""Image Generator models — tracks async image generation requests."""
from django.db import models
from apps.accounts.models import User


class ImageGenerationRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("processing", "生成中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="image_generation_requests"
    )
    prompt = models.TextField()
    ref_image_path = models.CharField(max_length=1024, blank=True)  # local temp path
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    jimeng_task_id = models.CharField(max_length=255, blank=True)
    result_image_url = models.CharField(max_length=1024, blank=True)  # raw Jimeng URL
    media_item = models.ForeignKey(
        "media_library.MediaItem",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="image_generation_requests",
    )
    error_message = models.TextField(blank=True)
    progress = models.IntegerField(default=0)  # 0-100
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "image_generation_request"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ImageRequest #{self.pk} [{self.status}] by {self.user.email}"
