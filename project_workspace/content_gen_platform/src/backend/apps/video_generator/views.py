"""Video generator API views."""
import subprocess
import tempfile
import os
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import Content
from .models import VideoProject, Scene
from .serializers import VideoProjectSerializer, SceneSerializer
from .scene_generator import generate_scenes_from_content, validate_scene_continuity
from .tasks import generate_video_task

logger = logging.getLogger(__name__)


class VideoProjectCreateView(APIView):
    """
    GET  /api/v1/video/projects/  — list the authenticated user's video projects.
    POST /api/v1/video/projects/  — create a video project from confirmed content.
    """

    def get(self, request):
        projects = (
            VideoProject.objects.filter(user=request.user)
            .prefetch_related("scenes")
            .order_by("-created_at")
        )
        serializer = VideoProjectSerializer(projects, many=True)
        return Response(serializer.data)

    def post(self, request):
        content_id = request.data.get("content_id")
        try:
            content = Content.objects.get(pk=content_id, user=request.user, status="confirmed")
        except Content.DoesNotExist:
            return Response(
                {"error": "文案不存在或未处于已确认状态"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project = VideoProject.objects.create(user=request.user, content=content)

        try:
            scenes_data = generate_scenes_from_content(content, request.user.pk)
        except RuntimeError as e:
            project.status = "failed"
            project.error_message = str(e)
            project.save(update_fields=["status", "error_message"])
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        scene_objects = [
            Scene(video_project=project, **sd) for sd in scenes_data
        ]
        Scene.objects.bulk_create(scene_objects)

        # Validate continuity
        issues = validate_scene_continuity(scenes_data)

        return Response(
            {
                "project": VideoProjectSerializer(project).data,
                "continuity_issues": issues,
            },
            status=status.HTTP_201_CREATED,
        )


class VideoProjectDetailView(APIView):
    def get(self, request, pk):
        try:
            project = VideoProject.objects.prefetch_related("scenes").get(
                pk=pk, user=request.user
            )
        except VideoProject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(VideoProjectSerializer(project).data)


class VideoProjectGenerateView(APIView):
    """POST /api/v1/video/projects/{pk}/generate/ — submit to Jimeng."""

    def post(self, request, pk):
        try:
            project = VideoProject.objects.get(pk=pk, user=request.user)
        except VideoProject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if project.status == "generating":
            return Response({"error": "视频正在生成中，请勿重复提交"})

        generate_video_task.delay(project.pk)
        project.status = "generating"
        project.save(update_fields=["status"])
        return Response({"message": "视频生成任务已提交", "project_id": project.pk})


class VideoProjectStatusView(APIView):
    def get(self, request, pk):
        try:
            project = VideoProject.objects.get(pk=pk, user=request.user)
        except VideoProject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({
            "status": project.status,
            "jimeng_task_id": project.jimeng_task_id,
            "error_message": project.error_message,
        })


class SceneUpdateView(APIView):
    def patch(self, request, pk, scene_id):
        try:
            scene = Scene.objects.get(
                pk=scene_id, video_project__pk=pk, video_project__user=request.user
            )
        except Scene.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        allowed = {"scene_prompt", "narration", "voice_style", "duration_sec", "transition"}
        for field in allowed:
            if field in request.data:
                if field == "duration_sec":
                    setattr(scene, field, max(2, min(10, int(request.data[field]))))
                else:
                    setattr(scene, field, request.data[field])
        scene.save()
        return Response(SceneSerializer(scene).data)

    def delete(self, request, pk, scene_id):
        try:
            scene = Scene.objects.get(
                pk=scene_id, video_project__pk=pk, video_project__user=request.user
            )
        except Scene.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        scene.is_deleted = True
        scene.save(update_fields=["is_deleted"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SceneReorderView(APIView):
    """POST /api/v1/video/projects/{pk}/reorder/ — reorder scenes."""

    def post(self, request, pk):
        try:
            project = VideoProject.objects.get(pk=pk, user=request.user)
        except VideoProject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        scene_ids = request.data.get("scene_ids", [])
        scenes = {s.pk: s for s in project.scenes.filter(is_deleted=False)}

        for new_index, scene_id in enumerate(scene_ids):
            if scene_id in scenes:
                scenes[scene_id].scene_index = new_index
                scenes[scene_id].save(update_fields=["scene_index"])

        return Response({"message": "分镜顺序已更新"})


class VideoExportView(APIView):
    """POST /api/v1/video/projects/{pk}/export/ — compose and export final video."""

    def post(self, request, pk):
        try:
            project = VideoProject.objects.prefetch_related("scenes").get(
                pk=pk, user=request.user, status="completed"
            )
        except VideoProject.DoesNotExist:
            return Response(
                {"error": "视频项目不存在或尚未生成完成"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scenes = project.scenes.filter(is_deleted=False).order_by("scene_index")
        clip_urls = [s.jimeng_clip_url for s in scenes if s.jimeng_clip_url]

        if not clip_urls:
            return Response({"error": "没有可合成的视频片段"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            output_path = _compose_video(clip_urls, project.pk)
            project.final_video_path = output_path
            project.save(update_fields=["final_video_path"])
            return Response({"download_url": f"/media/videos/{project.pk}/final.mp4"})
        except Exception as e:
            logger.exception("Video export failed for project %d", pk)
            return Response({"error": f"视频合成失败：{e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _compose_video(clip_urls: list[str], project_id: int) -> str:
    """Download clips and compose final video using FFmpeg."""
    import urllib.request

    output_dir = f"/tmp/video_export_{project_id}"
    os.makedirs(output_dir, exist_ok=True)

    clip_paths = []
    for i, url in enumerate(clip_urls):
        local_path = os.path.join(output_dir, f"clip_{i:03d}.mp4")
        urllib.request.urlretrieve(url, local_path)
        clip_paths.append(local_path)

    # Create FFmpeg concat file
    concat_file = os.path.join(output_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    output_path = f"/media/videos/{project_id}/final.mp4"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-c", "copy", output_path],
        check=True,
        capture_output=True,
    )
    return output_path
