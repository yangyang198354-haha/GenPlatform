"""Image Generator REST API views."""
import logging
import os
import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ImageGenerationRequest
from .serializers import ImageGenerationRequestSerializer, ImageGenerationStatusSerializer
from .tasks import generate_image_task

logger = logging.getLogger(__name__)

MAX_PROMPT_LEN = 500
MAX_REF_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_REF_IMAGE_TYPES = {"image/jpeg", "image/png"}


class ImageGenerationSubmitView(APIView):
    """POST /api/v1/image/generate/ — submit an image generation request."""
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        prompt = request.data.get("prompt", "").strip()
        if not prompt:
            return Response({"error": "提示词不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        if len(prompt) > MAX_PROMPT_LEN:
            return Response(
                {"error": f"提示词最多 {MAX_PROMPT_LEN} 个字符"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ref_image_path = ""
        ref_image_file = request.FILES.get("ref_image")
        if ref_image_file:
            # Validate
            mime = ref_image_file.content_type or ""
            if mime not in ALLOWED_REF_IMAGE_TYPES:
                return Response(
                    {"error": "参考图片仅支持 JPEG 和 PNG 格式"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if ref_image_file.size > MAX_REF_IMAGE_SIZE:
                return Response(
                    {"error": "参考图片大小不能超过 10 MB"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Save to temp directory
            temp_dir = os.path.join(settings.MEDIA_ROOT, "temp", uuid.uuid4().hex)
            os.makedirs(temp_dir, exist_ok=True)
            ext = ".jpg" if "jpeg" in mime else ".png"
            temp_path = os.path.join(temp_dir, f"ref{ext}")
            with open(temp_path, "wb") as f:
                for chunk in ref_image_file.chunks():
                    f.write(chunk)
            ref_image_path = temp_path

        gen_request = ImageGenerationRequest.objects.create(
            user=request.user,
            prompt=prompt,
            ref_image_path=ref_image_path,
            status="pending",
        )

        generate_image_task.delay(gen_request.pk)

        serializer = ImageGenerationRequestSerializer(gen_request)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class ImageGenerationStatusView(APIView):
    """GET /api/v1/image/generate/{pk}/status/ — poll task status."""

    def get(self, request, pk):
        try:
            gen_request = ImageGenerationRequest.objects.get(
                pk=pk, user=request.user
            )
        except ImageGenerationRequest.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = ImageGenerationStatusSerializer(gen_request)
        return Response(serializer.data)


class ImageGenerationListView(APIView):
    """GET /api/v1/image/history/ — list user's image generation history."""

    def get(self, request):
        requests_qs = ImageGenerationRequest.objects.filter(
            user=request.user
        ).order_by("-created_at")[:50]  # last 50 requests

        serializer = ImageGenerationRequestSerializer(requests_qs, many=True)
        return Response(serializer.data)
