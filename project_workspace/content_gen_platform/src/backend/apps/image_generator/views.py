"""
图片生成模块 REST API 视图——豆包 Seedream 版本。

端点列表：
    POST   /api/v1/image/generate/              → ImageGenerationSubmitView
    GET    /api/v1/image/generate/{pk}/status/  → ImageGenerationStatusView
    GET    /api/v1/image/history/               → ImageGenerationListView
    GET    /api/v1/image/batches/               → ImageBatchListView（新增）
    GET    /api/v1/image/batches/{id}/          → ImageBatchDetailView（新增）
    PATCH  /api/v1/image/batches/{id}/          → ImageBatchDetailView（新增）
    DELETE /api/v1/image/batches/{id}/          → ImageBatchDetailView（新增）

关联需求：FR-2、FR-3、FR-5、US-05、AC-04-5、AC-05-5
"""
import logging
import os
import uuid
from datetime import datetime

from django.conf import settings
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ImageBatch, ImageGenerationRequest
from .serializers import (
    ImageBatchListSerializer,
    ImageBatchSerializer,
    ImageGenerationRequestSerializer,
    ImageGenerationStatusSerializer,
    ImageGenerationSubmitSerializer,
)
from .tasks import generate_image_task

logger = logging.getLogger(__name__)

MAX_REF_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_REF_IMAGE_TYPES = {"image/jpeg", "image/png"}
BATCH_NAME_PROMPT_MAX_LEN = 15  # 批次名中提示词摘要最大字数（OQ-3）


def _generate_batch_name(prompt: str) -> str:
    """
    生成批次默认名称：格式 MMDD-HHmm <prompt前N字>...（OQ-3，AC-04-1）

    示例：0513-1430 日落时分的海边...
    """
    now = datetime.now()
    time_prefix = now.strftime("%m%d-%H%M")
    # 提取提示词前 BATCH_NAME_PROMPT_MAX_LEN 个字符
    prompt_summary = prompt[:BATCH_NAME_PROMPT_MAX_LEN]
    suffix = "..." if len(prompt) > BATCH_NAME_PROMPT_MAX_LEN else ""
    return f"{time_prefix} {prompt_summary}{suffix}"


