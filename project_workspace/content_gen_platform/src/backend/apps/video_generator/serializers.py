from rest_framework import serializers
from .models import VideoProject, Scene


class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = (
            "id", "scene_index", "scene_prompt", "narration",
            "voice_style", "duration_sec", "transition",
            "jimeng_clip_url", "is_deleted",
        )
        read_only_fields = ("id", "jimeng_clip_url")


class VideoProjectSerializer(serializers.ModelSerializer):
    scenes = SceneSerializer(many=True, read_only=True)
    content_title = serializers.CharField(source="content.title", read_only=True)
    total_duration_sec = serializers.SerializerMethodField()

    class Meta:
        model = VideoProject
        fields = (
            "id", "content_title", "status", "scenes",
            "total_duration_sec", "final_video_path",
            "jimeng_task_id", "error_message", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_total_duration_sec(self, obj):
        return sum(s.duration_sec for s in obj.scenes.filter(is_deleted=False))
