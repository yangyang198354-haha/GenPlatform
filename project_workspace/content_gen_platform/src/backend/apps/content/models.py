from django.db import models
from apps.accounts.models import User


class Content(models.Model):
    PLATFORM_CHOICES = [
        ("weibo", "微博"),
        ("xiaohongshu", "小红书"),
        ("wechat_mp", "微信公众号"),
        ("wechat_video", "微信视频号"),
        ("toutiao", "今日头条"),
        ("general", "通用"),
    ]
    STYLE_CHOICES = [
        ("professional", "专业"),
        ("casual", "口语"),
        ("humorous", "幽默"),
        ("promotion", "种草"),
    ]
    STATUS_CHOICES = [
        ("draft", "草稿"),
        ("confirmed", "已确认"),
        ("published", "已发布"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contents")
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    platform_type = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="general")
    style = models.CharField(max_length=20, choices=STYLE_CHOICES, default="professional")
    word_limit = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    generation_prompt = models.TextField(blank=True)
    used_document_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_content"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title or self.body[:30]}... ({self.status})"
