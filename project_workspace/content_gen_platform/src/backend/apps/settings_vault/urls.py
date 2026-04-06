from django.urls import path
from .views import ServiceConfigListView, ServiceConfigDetailView, ServiceConfigTestView

urlpatterns = [
    path("services/", ServiceConfigListView.as_view(), name="settings-list"),
    path("services/<str:service_type>/", ServiceConfigDetailView.as_view(), name="settings-detail"),
    path("services/<str:service_type>/test/", ServiceConfigTestView.as_view(), name="settings-test"),
]
