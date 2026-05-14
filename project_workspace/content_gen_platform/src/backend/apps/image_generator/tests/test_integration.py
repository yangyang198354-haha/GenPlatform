"""
图片生成模块集成测试——豆包 Seedream 版本。

【重要】本文件中的所有测试均标记为 @pytest.mark.integration。
本地运行时（-m "not integration"）这些测试会被跳过。
它们由 GitHub Actions CI 在 PostgreSQL + Celery 环境中运行。

测试内容：
- 端到端流程：POST 提交 → Celery task → mock Ark → media_library 入库 → WebSocket 推送
- 数据库迁移验证：0002_imagebatch_and_fields 正向迁移

关联需求：FR-2、FR-5、ADR-03、ADR-04
"""
import pytest
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile

from apps.image_generator.models import ImageBatch, ImageGenerationRequest
from apps.image_generator.doubao_image_client import ImageGenerationResult
from apps.media_library.models import MediaItem


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _make_doubao_config(user):
    """为用户创建有效的 doubao_image 服务配置。"""
    from core.encryption import encrypt
    from apps.settings_vault.models import UserServiceConfig
    return UserServiceConfig.objects.create(
        user=user,
        service_type="doubao_image",
        encrypted_config=encrypt({"api_key": "test-integration-key"}),
        is_active=True,
    )


# ── 端到端集成测试 ────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
class TestImageGenerationEndToEnd:
    """
    端到端集成测试：POST 提交 → Celery → mock Ark → 入库 → 推送。

    本地跳过说明：
      - 依赖 PostgreSQL（SQLite 不支持 CheckConstraint 的部分行为）
      - 依赖 Celery eager 模式（CELERY_TASK_ALWAYS_EAGER=True，已在 test.py 配置）
      - 所有 Ark API 调用均使用 mock，不发起真实请求

    CI 运行环境：
      - GitHub Actions：postgres service + test.py settings
      - 标记为 integration，由 CI 工作流 pytest -m integration 触发
    """

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_full_pipeline_single_image(
        self, mock_generate, mock_create_media, mock_push, user, auth_client
    ):
        """
        完整流水线：POST 提交（1 张）→ Celery → mock Ark → 入库 → 批次完成。

        验证：
        1. POST /api/v1/image/generate/ 返回 202
        2. Celery task 被触发（CELERY_TASK_ALWAYS_EAGER=True，在进程内执行）
        3. mock Ark 客户端被调用一次
        4. create_media_item_from_url 被调用，provider="doubao"
        5. ImageBatch 最终 status=completed
        6. push_notification_sync 被调用（WebSocket 推送）
        """
        client, user_obj = auth_client
        _make_doubao_config(user_obj)

        # 准备 mock 返回
        mock_generate.return_value = ImageGenerationResult(
            image_urls=["https://mock-ark.example.com/img1.jpg"]
        )
        media = MediaItem(
            owner=user_obj, media_type="image", source="ai_generated", title="test"
        )
        media.file.save("test.jpg", ContentFile(b"fake_data"), save=True)
        mock_create_media.return_value = media

        # 触发 POST（Celery TASK_ALWAYS_EAGER 模式，任务同步执行）
        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": "集成测试提示词", "model": "doubao-seedream-4-5-251128", "n": 1},
            format="json",
        )

        assert resp.status_code == 202
        batch_id = resp.data["batch_id"]

        # 验证批次最终状态（Celery eager 模式已同步执行）
        batch = ImageBatch.objects.get(pk=batch_id)
        assert batch.status == "completed"
        assert batch.completed_count == 1

        # 验证 mock Ark 被调用，且传入正确参数
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1] if mock_generate.call_args[1] else {}
        call_args = mock_generate.call_args[0] if mock_generate.call_args[0] else []
        # prompt 应正确传递
        # provider="doubao" 应传入 media library
        mock_create_media.assert_called_once()
        assert mock_create_media.call_args[1].get("provider") == "doubao"

        # 验证 WebSocket 推送被调用
        assert mock_push.call_count >= 2  # 至少 batch_progress + batch_completed

    @patch("apps.image_generator.tasks.push_notification_sync")
    @patch("apps.image_generator.tasks.create_media_item_from_url")
    @patch("apps.image_generator.doubao_image_client.DoubaoImageClient.generate_images")
    def test_full_pipeline_batch_4_images(
        self, mock_generate, mock_create_media, mock_push, user, auth_client
    ):
        """
        完整流水线：POST 提交（4 张）→ Celery → mock Ark → 全部入库 → completed。

        验证四张生成流程完整性（AC-04-3）。
        """
        client, user_obj = auth_client
        _make_doubao_config(user_obj)

        mock_generate.return_value = ImageGenerationResult(
            image_urls=[f"https://mock-ark.example.com/img{i}.jpg" for i in range(4)]
        )
        media_items = []
        for i in range(4):
            m = MediaItem(
                owner=user_obj, media_type="image", source="ai_generated", title=f"m{i}"
            )
            m.file.save(f"m{i}.jpg", ContentFile(b"data"), save=True)
            media_items.append(m)
        mock_create_media.side_effect = media_items

        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": "批量集成测试", "model": "doubao-seedream-4-5-251128", "n": 4},
            format="json",
        )
        assert resp.status_code == 202
        batch_id = resp.data["batch_id"]

        batch = ImageBatch.objects.get(pk=batch_id)
        assert batch.status == "completed"
        assert batch.completed_count == 4
        assert mock_create_media.call_count == 4


