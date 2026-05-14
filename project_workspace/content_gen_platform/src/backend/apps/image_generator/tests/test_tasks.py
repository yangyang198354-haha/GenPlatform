"""
图片生成 Celery 任务单元测试——豆包 Seedream 版本。

测试策略：
- 所有外部依赖（httpx、settings_vault、media_library）均使用 mock
- 不启动真实 Celery worker，直接调用函数
- 覆盖主要分支：成功、API Key 缺失、内容审核拒绝、配额耗尽、认证失败

关联需求：FR-2、FR-3、FR-4、FR-5、ADR-03、ADR-07
"""
import pytest
from unittest.mock import patch, MagicMock

from apps.image_generator.models import ImageBatch, ImageGenerationRequest
from apps.image_generator.doubao_image_client import (
    ImageGenerationResult,
    DoubaoContentFilterError,
    DoubaoQuotaExceededError,
    DoubaoAuthError,
)
from apps.media_library.models import MediaItem
from core.encryption import encrypt
from apps.settings_vault.models import UserServiceConfig


def _make_doubao_config(user):
    """为用户创建有效的 doubao_image 服务配置。"""
    return UserServiceConfig.objects.create(
        user=user,
        service_type="doubao_image",
        encrypted_config=encrypt({"api_key": "test-ark-api-key"}),
        is_active=True,
    )


def _make_batch(user, n=1, is_img2img=False):
    """创建测试用 ImageBatch 及关联请求。"""
    batch = ImageBatch.objects.create(
        user=user,
        name="0513-1430 测试批次",
        model="doubao-seedream-4-5-251128",
        prompt="测试提示词",
        is_img2img=is_img2img,
        total_count=n,
        status="pending",
    )
    requests = []
    for _ in range(n):
        req = ImageGenerationRequest.objects.create(
            user=user,
            batch=batch,
            prompt="测试提示词",
            model="doubao-seedream-4-5-251128",
            provider="doubao",
            status="pending",
        )
        requests.append(req)
    return batch, requests


