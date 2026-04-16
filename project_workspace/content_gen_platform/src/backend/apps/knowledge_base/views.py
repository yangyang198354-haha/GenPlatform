"""Knowledge base API views."""
import json
import os
from django.conf import settings
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document
from .serializers import DocumentSerializer, BatchUploadResultSerializer
from .tasks import process_document_task
from apps.accounts.models import User


ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB fallback (settings overrides this)


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


class DocumentBatchUploadView(APIView):
    """
    Batch upload endpoint for directory uploads.

    Accepts multiple files via ``files`` multipart field.
    Optionally accepts ``relative_paths`` as a JSON-encoded list of strings
    (one per file, in the same order) to record the original directory path.

    Processing strategy (REQ-FUNC-001, ADR-002):
    - Unsupported formats  → skipped (no error)
    - Files exceeding 50 MB → rejected with reason "file_too_large"
    - Files exceeding remaining quota → rejected with reason "quota_exceeded";
      once quota is exhausted further files are also rejected without writing
    - All others → accepted, Document created, Celery task fired
    """

    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"error": "所选目录中未包含受支持的文档"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse optional relative paths (one per file, same order)
        relative_paths_raw = request.data.get("relative_paths", "[]")
        try:
            relative_paths = json.loads(relative_paths_raw)
        except (ValueError, TypeError):
            relative_paths = []

        user: User = request.user
        # Refresh user from DB to get the latest used_storage_bytes
        user.refresh_from_db()

        max_size = getattr(settings, "MAX_DOCUMENT_SIZE_BYTES", MAX_FILE_SIZE_BYTES)
        upload_dir = os.path.join(settings.MEDIA_ROOT, "documents", str(user.pk))
        os.makedirs(upload_dir, exist_ok=True)

        accepted = []
        skipped = []
        rejected = []
        quota_exhausted = False

        for idx, file in enumerate(files):
            # Determine original filename from relative path (strip directory prefix)
            rel_path = relative_paths[idx] if idx < len(relative_paths) else file.name
            # Use only the basename as the display name / original_filename
            original_filename = os.path.basename(rel_path) or file.name

            ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""

            # --- Format check ---
            if ext not in ALLOWED_EXTENSIONS:
                skipped.append({
                    "name": original_filename,
                    "reason": "format_not_supported",
                })
                continue

            # --- Size check ---
            if file.size > max_size:
                rejected.append({
                    "name": original_filename,
                    "reason": "file_too_large",
                })
                continue

            # --- Quota check ---
            if quota_exhausted or not user.has_storage_quota(file.size):
                quota_exhausted = True
                rejected.append({
                    "name": original_filename,
                    "reason": "quota_exceeded",
                })
                continue

            # --- Write to disk ---
            safe_name = original_filename.replace("/", "_").replace("\\", "_")
            # Avoid collisions by prefixing with loop index when needed
            file_path = os.path.join(upload_dir, safe_name)
            if os.path.exists(file_path):
                base, dot_ext = os.path.splitext(safe_name)
                file_path = os.path.join(upload_dir, f"{base}_{idx}{dot_ext}")

            with open(file_path, "wb+") as dest:
                for chunk in file.chunks():
                    dest.write(chunk)

            # --- Create Document record ---
            doc = Document.objects.create(
                user=user,
                name=original_filename,
                original_filename=original_filename,
                file_path=file_path,
                file_size_bytes=file.size,
                file_type=ext,
                status="processing",
            )
            user.consume_storage(file.size)
            # Refresh so subsequent quota checks use updated used_storage_bytes
            user.refresh_from_db()

            process_document_task.delay(doc.pk)

            accepted.append({
                "name": original_filename,
                "document_id": doc.pk,
                "status": "processing",
            })

        # If no files were successfully accepted, return 400
        if not accepted:
            return Response(
                {"error": "所选目录中未包含受支持的文档"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build human-readable summary
        parts = []
        if accepted:
            parts.append(f"{len(accepted)} 个文件已提交处理")
        if skipped:
            parts.append(f"{len(skipped)} 个格式不支持已跳过")
        if rejected:
            reasons = {r["reason"] for r in rejected}
            if "file_too_large" in reasons:
                parts.append(f"{sum(1 for r in rejected if r['reason'] == 'file_too_large')} 个超过大小限制")
            if "quota_exceeded" in reasons:
                parts.append("配额已满，部分文件未能导入")

        summary = "；".join(parts) if parts else "无文件处理"

        result_data = {
            "accepted": accepted,
            "skipped": skipped,
            "rejected": rejected,
            "quota_exhausted": quota_exhausted,
            "summary": summary,
        }

        serializer = BatchUploadResultSerializer(data=result_data)
        serializer.is_valid(raise_exception=True)
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
