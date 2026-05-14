"""
图片生成模块序列化器。

包含：
- ImageGenerationSubmitSerializer: POST /api/v1/image/generate/ 请求体校验
  含 n≤4 硬约束（OQ-4，满足 AC-04-5）、模型枚举校验（满足 AC-01-5）
  以及 v1.2 新增的三模式尺寸归一化（size_mode / size_tier / size_ratio）
- ImageBatchSerializer: 批次详情序列化（含关联请求列表）
- ImageBatchListSerializer: 批次列表序列化（不含请求详情，减少响应体大小）
- ImageGenerationRequestSerializer: 请求记录序列化
- ImageGenerationStatusSerializer: 状态查询响应序列化

关联需求：FR-1.2、FR-2、FR-3、FR-5、OQ-4、AC-04-5、AC-01-5
"""
from rest_framework import serializers
from .models import ImageBatch, ImageGenerationRequest
from .size_normalizer import PIXEL_VALID_SIZES, normalize_size


class ImageGenerationSubmitSerializer(serializers.Serializer):
    """
    POST /api/v1/image/generate/ 请求体校验序列化器。

    三层约束中的序列化器层（第一层）：
    - n max_value=4 → OQ-4 硬约束（AC-04-5）
    - model ChoiceField → 枚举校验（AC-01-5）
    - size 三模式归一化 → v1.2 新增（FR-1.2）
    前端（第二层）和 DB CheckConstraint（第三层）共同构成三层防护。
    """

    SUPPORTED_MODELS = [
        "doubao-seedream-5-0-260128",
        "doubao-seedream-4-5-251128",
        "doubao-seedream-4-0-250828",
    ]

    prompt = serializers.CharField(
        min_length=1,
        max_length=500,
        help_text="提示词，1-500 字符",
    )
    model = serializers.ChoiceField(
        choices=SUPPORTED_MODELS,
        default="doubao-seedream-4-5-251128",
        help_text="豆包模型版本（AC-01-5：不在枚举中则返回 400）",
    )
    # OQ-4 硬约束：n 的 max_value=4（AC-04-5）
    n = serializers.IntegerField(
        min_value=1,
        max_value=4,
        default=1,
        help_text="生成张数 1-4（超过 4 张返回 400，AC-04-5）",
    )

    # ── v1.2 尺寸三模式字段 ────────────────────────────────────────────────────
    size_mode = serializers.ChoiceField(
        choices=["pixel", "tier", "ratio"],
        default="pixel",
        required=False,
        help_text="尺寸输入方式：pixel（像素精确）/ tier（档位）/ ratio（比例×档位组合）",
    )
    size = serializers.ChoiceField(
        choices=sorted(PIXEL_VALID_SIZES),
        default="2048x2048",
        required=False,
        help_text="size_mode=pixel 时使用，像素精确尺寸字符串（如 '2048x2048'）",
    )
    size_tier = serializers.ChoiceField(
        choices=["2K", "3K", "4K"],
        default="2K",
        required=False,
        help_text="size_mode=tier 时使用档位名；size_mode=ratio 时与 size_ratio 联合决定像素（默认 2K）",
    )
    size_ratio = serializers.ChoiceField(
        choices=["1:1", "16:9", "9:16", "4:3", "3:4"],
        default="1:1",
        required=False,
        help_text="size_mode=ratio 时使用，比例字符串；必须配合 size_tier 使用",
    )

    # ── 高级参数（折叠面板，OQ-2，不传则不透传给 Ark） ─────────────────────────
    seed = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="随机种子（可选）",
    )
    negative_prompt = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="负向提示词（可选）",
    )
    guidance_scale = serializers.FloatField(
        required=False,
        allow_null=True,
        help_text="CFG Scale（可选，默认 7.5）",
    )
    steps = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="推理步数（可选，4.0/4.5 支持；5.0 Lite 由 Task 层白名单过滤）",
    )
    watermark = serializers.BooleanField(
        required=False,
        help_text="是否添加水印（未传则不透传给 Ark，使用模型默认行为）",
    )

    def validate(self, data):
        """
        归一化 size，将三种输入方式统一为 validated_data['size']。
        ratio 模式下 size_tier 参与计算（默认 2K）。
        """
        try:
            normalized = normalize_size(
                size_mode=data.get("size_mode", "pixel"),
                size=data.get("size", "2048x2048"),
                size_tier=data.get("size_tier", "2K"),
                size_ratio=data.get("size_ratio", "1:1"),
            )
        except ValueError as e:
            raise serializers.ValidationError({"size": str(e)})
        data["size"] = normalized
        return data

    def get_advanced_params(self) -> dict:
        """
        从已验证数据中提取高级参数字典，供 View 层传入 Celery task。
        仅返回用户实际传入且非 None 的参数。
        """
        data = self.validated_data
        params = {}
        for key in ("seed", "negative_prompt", "guidance_scale", "steps", "watermark"):
            val = data.get(key)
            if val is not None and val != "":
                params[key] = val
        return params


