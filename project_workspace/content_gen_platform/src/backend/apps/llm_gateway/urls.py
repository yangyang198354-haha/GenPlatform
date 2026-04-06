from django.urls import path
from .views import GenerateContentView

urlpatterns = [
    path("generate/", GenerateContentView.as_view(), name="llm-generate"),
]
