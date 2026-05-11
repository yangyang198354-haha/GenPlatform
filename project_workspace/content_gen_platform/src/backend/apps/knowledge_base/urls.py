from django.urls import path
from .views import (
    DocumentListCreateView,
    DocumentBatchUploadView,
    DocumentDetailView,
    DocumentRetryView,
)

urlpatterns = [
    path("documents/", DocumentListCreateView.as_view(), name="kb-document-list"),
    # batch-upload MUST be registered before <int:pk>/ to avoid URL ambiguity
    path("documents/batch-upload/", DocumentBatchUploadView.as_view(), name="kb-document-batch-upload"),
    # retry MUST be registered before <int:pk>/ for the same reason
    path("documents/<int:pk>/retry/", DocumentRetryView.as_view(), name="kb-document-retry"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="kb-document-detail"),
]
