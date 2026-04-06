"""Publisher API: platform account management and publish task creation."""
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.encryption import encrypt
from apps.content.models import Content
from .models import PlatformAccount, PublishTask
from .serializers import PlatformAccountSerializer, PublishTaskSerializer
from .tasks import execute_publish_task


class PlatformAccountListView(generics.ListAPIView):
    serializer_class = PlatformAccountSerializer

    def get_queryset(self):
        return PlatformAccount.objects.filter(user=self.request.user, is_active=True)


class PlatformAccountBindView(APIView):
    """POST /api/v1/publisher/accounts/{platform}/bind/ — bind a platform account."""

    def post(self, request, platform):
        valid_platforms = {c[0] for c in PlatformAccount.PLATFORM_CHOICES}
        if platform not in valid_platforms:
            return Response({"error": "不支持的平台"}, status=status.HTTP_400_BAD_REQUEST)

        credentials = request.data.get("credentials")
        display_name = request.data.get("display_name", "")
        auth_type = request.data.get("auth_type", "api_key")

        if not credentials or not display_name:
            return Response(
                {"error": "credentials 和 display_name 不能为空"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        encrypted = encrypt(credentials if isinstance(credentials, dict) else {"token": credentials})
        account, _ = PlatformAccount.objects.update_or_create(
            user=request.user,
            platform=platform,
            defaults={
                "display_name": display_name,
                "auth_type": auth_type,
                "encrypted_credentials": encrypted,
                "is_active": True,
            },
        )
        return Response(PlatformAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class PlatformAccountDeleteView(APIView):
    def delete(self, request, pk):
        try:
            account = PlatformAccount.objects.get(pk=pk, user=request.user)
        except PlatformAccount.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        account.is_active = False
        account.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublishTaskListCreateView(generics.ListCreateAPIView):
    serializer_class = PublishTaskSerializer

    def get_queryset(self):
        return PublishTask.objects.filter(user=self.request.user).select_related(
            "content", "platform_account"
        )

    def create(self, request, *args, **kwargs):
        content_id = request.data.get("content_id")
        account_ids = request.data.get("platform_account_ids", [])
        scheduled_at = request.data.get("scheduled_at")  # ISO8601 or null

        if not content_id or not account_ids:
            return Response(
                {"error": "content_id 和 platform_account_ids 不能为空"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            content = Content.objects.get(pk=content_id, user=request.user, status="confirmed")
        except Content.DoesNotExist:
            return Response(
                {"error": "文案不存在或未处于已确认状态"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        accounts = PlatformAccount.objects.filter(
            pk__in=account_ids, user=request.user, is_active=True
        )
        if not accounts.exists():
            return Response({"error": "未找到有效的平台账号"}, status=status.HTTP_400_BAD_REQUEST)

        tasks_created = []
        for account in accounts:
            task = PublishTask.objects.create(
                user=request.user,
                content=content,
                platform_account=account,
                scheduled_at=scheduled_at,
            )
            tasks_created.append(task)

            if not scheduled_at:
                # Immediate publish
                execute_publish_task.delay(task.pk)
            else:
                # Scheduled publish: Celery Beat will trigger execute_publish_task at scheduled_at
                execute_publish_task.apply_async(args=[task.pk], eta=task.scheduled_at)

        return Response(
            PublishTaskSerializer(tasks_created, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class PublishTaskRetryView(APIView):
    def post(self, request, pk):
        try:
            task = PublishTask.objects.get(pk=pk, user=request.user, status="failed")
        except PublishTask.DoesNotExist:
            return Response({"error": "任务不存在或非失败状态"}, status=status.HTTP_404_NOT_FOUND)
        task.status = "pending"
        task.save(update_fields=["status"])
        execute_publish_task.delay(task.pk)
        return Response({"message": "重试任务已提交"})
