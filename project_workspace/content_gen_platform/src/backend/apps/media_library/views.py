"""Media Library REST API views."""
import logging
import mimetypes
import os

from django.http import FileResponse, Http404
from django.shortcuts import redirect
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from core.pagination import StandardResultsSetPagination
from .models import MediaItem
from .serializers import MediaItemSerializer

logger = logging.getLogger(__name__)


class MediaListThrottle(UserRateThrottle):
    """Dedicated throttle for the media library listing endpoint.

    The listing page is loaded on every visit and every filter-tab switch.
    Using a separate scope (300/minute) prevents the media list from
    exhausting the shared global 'user' quota (1000/hour) when users
    browse quickly or open multiple tabs.
    """

    scope = "media_list"


# Allowed MIME types per media type
ALLOWED_TYPES = {
    "image": {"image/jpeg", "image/png", "image/gif", "image/webp"},
    "video": {"video/mp4", "video/quicktime", "video/x-msvideo"},
    "audio": {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/x-m4a"},
}

# Max upload sizes in bytes
MAX_SIZES = {
    "image": 20 * 1024 * 1024,   # 20 MB
    "video": 500 * 1024 * 1024,  # 500 MB
    "audio": 100 * 1024 * 1024,  # 100 MB
}


class MediaItemListView(APIView):
    """GET /api/v1/media/ — list the authenticated user's media items."""

    throttle_classes = [MediaListThrottle]

    def get(self, request):
        qs = MediaItem.objects.filter(owner=request.user)

        media_type = request.query_params.get("media_type")
        if media_type in ("image", "video", "audio"):
            qs = qs.filter(media_type=media_type)

        source = request.query_params.get("source")
        if source in ("ai_generated", "uploaded"):
            qs = qs.filter(source=source)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MediaItemSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class MediaItemUploadView(APIView):
    """POST /api/v1/media/upload/ — upload a file to the media library."""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "未上传文件"}, status=status.HTTP_400_BAD_REQUEST)

        media_type = request.data.get("media_type", "").lower()
        if media_type not in ("image", "video", "audio"):
            return Response(
                {"error": "media_type 必须为 image、video 或 audio"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate MIME type
        mime_type, _ = mimetypes.guess_type(uploaded_file.name)
        if not mime_type:
            mime_type = uploaded_file.content_type or ""
        if mime_type not in ALLOWED_TYPES.get(media_type, set()):
            return Response(
                {"error": f"不支持的文件格式: {mime_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file size
        if uploaded_file.size > MAX_SIZES[media_type]:
            max_mb = MAX_SIZES[media_type] // (1024 * 1024)
            return Response(
                {"error": f"文件超过大小限制（最大 {max_mb} MB）"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title = request.data.get("title", "").strip()
        if not title:
            title = os.path.splitext(uploaded_file.name)[0]

        item = MediaItem(
            owner=request.user,
            media_type=media_type,
            source="uploaded",
            title=title,
            file_size=uploaded_file.size,
        )
        item.file.save(uploaded_file.name, uploaded_file, save=True)

        serializer = MediaItemSerializer(item, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MediaItemDeleteView(APIView):
    """DELETE /api/v1/media/{pk}/ — delete a media item (owner only)."""

    def delete(self, request, pk):
        try:
            item = MediaItem.objects.get(pk=pk)
        except MediaItem.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if item.owner_id != request.user.pk:
            return Response({"error": "无权限"}, status=status.HTTP_403_FORBIDDEN)

        item.delete()  # model.delete() handles file cleanup
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediaItemDownloadView(APIView):
    """GET /api/v1/media/{pk}/download/ — redirect to media file URL."""

    def get(self, request, pk):
        try:
            item = MediaItem.objects.get(pk=pk)
        except MediaItem.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if item.owner_id != request.user.pk:
            return Response({"error": "无权限"}, status=status.HTTP_403_FORBIDDEN)

        if not item.file:
            raise Http404

        # Redirect to the media URL for nginx to serve directly
        return redirect(item.file.url)
