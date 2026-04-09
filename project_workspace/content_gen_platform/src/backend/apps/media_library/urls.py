from django.urls import path
from .views import (
    MediaItemListView,
    MediaItemUploadView,
    MediaItemDeleteView,
    MediaItemDownloadView,
)

urlpatterns = [
    path("", MediaItemListView.as_view(), name="media-list"),
    path("upload/", MediaItemUploadView.as_view(), name="media-upload"),
    path("<int:pk>/", MediaItemDeleteView.as_view(), name="media-delete"),
    path("<int:pk>/download/", MediaItemDownloadView.as_view(), name="media-download"),
]
