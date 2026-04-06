from django.urls import path
from .views import ContentListCreateView, ContentDetailView, ContentConfirmView

urlpatterns = [
    path("", ContentListCreateView.as_view(), name="content-list"),
    path("<int:pk>/", ContentDetailView.as_view(), name="content-detail"),
    path("<int:pk>/confirm/", ContentConfirmView.as_view(), name="content-confirm"),
]
