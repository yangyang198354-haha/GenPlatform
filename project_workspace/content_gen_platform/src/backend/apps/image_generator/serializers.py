"""Image Generator serializers."""
from rest_framework import serializers
from .models import ImageGenerationRequest


class ImageGenerationRequestSerializer(serializers.ModelSerializer):
    media_item_id = serializers.PrimaryKeyRelatedField(
        source="media_item", read_only=True
    )

    class Meta:
        model = ImageGenerationRequest
        fields = (
            "id", "status", "prompt", "progress",
            "jimeng_task_id", "result_image_url",
            "media_item_id", "error_message",
            "created_at",
        )
        read_only_fields = fields


class ImageGenerationStatusSerializer(serializers.ModelSerializer):
    media_item_id = serializers.PrimaryKeyRelatedField(
        source="media_item", read_only=True
    )

    class Meta:
        model = ImageGenerationRequest
        fields = (
            "id", "status", "progress",
            "media_item_id", "error_message",
        )
        read_only_fields = fields
