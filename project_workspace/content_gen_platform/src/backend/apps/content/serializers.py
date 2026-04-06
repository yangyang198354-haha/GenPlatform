from rest_framework import serializers
from .models import Content


class ContentSerializer(serializers.ModelSerializer):
    word_count = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = (
            "id", "title", "body", "platform_type", "style", "word_limit",
            "status", "generation_prompt", "used_document_ids",
            "word_count", "created_at", "updated_at", "confirmed_at",
        )
        read_only_fields = ("id", "status", "word_count", "created_at", "updated_at", "confirmed_at")

    def get_word_count(self, obj):
        return len(obj.body)
