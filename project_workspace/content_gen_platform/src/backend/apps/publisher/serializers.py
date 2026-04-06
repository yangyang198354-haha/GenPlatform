from rest_framework import serializers
from .models import PlatformAccount, PublishTask


class PlatformAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformAccount
        fields = ("id", "platform", "display_name", "auth_type", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class PublishTaskSerializer(serializers.ModelSerializer):
    platform = serializers.CharField(source="platform_account.platform", read_only=True)
    platform_display = serializers.CharField(
        source="platform_account.get_platform_display", read_only=True
    )
    content_title = serializers.CharField(source="content.title", read_only=True)

    class Meta:
        model = PublishTask
        fields = (
            "id", "platform", "platform_display", "content_title",
            "status", "scheduled_at", "published_at",
            "platform_post_id", "platform_post_url",
            "error_message", "retry_count", "created_at",
        )
        read_only_fields = fields
