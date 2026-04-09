from django.db import models
from apps.accounts.models import User


class UserServiceConfig(models.Model):
    SERVICE_CHOICES = [
        ("llm_deepseek", "DeepSeek LLM"),
        ("llm_volcano", "火山引擎（豆包）"),
        ("jimeng", "即梦视频/图片生成"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="service_configs")
    service_type = models.CharField(max_length=30, choices=SERVICE_CHOICES)
    encrypted_config = models.BinaryField()  # AES-256-GCM encrypted JSON
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "settings_service_config"
        unique_together = [("user", "service_type")]

    def __str__(self):
        return f"{self.user.email} — {self.service_type}"
