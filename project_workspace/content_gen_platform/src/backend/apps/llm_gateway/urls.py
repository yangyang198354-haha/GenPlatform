from django.urls import path
from .views import GenerateContentView, ProvidersView

urlpatterns = [
    path("generate/", GenerateContentView.as_view(), name="llm-generate"),
    path("providers/", ProvidersView.as_view(), name="llm-providers"),
]
