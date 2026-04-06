"""Settings vault: secure API credential storage and retrieval."""
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from core.encryption import encrypt, decrypt
from .models import UserServiceConfig

logger = logging.getLogger(__name__)


class ServiceConfigListView(APIView):
    """List all configured services (keys masked)."""

    def get(self, request):
        configs = UserServiceConfig.objects.filter(user=request.user, is_active=True)
        result = []
        for cfg in configs:
            try:
                raw = decrypt(bytes(cfg.encrypted_config))
                # Mask sensitive values
                masked = {k: _mask_value(v) for k, v in raw.items() if k != "model_name"}
                if "model_name" in raw:
                    masked["model_name"] = raw["model_name"]
            except Exception:
                masked = {}
            result.append({
                "service_type": cfg.service_type,
                "is_configured": True,
                "config_preview": masked,
                "updated_at": cfg.updated_at,
            })

        # Add unconfigured services
        configured_types = {c.service_type for c in configs}
        for choice_value, choice_label in UserServiceConfig.SERVICE_CHOICES:
            if choice_value not in configured_types:
                result.append({"service_type": choice_value, "is_configured": False})

        return Response(result)


class ServiceConfigDetailView(APIView):
    """Save or update a service config (encrypts before storing)."""

    def put(self, request, service_type):
        valid_types = {c[0] for c in UserServiceConfig.SERVICE_CHOICES}
        if service_type not in valid_types:
            return Response({"error": "无效的服务类型"}, status=status.HTTP_400_BAD_REQUEST)

        config_data = request.data
        if not config_data:
            return Response({"error": "配置不能为空"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate required keys per service type
        required_keys = _required_keys(service_type)
        missing = [k for k in required_keys if k not in config_data or not config_data[k]]
        if missing:
            return Response(
                {"error": f"缺少必填字段：{', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        encrypted = encrypt(dict(config_data))
        UserServiceConfig.objects.update_or_create(
            user=request.user,
            service_type=service_type,
            defaults={"encrypted_config": encrypted, "is_active": True},
        )
        return Response({"message": "配置已保存"})

    def delete(self, request, service_type):
        UserServiceConfig.objects.filter(user=request.user, service_type=service_type).update(
            is_active=False
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServiceConfigTestView(APIView):
    """Test connectivity for a configured service."""

    def post(self, request, service_type):
        try:
            cfg = UserServiceConfig.objects.get(
                user=request.user, service_type=service_type, is_active=True
            )
            config = decrypt(bytes(cfg.encrypted_config))
        except UserServiceConfig.DoesNotExist:
            return Response({"error": "未找到该服务配置"}, status=status.HTTP_404_NOT_FOUND)

        result = _test_connection(service_type, config)
        return Response(result)


def _required_keys(service_type: str) -> list[str]:
    return {
        "llm_deepseek": ["api_key"],
        "llm_volcano": ["api_key", "model_name"],
        "jimeng": ["access_key", "secret_key"],
    }.get(service_type, [])


def _mask_value(value: str) -> str:
    if not isinstance(value, str) or len(value) <= 4:
        return "****"
    return value[:4] + "****"


def _test_connection(service_type: str, config: dict) -> dict:
    """Test API connectivity. Returns success status and message."""
    import httpx
    try:
        if service_type == "llm_deepseek":
            resp = httpx.get(
                "https://api.deepseek.com/v1/models",
                headers={"Authorization": f"Bearer {config['api_key']}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return {"success": True, "message": "DeepSeek 连接成功"}
            return {"success": False, "message": f"连接失败：HTTP {resp.status_code}"}

        if service_type == "llm_volcano":
            # Volcano uses OpenAI-compatible endpoint
            resp = httpx.get(
                "https://ark.cn-beijing.volces.com/api/v3/models",
                headers={"Authorization": f"Bearer {config['api_key']}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return {"success": True, "message": "火山引擎连接成功"}
            return {"success": False, "message": f"连接失败：HTTP {resp.status_code}"}

        if service_type == "jimeng":
            # Jimeng API health check
            resp = httpx.get(
                "https://visual.volcengineapi.com/",
                timeout=10,
            )
            return {"success": True, "message": "即梦 API 可达，请检查 Access Key 有效性"}

    except Exception as e:
        return {"success": False, "message": f"连接错误：{e}"}

    return {"success": False, "message": "未知服务类型"}
