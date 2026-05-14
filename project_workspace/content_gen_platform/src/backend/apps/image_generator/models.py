"""
图片生成模块数据模型。

包含：
- ImageBatch：一次提交生成的图片批次记录（FR-5，ADR-04）
- ImageGenerationRequest：单张图片生成请求，关联到批次（FR-2、FR-3）
"""
from django.db import models
from apps.accounts.models import User


class ImageBatch(models.Model):
    """
    图片批次记录——用户每次点击"生成"创建一条记录。
    关联需求：FR-5、ADR-04。
    """

    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("processing", "生成中"),
        ("completed", "已完成"),
        ("partial_failed", "部分失败"),
        ("failed", "失败"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="image_batches",
        verbose_name="所属用户",
    )
    name = models.CharField(
        max_length=255,
        verbose_name="批次名称",
        help_text="默认为时间戳+提示词摘要，用户可重命名（AC-05-3）",
    )
    model = models.CharField(
        max_length=64,
        verbose_name="豆包模型版本",
        help_text="Ark model ID，如 doubao-seedream-4-5-251128",
    )
    prompt = models.TextField(verbose_name="提示词")
    is_img2img = models.BooleanField(default=False, verbose_name="是否图生图")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="批次状态",
    )
    # total_count 取值范围 1-4，DB 层 CheckConstraint 保证（OQ-4）
    total_count = models.IntegerField(verbose_name="预计生成张数（1-4）")
    completed_count = models.IntegerField(default=0, verbose_name="已完成张数")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "image_batch"
        ordering = ["-created_at"]
        verbose_name = "图片批次"
        verbose_name_plural = "图片批次"
        constraints = [
            models.CheckConstraint(
                check=models.Q(total_count__gte=1) & models.Q(total_count__lte=4),
                name="image_batch_total_count_1_to_4",
            )
        ]

    def __str__(self):
        return f"ImageBatch #{self.pk} [{self.status}] {self.name}"


class ImageGenerationRequest(models.Model):
    """
    单张图片生成请求记录。
    改造后关联 ImageBatch；历史即梦数据 batch=null，provider=''（OQ-5）。
    """

    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("processing", "生成中"),
        ("completed", "已完成"),
        ("failed", "失败"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="image_generation_requests",
    )
    # 关联批次（新豆包数据必填；历史即梦数据为 null，OQ-5）
    batch = models.ForeignKey(
        "ImageBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requests",
        verbose_name="所属批次",
    )
    prompt = models.TextField()
    ref_image_path = models.CharField(max_length=1024, blank=True)  # 临时参考图路径
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # 即梦历史字段保留（历史数据兼容，不再写入新数据，ADR-02）
    jimeng_task_id = models.CharField(max_length=255, blank=True)
    result_image_url = models.CharField(max_length=1024, blank=True)
    media_item = models.ForeignKey(
        "media_library.MediaItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="image_generation_requests",
    )
    error_message = models.TextField(blank=True)
    progress = models.IntegerField(default=0)  # 0-100
    # 豆包新增字段（ADR-04）
    model = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="豆包模型名",
        help_text="新豆包请求填写，历史即梦数据为空字符串",
    )
    provider = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="生成来源",
        help_text="'doubao' 或空字符串（即梦历史数据，OQ-5）",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "image_generation_request"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ImageRequest #{self.pk} [{self.status}] by {self.user.email}"
