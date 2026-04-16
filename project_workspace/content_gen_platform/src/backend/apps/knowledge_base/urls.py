from django.urls import path
from .views import DocumentListCreateView, DocumentBatchUploadView, DocumentDetailView

urlpatterns = [
    path("documents/", DocumentListCreateView.as_view(), name="kb-document-list"),
    # batch-upload MUST be registered before <int:pk>/ to avoid URL ambiguity
    path("documents/batch-upload/", DocumentBatchUploadView.as_view(), name="kb-document-batch-upload"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="kb-document-detail"),
]