@pytest.mark.django_db
class TestGenerateImageTaskDoubao:
    """豆包 Ark 图片生成任务单元测试。"""

    def test_task_fails_when_no_doubao_config(self, user):
        """缺少 doubao_image API Key 配置时，批次状态应置为 failed（AC-01-4）。"""
        from apps.image_generator.tasks import generate_image_task

        batch, requests = _make_batch(user, n=1)

        with patch("apps.image_generator.tasks.push_notification_sync"):
            generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "failed"
        requests[0].refresh_from_db()
        assert requests[0].status == "failed"
        assert "API Key" in requests[0].error_message

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_completes_successfully_single_image(
        self, mock_generate, mock_create_media, mock_push, user
    ):
        """单张图片生成成功，批次状态应为 completed，MediaItem 已创建（AC-03-1）。"""
        from apps.image_generator.tasks import generate_image_task
        from django.core.files.base import ContentFile

        _make_doubao_config(user)
        batch, requests = _make_batch(user, n=1)

        # Mock Ark 返回
        mock_generate.return_value = ImageGenerationResult(
            image_urls=["https://example.com/test_img.jpg"]
        )

        # Mock MediaItem 创建
        media = MediaItem(
            owner=user, media_type="image", source="ai_generated", title="test"
        )
        media.file.save("test.jpg", ContentFile(b"fake_image_data"), save=True)
        mock_create_media.return_value = media

        generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "completed"
        assert batch.completed_count == 1

        requests[0].refresh_from_db()
        assert requests[0].status == "completed"
        assert requests[0].media_item_id == media.pk
        assert requests[0].provider == "doubao"

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_fails_on_content_filter(self, mock_generate, mock_push, user):
        """内容审核拒绝时，批次状态应为 failed，错误提示明确（ADR-07）。"""
        from apps.image_generator.tasks import generate_image_task

        _make_doubao_config(user)
        batch, requests = _make_batch(user, n=1)

        mock_generate.side_effect = DoubaoContentFilterError("内容违规")

        generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "failed"
        requests[0].refresh_from_db()
        assert requests[0].status == "failed"
        assert "不允许的内容" in requests[0].error_message

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_fails_on_quota_exceeded(self, mock_generate, mock_push, user):
        """配额耗尽时，批次状态应为 failed，错误提示正确（ADR-07）。"""
        from apps.image_generator.tasks import generate_image_task

        _make_doubao_config(user)
        batch, _ = _make_batch(user, n=1)

        mock_generate.side_effect = DoubaoQuotaExceededError("429")

        generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "failed"

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_fails_on_auth_error(self, mock_generate, mock_push, user):
        """API Key 无效时，批次状态应为 failed（ADR-07）。"""
        from apps.image_generator.tasks import generate_image_task

        _make_doubao_config(user)
        batch, _ = _make_batch(user, n=1)

        mock_generate.side_effect = DoubaoAuthError("401")

        generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "failed"

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_handles_partial_failure(
        self, mock_generate, mock_create_media, mock_push, user
    ):
        """2 张中 1 张入库失败时，批次状态应为 partial_failed（AC-04-4）。"""
        from apps.image_generator.tasks import generate_image_task
        from django.core.files.base import ContentFile

        _make_doubao_config(user)
        batch, requests = _make_batch(user, n=2)

        mock_generate.return_value = ImageGenerationResult(
            image_urls=[
                "https://example.com/img1.jpg",
                "https://example.com/img2.jpg",
            ]
        )

        # 第一张成功，第二张失败
        media = MediaItem(
            owner=user, media_type="image", source="ai_generated", title="ok"
        )
        media.file.save("ok.jpg", ContentFile(b"ok"), save=True)

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return media
            raise RuntimeError("下载失败")

        mock_create_media.side_effect = side_effect

        generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "partial_failed"
        assert batch.completed_count == 1

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_passes_provider_doubao_to_media_library(
        self, mock_generate, mock_create_media, mock_push, user
    ):
        """
        任务调用 create_media_item_from_url 时，必须传入 provider='doubao'（FR-4）。

        这是 Canary 守卫测试：确保 provider 参数始终正确传递，
        保证 MediaItem 能区分豆包来源与历史即梦来源（OQ-5）。
        """
        from apps.image_generator.tasks import generate_image_task
        from django.core.files.base import ContentFile

        _make_doubao_config(user)
        batch, requests = _make_batch(user, n=1)

        mock_generate.return_value = ImageGenerationResult(
            image_urls=["https://example.com/test.jpg"]
        )

        media = MediaItem(
            owner=user, media_type="image", source="ai_generated", title="test"
        )
        media.file.save("test.jpg", ContentFile(b"fake"), save=True)
        mock_create_media.return_value = media

        generate_image_task(batch.pk)

        # 验证 provider="doubao" 被正确传入 create_media_item_from_url
        mock_create_media.assert_called_once()
        call_kwargs = mock_create_media.call_args[1]
        assert call_kwargs.get("provider") == "doubao", (
            f"provider 参数应为 'doubao'，实际传入：{call_kwargs.get('provider')}"
        )

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_nonexistent_batch(self, mock_generate, mock_push, user):
        """批次 ID 不存在时，任务应安全退出，不抛异常。"""
        from apps.image_generator.tasks import generate_image_task

        # 应静默退出，不崩溃
        generate_image_task(99999)

        # 未调用 Ark 客户端
        mock_generate.assert_not_called()

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_task_batch_status_update_to_completed(
        self, mock_generate, mock_create_media, mock_push, user
    ):
        """4 张全部成功时，批次状态应更新为 completed，completed_count=4（AC-04-3）。"""
        from apps.image_generator.tasks import generate_image_task
        from django.core.files.base import ContentFile

        _make_doubao_config(user)
        batch, requests = _make_batch(user, n=4)

        mock_generate.return_value = ImageGenerationResult(
            image_urls=[f"https://example.com/img{i}.jpg" for i in range(4)]
        )

        media_items = []
        for i in range(4):
            m = MediaItem(
                owner=user, media_type="image", source="ai_generated", title=f"m{i}"
            )
            m.file.save(f"m{i}.jpg", ContentFile(b"data"), save=True)
            media_items.append(m)

        mock_create_media.side_effect = media_items

        generate_image_task(batch.pk)

        batch.refresh_from_db()
        assert batch.status == "completed"
        assert batch.completed_count == 4
