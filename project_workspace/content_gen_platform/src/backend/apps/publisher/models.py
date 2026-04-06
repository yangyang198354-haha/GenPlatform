from django.db import models
from apps.accounts.models import User
from apps.content.models import Content


class PlatformAccount(models.Model):
    PLATFORM_CHOICES = [
        ("weibo", "微博"),
        ("xiaohongshu", "小红书"),
        ("wechat_mp", "微信公众号"),
        ("wechat_video", "微信视频号"),
        ("toutiao", "今日头条"),
    ]
    AUTH_CHOICES = [("oauth", "OAuth"), ("api_key", "API Key")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="platform_accounts")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    display_name = models.CharField(max_length=255)
    auth_type = models.CharField(max_length=10, choices=AUTH_CHOICES)
    encrypted_credentials = models.BinaryField()  # AES-256-GCM
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publisher_platform_account"

    def __str__(self):
        return f"{self.user.email} — {self.platform}: {self.display_name}"


class PublishTask(models.Model):
    STATUS_CHOICES = [
        ("pending", "待发布"),
        ("publishing", "发布中"),
        ("success", "成功"),
        ("failed", "失败"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="publish_tasks")
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="publish_tasks")
    platform_account = models.ForeignKey(PlatformAccount, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    platform_post_id = models.CharField(max_length=255, null=True, blank=True)
    platform_post_url = models.URLField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publisher_publish_task"
        ordering = ["-created_at"]
