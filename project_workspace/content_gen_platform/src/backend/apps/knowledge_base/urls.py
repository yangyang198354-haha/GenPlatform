from django.urls import path
from .views import DocumentListCreateView, DocumentDetailView

urlpatterns = [
    path("documents/", DocumentListCreateView.as_view(), name="kb-document-list"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="kb-document-detail"),
]
