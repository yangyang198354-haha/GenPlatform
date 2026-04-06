"""Knowledge base API views."""
import os
from django.conf import settings
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import Document
from .serializers import DocumentSerializer
from .tasks import process_document_task
from apps.accounts.models import User


ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}


class DocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        qs = Document.objects.filter(user=self.request.user)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def create(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "文件不能为空"}, status=status.HTTP_400_BAD_REQUEST)

        ext = file.name.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {"error": f"不支持的文件格式，支持格式：{', '.join(ALLOWED_EXTENSIONS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if file.size > settings.MAX_DOCUMENT_SIZE_BYTES:
            return Response(
                {"error": "文件大小超过50MB限制"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user: User = request.user
        if not user.has_storage_quota(file.size):
            return Response(
                {"error": "存储空间不足，请删除部分文档后重试"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save file
        upload_dir = os.path.join(settings.MEDIA_ROOT, "documents", str(user.pk))
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = file.name.replace("/", "_").replace("\\", "_")
        file_path = os.path.join(upload_dir, safe_name)
        with open(file_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        doc = Document.objects.create(
            user=user,
            name=request.data.get("name", file.name),
            original_filename=file.name,
            file_path=file_path,
            file_size_bytes=file.size,
            file_type=ext,
            status="processing",
        )
        user.consume_storage(file.size)

        # Trigger async processing
        process_document_task.delay(doc.pk)

        serializer = DocumentSerializer(doc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        # Release storage quota
        self.request.user.release_storage(instance.file_size_bytes)
        # Delete physical file
        if os.path.exists(instance.file_path):
            os.remove(instance.file_path)
        # Cascade deletes DocumentChunk via FK
        instance.delete()
