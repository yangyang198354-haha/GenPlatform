from django.db import models
from apps.accounts.models import User
from apps.content.models import Content


class VideoProject(models.Model):
    STATUS_CHOICES = [
        ("draft", "草稿"),
        ("generating", "生成中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="video_projects")
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="video_projects")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    final_video_path = models.CharField(max_length=1024, blank=True)
    jimeng_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video_project"
        ordering = ["-created_at"]


class Scene(models.Model):
    TRANSITION_CHOICES = [
        ("cut", "硬切"),
        ("fade", "淡入淡出"),
        ("push_pull", "推拉"),
    ]

    video_project = models.ForeignKey(
        VideoProject, on_delete=models.CASCADE, related_name="scenes"
    )
    scene_index = models.IntegerField()
    scene_prompt = models.TextField()       # 画面描述提示词
    narration = models.TextField()          # 配音文案
    voice_style = models.JSONField(
        default=dict
    )  # {speed: "normal", emotion: "neutral", voice_id: "zh_female_1"}
    duration_sec = models.IntegerField(default=5)  # 2-10 seconds
    transition = models.CharField(
        max_length=20, choices=TRANSITION_CHOICES, default="cut"
    )
    jimeng_clip_url = models.URLField(blank=True)  # URL returned by Jimeng API
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video_scene"
        ordering = ["scene_index"]
