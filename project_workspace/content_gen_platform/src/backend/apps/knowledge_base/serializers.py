from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id", "name", "original_filename", "file_type",
            "file_size_bytes", "file_size_mb", "status", "chunk_count",
            "error_message", "progress", "progress_message",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "original_filename", "file_type", "file_size_bytes",
            "file_size_mb", "status", "chunk_count", "error_message",
            "progress", "progress_message",
            "created_at", "updated_at",
        )

    def get_file_size_mb(self, obj):
        return round(obj.file_size_bytes / (1024**2), 2)


class BatchUploadItemSerializer(serializers.Serializer):
    """Represents a single file entry in a batch upload result."""

    name = serializers.CharField()
    document_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_null=True)


class BatchUploadResultSerializer(serializers.Serializer):
    """Response body for POST /documents/batch-upload/."""

    accepted = BatchUploadItemSerializer(many=True)
    skipped = BatchUploadItemSerializer(many=True)
    rejected = BatchUploadItemSerializer(many=True)
    quota_exhausted = serializers.BooleanField()
    summary = serializers.CharField()
