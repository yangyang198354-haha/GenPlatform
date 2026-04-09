from django.urls import path
from .views import (
    ImageGenerationSubmitView,
    ImageGenerationStatusView,
    ImageGenerationListView,
)

urlpatterns = [
    path("generate/", ImageGenerationSubmitView.as_view(), name="image-generate"),
    path("generate/<int:pk>/status/", ImageGenerationStatusView.as_view(), name="image-status"),
    path("history/", ImageGenerationListView.as_view(), name="image-history"),
]
