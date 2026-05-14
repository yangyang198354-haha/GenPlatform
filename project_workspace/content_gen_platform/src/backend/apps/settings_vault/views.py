"""
Settings vault: secure API credential storage and retrieval.

v1.1 新增：
  - ServiceStatusView：GET /users/me/services/<service_type>/status/（ADR-09，FR-7.1）
  - TestAndSaveView：POST /users/me/services/<service_type>/test-and-save/（ADR-10，FR-6.3）

安全约束（适用于所有新增 View）：
  - status 端点响应体不含任何 Key 派生信息（仅 is_configured + last_validated_at）。
  - TestAndSaveView 中 api_key 不出现在任何日志、响应体或异常消息中。
  - TestAndSaveView 使用 transaction.atomic() 确保验证通过才入库（OQ-8=A，ADR-10）。
  - 权限：IsAuthenticated（所有新增 View）。

关联需求：FR-6.1、FR-6.3、FR-7.1、US-08 AC-08-1/AC-08-3/AC-08-4
"""
import logging
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone

from core.encryption import encrypt, decrypt
from .models import UserServiceConfig
from .serializers import ServiceStatusSerializer, TestAndSaveSerializer
from .ark_validator import validate_doubao_key

logger = logging.getLogger(__name__)


class ServiceConfigListView(APIView):
    """List all configured services (keys masked)."""

    def get(self, request):
        configs = UserServiceConfig.objects.filter(user=request.user, is_active=True)
        result = []
        for cfg in configs:
            try:
                raw = decrypt(bytes(cfg.encrypted_config))
                # Non-sensitive fields are returned as-is; sensitive fields are masked.
                # Sensitive: api_key, access_key, secret_key (anything with "key" in name).
                # Non-sensitive (plaintext): model_name, doubao_model, temperature, max_tokens.
                non_sensitive = {"model_name", "doubao_model", "temperature", "max_tokens"}
                masked = {}
                for k, v in raw.items():
                    if k in non_sensitive:
                        masked[k] = v
                    else:
                        masked[k] = _mask_value(v)
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


def _required_keys(service_type: str) -> list:
    return {
        "llm_deepseek": ["api_key"],
        "llm_volcano": ["api_key", "model_name"],
        "jimeng": ["access_key", "secret_key"],
        "doubao_image": ["api_key"],
    }.get(service_type, [])


# ── v1.1 新增 View：ServiceStatusView（ADR-09，FR-7.1）─────────────────────