class ImageGenerationRequestSerializer(serializers.ModelSerializer):
    """
    ImageGenerationRequest 基础序列化器。

    v1.2.1 新增：
    - thumbnail_url (SerializerMethodField): 优先返回 MediaItem.file.url（持久 URL），
      降级到 result_image_url（Ark CDN，约 24h 有效），两者均空则返回 ""。
    - result_image_url 显式暴露（原来字段存在但未在 fields 中声明）。
    """

    media_item_id = serializers.PrimaryKeyRelatedField(
        source="media_item", read_only=True
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source="batch", read_only=True
    )
    # v1.2.1 BUG-01：新增 thumbnail_url，两层降级逻辑（见 get_thumbnail_url）
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = ImageGenerationRequest
        fields = (
            "id",
            "status",
            "prompt",
            "progress",
            "provider",
            "model",
            "batch_id",
            "media_item_id",
            "result_image_url",   # v1.2.1：显式暴露（向后兼容，原字段已存在）
            "thumbnail_url",      # v1.2.1：新增，优先持久 URL
            "error_message",
            "created_at",
        )
        read_only_fields = fields

    def get_thumbnail_url(self, obj):
        """
        优先返回已入库的 MediaItem.file.url（持久存储，不过期）。
        若 MediaItem 不存在或 URL 构建失败，降级到 result_image_url（Ark CDN，约 24h 有效）。
        两者均空时返回空字符串（不报错，向后兼容历史即梦数据）。

        BUG-01 修复（v1.2.1）。
        """
        try:
            if obj.media_item and obj.media_item.file:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(obj.media_item.file.url)
                return obj.media_item.file.url
        except Exception:
            pass
        return obj.result_image_url or ""


class ImageGenerationStatusSerializer(serializers.ModelSerializer):
    """GET /api/v1/image/generate/{pk}/status/ 状态查询响应序列化器。"""

    media_item_id = serializers.PrimaryKeyRelatedField(
        source="media_item", read_only=True
    )

    class Meta:
        model = ImageGenerationRequest
        fields = (
            "id",
            "status",
            "progress",
            "media_item_id",
            "error_message",
        )
        read_only_fields = fields


class ImageBatchSerializer(serializers.ModelSerializer):
    """
    批次详情序列化器（含关联请求列表，用于 GET /api/v1/image/batches/{id}/）。
    name 字段可通过 PATCH 修改（重命名，AC-05-3）。
    """

    requests = ImageGenerationRequestSerializer(many=True, read_only=True)

    class Meta:
        model = ImageBatch
        fields = (
            "id",
            "name",
            "model",
            "prompt",
            "is_img2img",
            "status",
            "total_count",
            "completed_count",
            "created_at",
            "updated_at",
            "requests",
        )
        read_only_fields = (
            "id",
            "model",
            "prompt",
            "is_img2img",
            "status",
            "total_count",
            "completed_count",
            "created_at",
            "updated_at",
        )
        # name 字段可写，用于重命名（AC-05-3）


class ImageBatchListSerializer(serializers.ModelSerializer):
    """
    批次列表序列化器（不含 requests 详情，减少响应体大小）。
    用于 GET /api/v1/image/batches/（分页列表）。
    """

    class Meta:
        model = ImageBatch
        fields = (
            "id",
            "name",
            "model",
            "prompt",
            "is_img2img",
            "status",
            "total_count",
            "completed_count",
            "created_at",
        )
        read_only_fields = fields
