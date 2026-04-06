from django.urls import path
from .views import (
    PlatformAccountListView,
    PlatformAccountBindView,
    PlatformAccountDeleteView,
    PublishTaskListCreateView,
    PublishTaskRetryView,
)

urlpatterns = [
    path("accounts/", PlatformAccountListView.as_view(), name="publisher-account-list"),
    path("accounts/<str:platform>/bind/", PlatformAccountBindView.as_view(), name="publisher-account-bind"),
    path("accounts/<int:pk>/", PlatformAccountDeleteView.as_view(), name="publisher-account-delete"),
    path("tasks/", PublishTaskListCreateView.as_view(), name="publisher-task-list"),
    path("tasks/<int:pk>/retry/", PublishTaskRetryView.as_view(), name="publisher-task-retry"),
]
