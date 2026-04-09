"""URL configuration for content_gen_platform."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

api_v1_patterns = [
    path("auth/", include("apps.accounts.urls")),
    path("llm/", include("apps.llm_gateway.urls")),
    path("contents/", include("apps.content.urls")),
    path("publisher/", include("apps.publisher.urls")),
    path("video/", include("apps.video_generator.urls")),
    path("settings/", include("apps.settings_vault.urls")),
    path("media/", include("apps.media_library.urls")),
    path("image/", include("apps.image_generator.urls")),
]

# knowledge-base requires pgvector (PostgreSQL); omit when the app is excluded
if "apps.knowledge_base" in settings.INSTALLED_APPS:
    api_v1_patterns.insert(1, path("knowledge/", include("apps.knowledge_base.urls")))

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
