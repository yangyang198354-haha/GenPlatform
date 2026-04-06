from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Content
from .serializers import ContentSerializer


class ContentListCreateView(generics.ListCreateAPIView):
    serializer_class = ContentSerializer

    def get_queryset(self):
        qs = Content.objects.filter(user=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ContentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ContentSerializer

    def get_queryset(self):
        return Content.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        # Revert to draft if confirmed content is edited
        if instance.status == "confirmed" and "body" in self.request.data:
            serializer.save(status="draft", confirmed_at=None)
        else:
            serializer.save()


class ContentConfirmView(APIView):
    """POST /api/v1/contents/{pk}/confirm/ — mark content as confirmed."""

    def post(self, request, pk):
        try:
            content = Content.objects.get(pk=pk, user=request.user)
        except Content.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if content.status == "confirmed":
            return Response({"message": "文案已处于确认状态"})

        content.status = "confirmed"
        content.confirmed_at = timezone.now()
        content.save(update_fields=["status", "confirmed_at"])
        return Response(ContentSerializer(content).data)
