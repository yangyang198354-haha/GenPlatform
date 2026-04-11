"""Integration tests for video_generator API views."""
import pytest
from unittest.mock import patch, MagicMock
from rest_framework import status
from apps.video_generator.models import VideoProject, Scene

PROJECTS_URL = "/api/v1/video/projects/"


def _project_url(pk):
    return f"{PROJECTS_URL}{pk}/"


def _generate_url(pk):
    return f"{PROJECTS_URL}{pk}/generate/"


def _status_url(pk):
    return f"{PROJECTS_URL}{pk}/status/"


def _scene_url(project_pk, scene_pk):
    return f"{PROJECTS_URL}{project_pk}/scenes/{scene_pk}/"


def _reorder_url(pk):
    return f"{PROJECTS_URL}{pk}/reorder/"


def _export_url(pk):
    return f"{PROJECTS_URL}{pk}/export/"


FAKE_SCENES = [
    {
        "scene_index": 0,
        "scene_prompt": "A person smiling, close-up, natural light.",
        "narration": "美好的一天开始了。",
        "voice_style": {"speed": "normal", "emotion": "neutral", "voice_id": "zh_female_1"},
        "duration_sec": 5,
        "transition": "cut",
    },
    {
        "scene_index": 1,
        "scene_prompt": "Wide shot of a park, morning sunlight.",
        "narration": "大自然的美丽令人心旷神怡。",
        "voice_style": {"speed": "normal", "emotion": "warm", "voice_id": "zh_female_1"},
        "duration_sec": 6,
        "transition": "fade",
    },
]


