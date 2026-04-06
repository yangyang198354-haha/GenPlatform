"""URL configuration for content_gen_platform."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

api_v1_patterns = [
    path("auth/", include("apps.accounts.urls")),
    path("knowledge/", include("apps.knowledge_base.urls")),
    path("llm/", include("apps.llm_gateway.urls")),
    path("contents/", include("apps.content.urls")),
    path("publisher/", include("apps.publisher.urls")),
    path("video/", include("apps.video_generator.urls")),
    path("settings/", include("apps.settings_vault.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
