"""Media Library serializers."""
from rest_framework import serializers
from .models import MediaItem


class MediaItemSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaItem
        fields = (
            "id", "media_type", "source", "title",
            "file_url", "thumbnail_url",
            "file_size", "duration_sec",
            "created_at",
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file:
            url = obj.file.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_thumbnail_url(self, obj):
        request = self.context.get("request")
        if obj.thumbnail:
            url = obj.thumbnail.url
            return request.build_absolute_uri(url) if request else url
        return None
