"""
图片生成模块序列化器。

包含：
- ImageGenerationSubmitSerializer: POST /api/v1/image/generate/ 请求体校验
  含 n≤4 硬约束（OQ-4，满足 AC-04-5）和模型枚举校验（满足 AC-01-5）
- ImageBatchSerializer: 批次详情序列化（含关联请求列表）
- ImageBatchListSerializer: 批次列表序列化（不含请求详情，减少响应体大小）
- ImageGenerationRequestSerializer: 请求记录序列化
- ImageGenerationStatusSerializer: 状态查询响应序列化

关联需求：FR-2、FR-3、FR-5、OQ-4、AC-04-5、AC-01-5
"""
from rest_framework import serializers
from .models import ImageBatch, ImageGenerationRequest


class ImageGenerationSubmitSerializer(serializers.Serializer):
    """
    POST /api/v1/image/generate/ 请求体校验序列化器。

    三层约束中的序列化器层（第一层）：
    - n max_value=4 → OQ-4 硬约束（AC-04-5）
    - model ChoiceField → 枚举校验（AC-01-5）
    前端（第二层）和 DB CheckConstraint（第三层）共同构成三层防护。
    """

    SUPPORTED_MODELS = [
        "doubao-seedream-5-0-260128",
        "doubao-seedream-4-5-251128",
        "doubao-seedream-4-0-250828",
    ]
    SUPPORTED_SIZES = ["1024x1024", "1280x720", "720x1280"]

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
    size = serializers.ChoiceField(
        choices=SUPPORTED_SIZES,
        default="1024x1024",
        help_text="图片尺寸",
    )
    # 高级参数（折叠面板，OQ-2，不传则不透传给 Ark）
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
        help_text="CFG Scale（可选）",
    )
    steps = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="推理步数（可选，4.0/4.5 支持）",
    )
    watermark = serializers.BooleanField(
        required=False,
        help_text="是否添加水印（未传则不透传给 Ark，使用模型默认行为）",
    )

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
    """ImageGenerationRequest 基础序列化器。"""

    media_item_id = serializers.PrimaryKeyRelatedField(
        source="media_item", read_only=True
    )
    batch_id = serializers.PrimaryKeyRelatedField(
        source="batch", read_only=True
    )

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
            "error_message",
            "created_at",
        )
        read_only_fields = fields


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
