"""Unit tests for video_generator models."""
import pytest
from apps.video_generator.models import VideoProject, Scene


@pytest.mark.django_db
class TestVideoProjectModel:
    def test_default_status_is_draft(self, user, confirmed_content):
        project = VideoProject.objects.create(user=user, content=confirmed_content)
        assert project.status == "draft"

    def test_final_video_path_default_empty(self, user, confirmed_content):
        project = VideoProject.objects.create(user=user, content=confirmed_content)
        assert project.final_video_path == ""

    def test_error_message_default_empty(self, user, confirmed_content):
        project = VideoProject.objects.create(user=user, content=confirmed_content)
        assert project.error_message == ""

    def test_ordering_newest_first(self, user, confirmed_content):
        p1 = VideoProject.objects.create(user=user, content=confirmed_content)
        p2 = VideoProject.objects.create(user=user, content=confirmed_content)
        projects = list(VideoProject.objects.filter(user=user))
        assert projects[0].pk == p2.pk


@pytest.mark.django_db
class TestSceneModel:
    def test_default_values(self, video_project):
        scene = Scene.objects.create(
            video_project=video_project,
            scene_index=0,
            scene_prompt="A beautiful sunset over the ocean.",
            narration="美丽的日落。",
        )
        assert scene.duration_sec == 5
        assert scene.transition == "cut"
        assert scene.is_deleted is False
        assert scene.jimeng_clip_url == ""
        assert scene.voice_style == {}

    def test_ordering_by_scene_index(self, video_project):
        s2 = Scene.objects.create(video_project=video_project, scene_index=1,
                                  scene_prompt="B", narration="B")
        s1 = Scene.objects.create(video_project=video_project, scene_index=0,
                                  scene_prompt="A", narration="A")
        scenes = list(Scene.objects.filter(video_project=video_project))
        assert scenes[0].pk == s1.pk
        assert scenes[1].pk == s2.pk

    def test_is_deleted_defaults_false(self, video_project):
        scene = Scene.objects.create(video_project=video_project, scene_index=0,
                                     scene_prompt="p", narration="n")
        assert scene.is_deleted is False
