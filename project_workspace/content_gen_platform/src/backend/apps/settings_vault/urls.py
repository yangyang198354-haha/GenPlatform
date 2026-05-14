"""
settings_vault URL 配置。

v1.1 新增路由（ADR-09/ADR-10）：
  - GET  users/me/services/<service_type>/status/       → ServiceStatusView
  - POST users/me/services/<service_type>/test-and-save/ → TestAndSaveView

完整 URL 前缀由 config/urls.py 的 settings/ 决定，最终路径为：
  GET  /api/v1/settings/users/me/services/<service_type>/status/
  POST /api/v1/settings/users/me/services/<service_type>/test-and-save/

关联需求：FR-6.3、FR-7.1、ADR-09、ADR-10
"""
from django.urls import path
from .views import (
    ServiceConfigListView,
    ServiceConfigDetailView,
    ServiceConfigTestView,
    ServiceStatusView,
    TestAndSaveView,
)

urlpatterns = [
    # ── 原有路由（v1.0，不变）────────────────────────────────────────────────
    path("services/", ServiceConfigListView.as_view(), name="settings-list"),
    path("services/<str:service_type>/", ServiceConfigDetailView.as_view(), name="settings-detail"),
    path("services/<str:service_type>/test/", ServiceConfigTestView.as_view(), name="settings-test"),

    # ── v1.1 新增路由（ADR-09/ADR-10）───────────────────────────────────────
    # 注意：路由顺序很重要，具体路径（test-and-save/）必须在通配 <service_type>/ 之前注册。
    # 此处单独使用 users/me/ 前缀，与 settings/services/ 路由不冲突。
    path(
        "users/me/services/<str:service_type>/status/",
        ServiceStatusView.as_view(),
        name="service-status",
    ),
    path(
        "users/me/services/<str:service_type>/test-and-save/",
        TestAndSaveView.as_view(),
        name="service-test-and-save",
    ),
]