@pytest.mark.django_db
class TestVideoProjectListView:
    """GET /api/v1/video/projects/ — lists the authenticated user's projects."""

    def test_list_returns_empty_for_new_user(self, auth_client):
        client, _ = auth_client
        resp = client.get(PROJECTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []

    def test_list_returns_own_projects(self, auth_client, video_project):
        client, _ = auth_client
        resp = client.get(PROJECTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["id"] == video_project.pk

    def test_list_does_not_include_other_user_projects(self, auth_client, auth_client2, video_project):
        # video_project belongs to user (auth_client), user2 should not see it
        client2, _ = auth_client2
        resp = client2.get(PROJECTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []

    def test_list_ordered_newest_first(self, auth_client, confirmed_content, user):
        from apps.video_generator.models import VideoProject
        p1 = VideoProject.objects.create(user=user, content=confirmed_content, status="draft")
        p2 = VideoProject.objects.create(user=user, content=confirmed_content, status="draft")
        client, _ = auth_client
        resp = client.get(PROJECTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data]
        assert ids.index(p2.pk) < ids.index(p1.pk)  # p2 (newer) comes first

    def test_list_requires_auth(self, api_client):
        resp = api_client.get(PROJECTS_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_response_shape(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.get(PROJECTS_URL)
        assert resp.status_code == status.HTTP_200_OK
        p = resp.data[0]
        assert "id" in p
        assert "status" in p
        assert "scenes" in p
        assert "content_title" in p
        assert "created_at" in p


@pytest.mark.django_db
class TestVideoProjectCreateView:
    @patch("apps.video_generator.views.generate_scenes_from_content", return_value=FAKE_SCENES)
    def test_create_project_success(self, mock_gen, auth_client, confirmed_content):
        client, _ = auth_client
        resp = client.post(PROJECTS_URL, {"content_id": confirmed_content.pk}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert "project" in resp.data
        assert "continuity_issues" in resp.data
        assert VideoProject.objects.filter(content=confirmed_content).exists()
        assert Scene.objects.filter(
            video_project__content=confirmed_content
        ).count() == len(FAKE_SCENES)

    @patch("apps.video_generator.views.generate_scenes_from_content", return_value=FAKE_SCENES)
    def test_create_project_creates_scenes(self, mock_gen, auth_client, confirmed_content):
        client, _ = auth_client
        client.post(PROJECTS_URL, {"content_id": confirmed_content.pk}, format="json")
        project = VideoProject.objects.get(content=confirmed_content)
        scenes = list(Scene.objects.filter(video_project=project).order_by("scene_index"))
        assert scenes[0].scene_prompt == FAKE_SCENES[0]["scene_prompt"]
        assert scenes[1].narration == FAKE_SCENES[1]["narration"]

    def test_create_project_requires_confirmed_content(self, auth_client, draft_content):
        client, _ = auth_client
        resp = client.post(PROJECTS_URL, {"content_id": draft_content.pk}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "已确认状态" in resp.data["error"]

    def test_create_project_nonexistent_content(self, auth_client):
        client, _ = auth_client
        resp = client.post(PROJECTS_URL, {"content_id": 99999}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.video_generator.views.generate_scenes_from_content",
           side_effect=RuntimeError("LLM 未配置"))
    def test_create_project_llm_failure(self, mock_gen, auth_client, confirmed_content):
        client, _ = auth_client
        resp = client.post(PROJECTS_URL, {"content_id": confirmed_content.pk}, format="json")
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        project = VideoProject.objects.get(content=confirmed_content)
        assert project.status == "failed"

    def test_other_user_content_returns_error(self, auth_client2, confirmed_content):
        client2, _ = auth_client2
        resp = client2.post(PROJECTS_URL, {"content_id": confirmed_content.pk}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_cannot_create(self, api_client, confirmed_content):
        resp = api_client.post(PROJECTS_URL, {"content_id": confirmed_content.pk}, format="json")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestVideoProjectDetailView:
    def test_get_project_detail(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.get(_project_url(video_project.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["id"] == video_project.pk
        assert len(resp.data["scenes"]) == 1

    def test_get_project_other_user_returns_404(self, auth_client2, video_project):
        client2, _ = auth_client2
        resp = client2.get(_project_url(video_project.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_nonexistent_project_returns_404(self, auth_client):
        client, _ = auth_client
        resp = client.get(_project_url(99999))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestVideoProjectGenerateView:
    @patch("apps.video_generator.views.generate_video_task")
    def test_generate_submits_task(self, mock_task, auth_client, video_project):
        client, _ = auth_client
        resp = client.post(_generate_url(video_project.pk))
        assert resp.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once_with(video_project.pk)
        video_project.refresh_from_db()
        assert video_project.status == "generating"

    @patch("apps.video_generator.views.generate_video_task")
    def test_generate_already_generating_returns_error(self, mock_task, auth_client, video_project):
        video_project.status = "generating"
        video_project.save()

        client, _ = auth_client
        resp = client.post(_generate_url(video_project.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert "正在生成" in resp.data["error"]
        mock_task.delay.assert_not_called()

    def test_generate_other_users_project_returns_404(self, auth_client2, video_project):
        client2, _ = auth_client2
        resp = client2.post(_generate_url(video_project.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestVideoProjectStatusView:
    def test_get_status(self, auth_client, video_project):
        client, _ = auth_client
        resp = client.get(_status_url(video_project.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "draft"
        assert "jimeng_task_id" in resp.data
        assert "error_message" in resp.data

    def test_get_status_other_user_returns_404(self, auth_client2, video_project):
        client2, _ = auth_client2
        resp = client2.get(_status_url(video_project.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestSceneUpdateView:
    def test_update_scene_prompt(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.patch(
            _scene_url(video_project.pk, scene.pk),
            {"scene_prompt": "New prompt for the scene."},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        scene.refresh_from_db()
        assert scene.scene_prompt == "New prompt for the scene."

    def test_update_narration(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.patch(
            _scene_url(video_project.pk, scene.pk),
            {"narration": "新的配音文案"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        scene.refresh_from_db()
        assert scene.narration == "新的配音文案"

    def test_duration_clamped_to_min(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.patch(
            _scene_url(video_project.pk, scene.pk),
            {"duration_sec": 0},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        scene.refresh_from_db()
        assert scene.duration_sec == 2

    def test_duration_clamped_to_max(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.patch(
            _scene_url(video_project.pk, scene.pk),
            {"duration_sec": 100},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        scene.refresh_from_db()
        assert scene.duration_sec == 10

    def test_update_transition(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.patch(
            _scene_url(video_project.pk, scene.pk),
            {"transition": "fade"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        scene.refresh_from_db()
        assert scene.transition == "fade"

    def test_delete_scene_soft_deletes(self, auth_client, video_project, scene):
        client, _ = auth_client
        resp = client.delete(_scene_url(video_project.pk, scene.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        scene.refresh_from_db()
        assert scene.is_deleted is True
        assert Scene.objects.filter(pk=scene.pk).exists()  # still in DB

    def test_update_other_users_scene_returns_404(self, auth_client2, video_project, scene):
        client2, _ = auth_client2
        resp = client2.patch(
            _scene_url(video_project.pk, scene.pk),
            {"narration": "hack"},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_other_users_scene_returns_404(self, auth_client2, video_project, scene):
        client2, _ = auth_client2
        resp = client2.delete(_scene_url(video_project.pk, scene.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestSceneReorderView:
    def test_reorder_scenes(self, auth_client, video_project):
        s0 = Scene.objects.create(video_project=video_project, scene_index=0,
                                  scene_prompt="A", narration="a")
        s1 = Scene.objects.create(video_project=video_project, scene_index=1,
                                  scene_prompt="B", narration="b")

        client, _ = auth_client
        resp = client.post(
            _reorder_url(video_project.pk),
            {"scene_ids": [s1.pk, s0.pk]},  # reverse order
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        s0.refresh_from_db()
        s1.refresh_from_db()
        assert s1.scene_index == 0
        assert s0.scene_index == 1

    def test_reorder_other_users_project_returns_404(self, auth_client2, video_project):
        client2, _ = auth_client2
        resp = client2.post(_reorder_url(video_project.pk), {"scene_ids": []}, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestVideoExportView:
    def test_export_requires_completed_status(self, auth_client, video_project):
        client, _ = auth_client
        resp = client.post(_export_url(video_project.pk))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "未生成完成" in resp.data["error"]

    def test_export_no_clips_returns_error(self, auth_client, video_project, scene):
        video_project.status = "completed"
        video_project.save()
        # scene has no jimeng_clip_url

        client, _ = auth_client
        resp = client.post(_export_url(video_project.pk))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "没有可合成" in resp.data["error"]

    @patch("apps.video_generator.views._compose_video", return_value="/media/videos/1/final.mp4")
    def test_export_success(self, mock_compose, auth_client, video_project, scene):
        video_project.status = "completed"
        video_project.save()
        scene.jimeng_clip_url = "http://cdn.example.com/clip.mp4"
        scene.save()

        client, _ = auth_client
        resp = client.post(_export_url(video_project.pk))
        assert resp.status_code == status.HTTP_200_OK
        assert "download_url" in resp.data
        mock_compose.assert_called_once()

    def test_export_other_users_project_returns_error(self, auth_client2, video_project):
        video_project.status = "completed"
        video_project.save()
        client2, _ = auth_client2
        resp = client2.post(_export_url(video_project.pk))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