class ServiceStatusView(generics.GenericAPIView):
    """
    查询当前用户指定服务类型的配置状态。

    GET /api/v1/settings/users/me/services/<service_type>/status/

    安全约束：
      - 响应体不包含 api_key 值、Key 前缀或任何 Key 派生信息。
      - 仅返回 is_configured（bool）和 last_validated_at（datetime | null）。
      - 权限：IsAuthenticated（仅查询当前登录用户数据）。

    关联需求：FR-7.1、US-08 AC-08-1/AC-08-4、ADR-09
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ServiceStatusSerializer

    def get(self, request, service_type):
        """
        参数：
            service_type: URL path 参数，如 "doubao_image"

        响应 200：
            {
              "is_configured": true | false,
              "last_validated_at": "2026-05-14T10:00:00Z" | null
            }

        响应 400：service_type 不在白名单（SERVICE_CHOICES）内。

        安全自检：响应字段穷举如上，不含任何 Key 相关信息；未知 service_type
        立即拒绝，避免向客户端泄露系统支持的 service_type 集合语义。
        """
        valid_types = {c[0] for c in UserServiceConfig.SERVICE_CHOICES}
        if service_type not in valid_types:
            return Response(
                {"error": "INVALID_SERVICE_TYPE", "detail": f"未知的服务类型: {service_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = UserServiceConfig.objects.filter(
            user=request.user,
            service_type=service_type,
            is_active=True,
        ).first()

        if config is None:
            data = {"is_configured": False, "last_validated_at": None}
        else:
            data = {
                "is_configured": True,
                "last_validated_at": config.last_validated_at,
            }

        # 直接返回 dict 数据，不经过 Serializer 实例化（read_only Serializer 无验证逻辑）
        # 此处手动构造响应体等效于 ServiceStatusSerializer(instance=data).data，
        # 且字段完全匹配 ServiceStatusSerializer 定义（is_configured, last_validated_at）
        return Response(data, status=status.HTTP_200_OK)


# ── v1.1 新增 View：TestAndSaveView（ADR-10，FR-6.3）──────────────────────

class TestAndSaveView(generics.GenericAPIView):
    """
    原子测试 Ark API Key 并保存（测试即保存，OQ-8=A）。

    POST /api/v1/settings/users/me/services/<service_type>/test-and-save/

    流程：
      1. Serializer 校验 api_key 非空（min_length=1）
      2. 校验 service_type 为 "doubao_image"（当前唯一支持原子测试保存的类型）
      3. 调用 validate_doubao_key() 验权（ADR-08）
      4. 验证通过 → with transaction.atomic() 写入加密 UserServiceConfig
      5. 验证失败 → 直接返回 400，不写入数据库

    安全约束：
      - api_key 不出现在任何日志、响应体或异常消息中（write_only Serializer 保证）。
      - 响应体仅含 {"saved": true, "last_validated_at": "..."} 或错误码。
      - 权限：IsAuthenticated。

    关联需求：FR-6.1、FR-6.3、US-08 AC-08-3/AC-08-4、OQ-8=A、ADR-10
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TestAndSaveSerializer

    # 错误码到中文详情的映射（不 echo api_key）
    _ERROR_DETAIL_MAP = {
        "ARK_KEY_INVALID":    "Key 无效或已吊销，请检查 Ark 控制台",
        "ARK_QUOTA_EXCEEDED": "账号欠费或权限受限，请检查账户余额",
        "ARK_UNREACHABLE":    "Ark 服务暂时不可达，请稍后重试",
    }

    def post(self, request, service_type):
        """
        请求体：{"api_key": "<用户输入的 Ark API Key>"}

        成功响应 200：
            {"saved": true, "last_validated_at": "2026-05-14T10:00:00Z"}

        失败响应 400（Ark 验证失败，Key 未写入数据库）：
            {"error": "ARK_KEY_INVALID", "detail": "Key 无效或已吊销，请检查 Ark 控制台"}
          | {"error": "ARK_QUOTA_EXCEEDED", "detail": "账号欠费或权限受限，请检查账户余额"}
          | {"error": "ARK_UNREACHABLE", "detail": "Ark 服务暂时不可达，请稍后重试"}
          | {"error": "UNSUPPORTED_SERVICE_TYPE", "detail": "..."}
        """
        # 当前仅 doubao_image 支持原子测试保存
        if service_type != "doubao_image":
            return Response(
                {
                    "error": "UNSUPPORTED_SERVICE_TYPE",
                    "detail": f"service_type '{service_type}' 暂不支持测试连接，请使用旧版配置接口",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # api_key 仅在此局部变量中存在，函数结束时由 GC 回收，不写入任何日志
        api_key: str = serializer.validated_data["api_key"]

        # 调用 Ark /api/v3/models 验权（ADR-08，OQ-6=B）
        is_valid, error_code = validate_doubao_key(api_key)

        if not is_valid:
            detail = self._ERROR_DETAIL_MAP.get(error_code, "未知错误")
            return Response(
                {"error": error_code, "detail": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 验证通过：原子写入加密配置（transaction.atomic，ADR-10，OQ-8=A）
        now = timezone.now()
        with transaction.atomic():
            UserServiceConfig.objects.update_or_create(
                user=request.user,
                service_type=service_type,
                defaults={
                    "encrypted_config": encrypt({"api_key": api_key}),
                    "is_active": True,
                    "last_validated_at": now,
                },
            )

        # api_key 局部变量在此之后不再使用，不做任何日志记录
        return Response(
            {"saved": True, "last_validated_at": now.isoformat()},
            status=status.HTTP_200_OK,
        )


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
