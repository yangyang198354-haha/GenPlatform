from django.urls import path
from .views import (
    VideoProjectCreateView,
    VideoProjectDetailView,
    VideoProjectGenerateView,
    VideoProjectStatusView,
    SceneUpdateView,
    SceneReorderView,
    VideoExportView,
)

urlpatterns = [
    path("projects/", VideoProjectCreateView.as_view(), name="video-project-create"),
    path("projects/<int:pk>/", VideoProjectDetailView.as_view(), name="video-project-detail"),
    path("projects/<int:pk>/generate/", VideoProjectGenerateView.as_view(), name="video-project-generate"),
    path("projects/<int:pk>/status/", VideoProjectStatusView.as_view(), name="video-project-status"),
    path("projects/<int:pk>/scenes/<int:scene_id>/", SceneUpdateView.as_view(), name="video-scene-update"),
    path("projects/<int:pk>/reorder/", SceneReorderView.as_view(), name="video-scene-reorder"),
    path("projects/<int:pk>/export/", VideoExportView.as_view(), name="video-project-export"),
]
