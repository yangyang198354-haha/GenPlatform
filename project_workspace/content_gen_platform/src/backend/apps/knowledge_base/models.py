from django.db import models
from pgvector.django import VectorField
from apps.accounts.models import User


class Document(models.Model):
    FILE_TYPE_CHOICES = [("pdf", "PDF"), ("docx", "Word"), ("txt", "TXT"), ("md", "Markdown")]
    STATUS_CHOICES = [("processing", "处理中"), ("available", "可用"), ("error", "错误")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
    name = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=1024)  # storage path
    file_size_bytes = models.BigIntegerField()
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="processing")
    chunk_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kb_document"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class DocumentChunk(models.Model):
    """A text chunk from a document with its vector embedding."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=1024)  # bge-m3 output dimension
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "kb_document_chunk"
        ordering = ["chunk_index"]
        indexes = [
            models.Index(fields=["document", "chunk_index"]),
        ]