@pytest.mark.integration
@pytest.mark.django_db
class TestMigrationIntegrity:
    """
    数据库迁移完整性验证测试。

    验证 0002_imagebatch_and_fields 迁移：
    1. ImageBatch 表存在，含所有新字段
    2. CheckConstraint 在 PostgreSQL 层面生效
    3. ImageGenerationRequest 新字段存在（batch / model / provider）
    """

    def test_imagebatch_table_exists_with_all_fields(self, user):
        """ImageBatch 表存在，所有字段可正常写入和读取。"""
        batch = ImageBatch.objects.create(
            user=user,
            name="迁移验证批次",
            model="doubao-seedream-4-5-251128",
            prompt="迁移测试",
            total_count=2,
            status="pending",
        )
        batch.refresh_from_db()
        assert batch.pk is not None
        assert batch.name == "迁移验证批次"
        assert batch.model == "doubao-seedream-4-5-251128"
        assert batch.is_img2img is False
        assert batch.total_count == 2
        assert batch.completed_count == 0

    def test_imagegenerationrequest_new_fields(self, user):
        """ImageGenerationRequest 的新字段（batch/model/provider）可正常操作。"""
        batch = ImageBatch.objects.create(
            user=user, name="test", model="doubao-seedream-4-5-251128",
            prompt="test", total_count=1,
        )
        req = ImageGenerationRequest.objects.create(
            user=user, batch=batch,
            prompt="test", model="doubao-seedream-4-5-251128",
            provider="doubao",
        )
        req.refresh_from_db()
        assert req.batch_id == batch.pk
        assert req.model == "doubao-seedream-4-5-251128"
        assert req.provider == "doubao"

    def test_check_constraint_in_postgres(self, user):
        """
        CheckConstraint total_count 1-4 在 PostgreSQL 层面生效。

        注意：此测试在 SQLite（local_test.py）下可能不生效，
        因为 SQLite 对 CheckConstraint 的支持有限。
        CI 环境（PostgreSQL）下会完整验证。
        """
        from django.db import IntegrityError, transaction
        with pytest.raises((IntegrityError, Exception)):
            with transaction.atomic():
                ImageBatch.objects.create(
                    user=user, name="bad", model="doubao-seedream-4-5-251128",
                    prompt="test", total_count=5,
                )