class ImageGenerationSubmitView(APIView):
    """
    POST /api/v1/image/generate/ — 提交豆包图片批次生成请求。

    成功响应：202 Accepted，含 batch_id / request_ids / batch_name
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        # ── 请求体校验（含 n≤4 硬约束，AC-04-5）──────────────────────────
        serializer = ImageGenerationSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            # 将 DRF 错误格式统一为 {"error": "..."} 结构
            errors = serializer.errors
            # 生成张数超限时给出明确提示
            if "n" in errors:
                return Response(
                    {"error": "单批次最多生成 4 张图片"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "model" in errors:
                return Response(
                    {"error": "不支持的模型版本"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # 其他校验错误
            first_field = next(iter(errors))
            first_msg = errors[first_field]
            if isinstance(first_msg, list):
                first_msg = first_msg[0]
            return Response(
                {"error": str(first_msg)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        prompt = data["prompt"]
        model = data["model"]
        n = data["n"]
        size = data["size"]
        advanced_params = serializer.get_advanced_params()

        # ── 参考图处理（图生图，FR-3）─────────────────────────────────────
        ref_image_path = ""
        ref_image_file = request.FILES.get("ref_image")
        is_img2img = False

        if ref_image_file:
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
            # 保存到临时目录
            temp_dir = os.path.join(settings.MEDIA_ROOT, "temp", uuid.uuid4().hex)
            os.makedirs(temp_dir, exist_ok=True)
            ext = ".png" if "png" in mime else ".jpg"
            temp_path = os.path.join(temp_dir, f"ref{ext}")
            with open(temp_path, "wb") as f:
                for chunk in ref_image_file.chunks():
                    f.write(chunk)
            ref_image_path = temp_path
            is_img2img = True

        # ── 创建 ImageBatch 记录（FR-5，AC-04-1）─────────────────────────
        batch_name = _generate_batch_name(prompt)
        batch = ImageBatch.objects.create(
            user=request.user,
            name=batch_name,
            model=model,
            prompt=prompt,
            is_img2img=is_img2img,
            total_count=n,
            status="pending",
        )

        # ── 创建 n 条 ImageGenerationRequest（关联批次，provider="doubao"）──
        gen_requests = []
        for _ in range(n):
            req = ImageGenerationRequest.objects.create(
                user=request.user,
                batch=batch,
                prompt=prompt,
                ref_image_path=ref_image_path,
                model=model,
                provider="doubao",
                status="pending",
            )
            gen_requests.append(req)

        logger.info(
            "用户 %s 提交图片生成请求：batch_id=%d model=%s n=%d is_img2img=%s",
            request.user.pk, batch.pk, model, n, is_img2img,
        )

        # ── 触发 Celery 任务（异步，NFR-1：POST 须在 500ms 内返回）──────────
        # 将高级参数和尺寸作为 kwargs 传入，避免在 DB 新增字段（ADR-04）
        generate_image_task.delay(
            batch.pk,
            advanced_params=advanced_params,
            size=size,
        )

        return Response(
            {
                "batch_id": batch.pk,
                "batch_name": batch.name,
                "request_ids": [r.pk for r in gen_requests],
                "status": "pending",
                "total_count": n,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImageGenerationStatusView(APIView):
    """GET /api/v1/image/generate/{pk}/status/ — 轮询单个请求状态（降级接口）。"""

    def get(self, request, pk):
        try:
            gen_request = ImageGenerationRequest.objects.get(pk=pk, user=request.user)
        except ImageGenerationRequest.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = ImageGenerationStatusSerializer(gen_request)
        return Response(serializer.data)


class ImageGenerationListView(APIView):
    """GET /api/v1/image/history/ — 用户图片生成历史（最近 50 条）。"""

    def get(self, request):
        requests_qs = ImageGenerationRequest.objects.filter(
            user=request.user
        ).order_by("-created_at")[:50]
        serializer = ImageGenerationRequestSerializer(requests_qs, many=True)
        return Response(serializer.data)


class ImageBatchListView(APIView):
    """
    GET /api/v1/image/batches/ — 获取用户批次列表（分页，按时间倒序，AC-05-1）。

    查询参数：
        page: 页码（默认 1）
        page_size: 每页数量（默认 20，最大 100）
    """

    def get(self, request):
        # 仅返回豆包新批次（batch 非 null），历史即梦数据不出现（AC-06-2）
        batches_qs = ImageBatch.objects.filter(user=request.user).order_by("-created_at")

        try:
            page_size = min(int(request.query_params.get("page_size", 20)), 100)
        except (ValueError, TypeError):
            page_size = 20

        paginator = Paginator(batches_qs, page_size)
        try:
            page_num = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            page_num = 1

        page = paginator.get_page(page_num)
        serializer = ImageBatchListSerializer(page.object_list, many=True)

        return Response(
            {
                "count": paginator.count,
                "next": (
                    f"?page={page_num + 1}&page_size={page_size}"
                    if page.has_next()
                    else None
                ),
                "previous": (
                    f"?page={page_num - 1}&page_size={page_size}"
                    if page.has_previous()
                    else None
                ),
                "results": serializer.data,
            }
        )


class ImageBatchDetailView(APIView):
    """
    GET    /api/v1/image/batches/{id}/ — 批次详情（含图片列表，AC-05-2）
    PATCH  /api/v1/image/batches/{id}/ — 重命名批次（AC-05-3）
    DELETE /api/v1/image/batches/{id}/ — 删除批次（AC-05-4，AC-05-5）
    """

    def _get_batch(self, pk, user):
        """获取属于当前用户的批次，不存在时返回 None。"""
        try:
            return ImageBatch.objects.prefetch_related("requests__media_item").get(
                pk=pk, user=user
            )
        except ImageBatch.DoesNotExist:
            return None

    def get(self, request, pk):
        """获取批次详情（含图片列表，AC-05-2）。"""
        batch = self._get_batch(pk, request.user)
        if batch is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ImageBatchSerializer(batch)
        return Response(serializer.data)

    def patch(self, request, pk):
        """
        重命名批次（AC-05-3）。

        请求体：{"name": "新名称"}
        """
        batch = self._get_batch(pk, request.user)
        if batch is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # 只允许修改 name 字段
        serializer = ImageBatchSerializer(batch, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 确认只更新 name
        if "name" not in serializer.validated_data:
            return Response(
                {"error": "PATCH 仅支持修改 name 字段"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_name = serializer.validated_data["name"]
        if not new_name.strip():
            return Response(
                {"name": ["该字段不能为空。"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        batch.name = new_name
        batch.save(update_fields=["name"])
        return Response(ImageBatchListSerializer(batch).data)

    def delete(self, request, pk):
        """
        删除批次及批次内所有图片（AC-05-4，AC-05-5）。

        生成中（status=processing）的批次不可删除（409 Conflict）。
        级联删除：ImageBatch → ImageGenerationRequest → MediaItem（通过信号触发）。
        """
        batch = self._get_batch(pk, request.user)
        if batch is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # 生成中不可删除（AC-05-5）
        if batch.status == "processing":
            return Response(
                {"error": "批次生成中，无法删除"},
                status=status.HTTP_409_CONFLICT,
            )

        # 级联删除：先删除关联的 MediaItem 和 ImageGenerationRequest
        from apps.media_library.models import MediaItem

        for req in batch.requests.select_related("media_item").all():
            if req.media_item_id:
                try:
                    req.media_item.delete()
                except Exception as exc:
                    logger.warning(
                        "删除 MediaItem #%d 失败：%s", req.media_item_id, exc
                    )
            req.delete()

        # 最后删除批次本身
        batch.delete()

        logger.info(
            "用户 %s 删除批次 #%d（级联删除 MediaItem）",
            request.user.pk, pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
