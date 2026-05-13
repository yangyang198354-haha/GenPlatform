"""
图片生成模块模型单元测试——豆包 Seedream 版本。

测试内容：
- ImageGenerationRequest 基础行为（含新增 batch / model / provider 字段）
- ImageBatch 模型（新增，FR-5，ADR-04）
- DB CheckConstraint：total_count 1-4（OQ-4）

关联需求：FR-5、OQ-4、ADR-04
"""
import pytest
from django.db import IntegrityError, transaction

from apps.image_generator.models import ImageBatch, ImageGenerationRequest


@pytest.mark.django_db
class TestImageGenerationRequestModel:
    """ImageGenerationRequest 模型基础测试（含新增字段）。"""

    def test_create_request_basic(self, user):
        """基本创建，默认状态为 pending。"""
        req = ImageGenerationRequest.objects.create(
            user=user,
            prompt="日落时分的海边灯塔",
            status="pending",
        )
        assert req.pk is not None
        assert req.status == "pending"
        assert req.progress == 0
        assert req.jimeng_task_id == ""
        assert req.media_item is None

    def test_new_fields_have_defaults(self, user):
        """新增字段 batch / model / provider 有合理默认值（OQ-5：历史数据兼容）。"""
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="test"
        )
        assert req.batch is None
        assert req.model == ""
        assert req.provider == ""

    def test_create_request_with_doubao_fields(self, user):
        """创建豆包新数据时，batch / model / provider 字段正常写入。"""
        batch = ImageBatch.objects.create(
            user=user,
            name="0513-1430 测试",
            model="Doubao-Seedream-4.5",
            prompt="测试",
            total_count=1,
            status="pending",
        )
        req = ImageGenerationRequest.objects.create(
            user=user,
            batch=batch,
            prompt="测试",
            model="Doubao-Seedream-4.5",
            provider="doubao",
            status="pending",
        )
        assert req.batch_id == batch.pk
        assert req.model == "Doubao-Seedream-4.5"
        assert req.provider == "doubao"

    def test_default_status_is_pending(self, user):
        req = ImageGenerationRequest.objects.create(user=user, prompt="test")
        assert req.status == "pending"

    def test_str_representation(self, user):
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="test prompt", status="processing"
        )
        s = str(req)
        assert str(req.pk) in s
        assert "processing" in s

    def test_ordering_newest_first(self, user):
        r1 = ImageGenerationRequest.objects.create(user=user, prompt="first")
        r2 = ImageGenerationRequest.objects.create(user=user, prompt="second")
        qs = list(ImageGenerationRequest.objects.filter(user=user).order_by("-pk"))
        assert qs[0].pk == r2.pk

    def test_media_item_fk_nullable(self, user):
        req = ImageGenerationRequest.objects.create(user=user, prompt="test")
        assert req.media_item is None


@pytest.mark.django_db
class TestImageBatchModel:
    """ImageBatch 模型测试（FR-5，ADR-04，OQ-4）。"""

    def test_create_batch_basic(self, user):
        """基础批次创建，默认状态为 pending。"""
        batch = ImageBatch.objects.create(
            user=user,
            name="0513-1430 日落时分的海边...",
            model="Doubao-Seedream-4.5",
            prompt="日落时分的海边灯塔",
            total_count=2,
            status="pending",
        )
        assert batch.pk is not None
        assert batch.status == "pending"
        assert batch.completed_count == 0
        assert batch.total_count == 2
        assert batch.is_img2img is False

    def test_batch_name_format(self, user):
        """批次名称字段正确保存（OQ-3，AC-04-1）。"""
        name = "0513-1430 日落时分的海边..."
        batch = ImageBatch.objects.create(
            user=user, name=name, model="Doubao-Seedream-4.5",
            prompt="test", total_count=1,
        )
        batch.refresh_from_db()
        assert batch.name == name

    def test_batch_status_choices(self, user):
        """批次状态枚举值完整（含 partial_failed，AC-04-4）。"""
        valid_statuses = ["pending", "processing", "completed", "partial_failed", "failed"]
        for s in valid_statuses:
            batch = ImageBatch.objects.create(
                user=user, name=f"批次-{s}", model="Doubao-Seedream-4.5",
                prompt="test", total_count=1, status=s,
            )
            assert batch.status == s

    def test_ordering_newest_first(self, user):
        """批次列表按时间倒序（Meta.ordering）。"""
        b1 = ImageBatch.objects.create(
            user=user, name="b1", model="Doubao-Seedream-4.5",
            prompt="test", total_count=1,
        )
        b2 = ImageBatch.objects.create(
            user=user, name="b2", model="Doubao-Seedream-4.5",
            prompt="test", total_count=1,
        )
        qs = list(ImageBatch.objects.filter(user=user).order_by("-pk"))
        assert qs[0].pk == b2.pk

    def test_str_representation(self, user):
        batch = ImageBatch.objects.create(
            user=user, name="测试批次", model="Doubao-Seedream-4.5",
            prompt="test", total_count=1, status="pending",
        )
        s = str(batch)
        assert str(batch.pk) in s
        assert "pending" in s

    def test_total_count_1_is_valid(self, user):
        """total_count=1 在约束范围内，应正常创建（OQ-4）。"""
        batch = ImageBatch.objects.create(
            user=user, name="test", model="Doubao-Seedream-4.5",
            prompt="test", total_count=1,
        )
        assert batch.total_count == 1

    def test_total_count_4_is_valid(self, user):
        """total_count=4 在约束范围内，应正常创建（OQ-4）。"""
        batch = ImageBatch.objects.create(
            user=user, name="test", model="Doubao-Seedream-4.5",
            prompt="test", total_count=4,
        )
        assert batch.total_count == 4

    def test_total_count_0_violates_constraint(self, user):
        """total_count=0 违反 DB CheckConstraint，应抛出 IntegrityError（OQ-4）。"""
        with pytest.raises((IntegrityError, Exception)):
            with transaction.atomic():
                ImageBatch.objects.create(
                    user=user, name="bad", model="Doubao-Seedream-4.5",
                    prompt="test", total_count=0,
                )

    def test_total_count_5_violates_constraint(self, user):
        """total_count=5 违反 DB CheckConstraint，应抛出 IntegrityError（OQ-4，AC-04-5）。"""
        with pytest.raises((IntegrityError, Exception)):
            with transaction.atomic():
                ImageBatch.objects.create(
                    user=user, name="bad", model="Doubao-Seedream-4.5",
                    prompt="test", total_count=5,
                )

    def test_cascade_delete_requests_on_batch_delete(self, user):
        """删除批次时，关联的 ImageGenerationRequest 通过 FK SET_NULL 处理（ADR-04）。"""
        batch = ImageBatch.objects.create(
            user=user, name="test", model="Doubao-Seedream-4.5",
            prompt="test", total_count=1,
        )
        req = ImageGenerationRequest.objects.create(
            user=user, batch=batch, prompt="test",
            model="Doubao-Seedream-4.5", provider="doubao",
        )
        batch_pk = batch.pk
        req_pk = req.pk

        # 删除批次
        batch.delete()

        # 请求记录仍存在，batch 字段被置为 null（SET_NULL）
        req.refresh_from_db()
        assert req.batch is None

    def test_is_img2img_default_false(self, user):
        """is_img2img 默认为 False（文生图场景）。"""
        batch = ImageBatch.objects.create(
            user=user, name="test", model="Doubao-Seedream-4.5",
            prompt="test", total_count=1,
        )
        assert batch.is_img2img is False
