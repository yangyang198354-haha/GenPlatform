"""
图片生成模块视图单元测试——豆包 Seedream 版本。

测试内容：
- POST /api/v1/image/generate/（豆包新接口，含 n≤4 约束）
- GET /api/v1/image/generate/{pk}/status/（降级轮询，保留）
- GET /api/v1/image/history/（历史，保留）
- GET/PATCH/DELETE /api/v1/image/batches/（新增批次管理）

关联需求：FR-2、FR-3、FR-5、US-05、AC-01-5、AC-04-5、AC-05-3、AC-05-4、AC-05-5
"""
import io
import pytest
from unittest.mock import MagicMock, patch

from rest_framework import status

from apps.image_generator.models import ImageBatch, ImageGenerationRequest
from apps.media_library.models import MediaItem


@pytest.mark.django_db
class TestImageGenerationSubmitView:
    """POST /api/v1/image/generate/ 测试（豆包版本）。"""

    def test_submit_valid_prompt_returns_202(self, auth_client):
        """有效提示词提交返回 202，响应包含 batch_id 和 request_ids（AC-01-2）。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "日落时分的海边灯塔", "model": "doubao-seedream-4-5-251128", "n": 1},
                format="json",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert "batch_id" in resp.data
        assert "request_ids" in resp.data
        assert resp.data["total_count"] == 1
        assert resp.data["status"] == "pending"

    def test_submit_creates_batch_and_requests(self, auth_client):
        """提交后应创建 ImageBatch 和 n 条 ImageGenerationRequest。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "测试提示词", "model": "doubao-seedream-4-5-251128", "n": 2},
                format="json",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        batch_id = resp.data["batch_id"]
        assert ImageBatch.objects.filter(pk=batch_id, user=user).exists()
        assert ImageGenerationRequest.objects.filter(batch_id=batch_id).count() == 2

    def test_submit_empty_prompt_returns_400(self, auth_client):
        """提示词为空返回 400。"""
        client, _ = auth_client
        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": ""},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_submit_n_exceeds_4_returns_400(self, auth_client):
        """n>4 返回 400，提示"单批次最多生成 4 张"（AC-04-5）。"""
        client, _ = auth_client
        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": "test", "model": "doubao-seedream-4-5-251128", "n": 5},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "4" in resp.data.get("error", "")

    def test_submit_invalid_model_returns_400(self, auth_client):
        """不支持的模型返回 400（AC-01-5）。"""
        client, _ = auth_client
        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": "test", "model": "Jimeng-v1"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "模型" in resp.data.get("error", "")

    def test_submit_with_valid_ref_image(self, auth_client):
        """上传有效参考图（图生图），应返回 202（FR-3）。"""
        client, user = auth_client
        fake_img = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)
        fake_img.name = "ref.jpg"
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "测试图生图", "model": "doubao-seedream-4-5-251128", "ref_image": fake_img},
                format="multipart",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED

    def test_submit_invalid_ref_image_format_returns_400(self, auth_client):
        """参考图格式为 GIF 时返回 400（AC-02-3）。"""
        client, _ = auth_client
        fake_gif = io.BytesIO(b"GIF89a" + b"\x00" * 100)
        fake_gif.name = "ref.gif"
        resp = client.post(
            "/api/v1/image/generate/",
            {"prompt": "test", "ref_image": fake_gif},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "格式" in resp.data.get("error", "")

    def test_submit_requires_auth(self, api_client):
        """未登录访问返回 401。"""
        resp = api_client.post("/api/v1/image/generate/", {"prompt": "test"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_submit_triggers_celery_task(self, auth_client):
        """提交后应触发 Celery 任务，传入 batch_id。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            client.post(
                "/api/v1/image/generate/",
                {"prompt": "test", "model": "doubao-seedream-4-5-251128"},
                format="json",
            )
            mock_task.delay.assert_called_once()
            # 验证传入的是 batch_id（整数）
            called_arg = mock_task.delay.call_args[0][0]
            assert isinstance(called_arg, int)

    def test_batch_name_format(self, auth_client):
        """批次名称格式应为 MMDD-HHmm + prompt 摘要（OQ-3，AC-04-1）。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "日落时分的海边灯塔", "model": "doubao-seedream-4-5-251128"},
                format="json",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        batch_name = resp.data["batch_name"]
        # 名称应以 MMDD-HHmm 格式开头（6位数字+横线+4位数字+空格）
        import re
        assert re.match(r"^\d{4}-\d{4} ", batch_name), f"批次名称格式不符：{batch_name}"

    def test_provider_is_doubao_for_new_requests(self, auth_client):
        """新提交的图片生成请求 provider 字段应为 'doubao'（FR-4，OQ-5）。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {"prompt": "test", "model": "doubao-seedream-4-5-251128"},
                format="json",
            )
        batch_id = resp.data["batch_id"]
        requests = ImageGenerationRequest.objects.filter(batch_id=batch_id)
        for req in requests:
            assert req.provider == "doubao"

    # ── v1.2 新增：尺寸三模式透传测试 ─────────────────────────────────────────

    def test_submit_tier_mode_size_is_normalized(self, auth_client):
        """v1.2 TC-VIEW-01: size_mode=tier, size_tier=3K → task.delay 接收 size='3072x3072'。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {
                    "prompt": "test",
                    "model": "doubao-seedream-4-5-251128",
                    "size_mode": "tier",
                    "size_tier": "3K",
                },
                format="json",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        # 验证 task.delay 的 size 参数已归一化
        call_kwargs = mock_task.delay.call_args[1]
        assert call_kwargs.get("size") == "3072x3072"

    def test_submit_ratio_mode_size_is_normalized(self, auth_client):
        """v1.2 TC-VIEW-02: size_mode=ratio, size_ratio=9:16, size_tier=3K → size='2160x3840'。"""
        client, user = auth_client
        with patch("apps.image_generator.views.generate_image_task") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/image/generate/",
                {
                    "prompt": "test",
                    "model": "doubao-seedream-4-5-251128",
                    "size_mode": "ratio",
                    "size_ratio": "9:16",
                    "size_tier": "3K",
                },
                format="json",
            )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        call_kwargs = mock_task.delay.call_args[1]
        assert call_kwargs.get("size") == "2160x3840"

    def test_submit_invalid_pixel_size_returns_400(self, auth_client):
        """v1.2 TC-VIEW-03: size_mode=pixel 配合非法 size → 400（AC-01-2）。"""
        client, _ = auth_client
        resp = client.post(
            "/api/v1/image/generate/",
            {
                "prompt": "test",
                "size_mode": "pixel",
                "size": "999x999",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestImageGenerationStatusView:
    """GET /api/v1/image/generate/{pk}/status/ 测试（降级轮询接口）。"""

    def test_get_status_own_request(self, auth_client):
        client, user = auth_client
        req = ImageGenerationRequest.objects.create(
            user=user, prompt="test", status="processing", progress=50
        )
        resp = client.get(f"/api/v1/image/generate/{req.pk}/status/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "processing"
        assert resp.data["progress"] == 50

    def test_get_status_other_user_returns_404(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2
        req = ImageGenerationRequest.objects.create(user=user2, prompt="other")
        resp = client.get(f"/api/v1/image/generate/{req.pk}/status/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_status_nonexistent_returns_404(self, auth_client):
        client, _ = auth_client
        resp = client.get("/api/v1/image/generate/99999/status/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestImageGenerationListView:
    """GET /api/v1/image/history/ 测试（历史，兼容即梦历史数据）。"""

    def test_history_returns_own_requests(self, auth_client, auth_client2):
        client, user = auth_client
        client2, user2 = auth_client2
        ImageGenerationRequest.objects.create(user=user, prompt="mine")
        ImageGenerationRequest.objects.create(user=user2, prompt="theirs")
        resp = client.get("/api/v1/image/history/")
        assert resp.status_code == status.HTTP_200_OK
        prompts = [r["prompt"] for r in resp.data]
        assert "mine" in prompts
        assert "theirs" not in prompts


@pytest.mark.django_db
class TestImageBatchListView:
    """GET /api/v1/image/batches/ 批次列表测试（US-05，AC-05-1）。"""

    def _create_batch(self, user, name="test"):
        return ImageBatch.objects.create(
            user=user,
            name=name,
            model="doubao-seedream-4-5-251128",
            prompt="test",
            total_count=1,
            status="completed",
        )

    def test_list_batches_own_only(self, auth_client, auth_client2):
        """批次列表只返回当前用户的批次。"""
        client, user = auth_client
        client2, user2 = auth_client2
        self._create_batch(user, "我的批次")
        self._create_batch(user2, "他人批次")
        resp = client.get("/api/v1/image/batches/")
        assert resp.status_code == status.HTTP_200_OK
        names = [b["name"] for b in resp.data["results"]]
        assert "我的批次" in names
        assert "他人批次" not in names

    def test_list_batches_pagination(self, auth_client):
        """批次列表包含分页信息。"""
        client, user = auth_client
        resp = client.get("/api/v1/image/batches/")
        assert resp.status_code == status.HTTP_200_OK
        assert "count" in resp.data
        assert "results" in resp.data

    def test_list_batches_requires_auth(self, api_client):
        resp = api_client.get("/api/v1/image/batches/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestImageBatchDetailView:
    """GET/PATCH/DELETE /api/v1/image/batches/{id}/ 批次详情测试（US-05）。"""

    def _create_batch(self, user, status="completed"):
        return ImageBatch.objects.create(
            user=user,
            name="原始名称",
            model="doubao-seedream-4-5-251128",
            prompt="test",
            total_count=1,
            status=status,
        )

    def test_get_batch_detail(self, auth_client):
        """获取批次详情（AC-05-2）。"""
        client, user = auth_client
        batch = self._create_batch(user)
        resp = client.get(f"/api/v1/image/batches/{batch.pk}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "原始名称"
        assert "requests" in resp.data

    def test_get_batch_other_user_returns_404(self, auth_client, auth_client2):
        """访问他人批次应返回 404。"""
        client, user = auth_client
        client2, user2 = auth_client2
        batch = self._create_batch(user2)
        resp = client.get(f"/api/v1/image/batches/{batch.pk}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_rename_batch(self, auth_client):
        """PATCH 重命名批次（AC-05-3）。"""
        client, user = auth_client
        batch = self._create_batch(user)
        resp = client.patch(
            f"/api/v1/image/batches/{batch.pk}/",
            {"name": "新名称"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        batch.refresh_from_db()
        assert batch.name == "新名称"

    def test_rename_batch_empty_name_returns_400(self, auth_client):
        """PATCH 提交空名称应返回 400。"""
        client, user = auth_client
        batch = self._create_batch(user)
        resp = client.patch(
            f"/api/v1/image/batches/{batch.pk}/",
            {"name": ""},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_batch_completed(self, auth_client):
        """DELETE 删除已完成批次应返回 204（AC-05-4）。"""
        client, user = auth_client
        batch = self._create_batch(user, status="completed")
        resp = client.delete(f"/api/v1/image/batches/{batch.pk}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not ImageBatch.objects.filter(pk=batch.pk).exists()

    def test_delete_batch_processing_returns_409(self, auth_client):
        """DELETE 生成中批次应返回 409 Conflict（AC-05-5）。"""
        client, user = auth_client
        batch = self._create_batch(user, status="processing")
        resp = client.delete(f"/api/v1/image/batches/{batch.pk}/")
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert "生成中" in resp.data.get("error", "")

    def test_delete_batch_other_user_returns_404(self, auth_client, auth_client2):
        """DELETE 他人批次应返回 404。"""
        client, user = auth_client
        client2, user2 = auth_client2
        batch = self._create_batch(user2)
        resp = client.delete(f"/api/v1/image/batches/{batch.pk}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_batch_cascades_media_items(self, auth_client):
        """DELETE 批次时，关联的 MediaItem 也应被删除（AC-05-4）。"""
        from django.core.files.base import ContentFile

        client, user = auth_client
        batch = self._create_batch(user)

        # 创建 MediaItem 并关联到请求
        media = MediaItem(owner=user, media_type="image", source="ai_generated", title="t")
        media.file.save("test.jpg", ContentFile(b"data"), save=True)
        media_pk = media.pk

        req = ImageGenerationRequest.objects.create(
            user=user, batch=batch, prompt="test",
            model="doubao-seedream-4-5-251128", provider="doubao",
            media_item=media, status="completed",
        )

        resp = client.delete(f"/api/v1/image/batches/{batch.pk}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        # MediaItem 应被删除
        assert not MediaItem.objects.filter(pk=media_pk).exists()
