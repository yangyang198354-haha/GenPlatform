"""
settings_vault 序列化器（v1.1 新增）。

新增：
  - ServiceStatusSerializer：GET status/ 端点响应序列化（ADR-09，FR-7.1）
  - TestAndSaveSerializer：POST test-and-save/ 端点请求校验（ADR-10，FR-6.3）

安全约束：
  - ServiceStatusSerializer 仅暴露 is_configured 和 last_validated_at，不含任何 Key 相关信息。
  - TestAndSaveSerializer.api_key 字段标记 write_only=True，
    禁止出现在任何序列化输出或响应体中。
  - validate 方法中不在错误信息里 echo api_key 内容。

关联需求：FR-6.3、FR-7.1、US-08 AC-08-1/AC-08-3/AC-08-4、ADR-09、ADR-10
"""
from rest_framework import serializers


class ServiceStatusSerializer(serializers.Serializer):
    """
    GET /users/me/services/<service_type>/status/ 响应序列化。

    安全约束：响应体仅含 is_configured 和 last_validated_at，
    不含 api_key、Key 前缀、Key 哈希或任何 Key 派生信息。

    关联需求：FR-7.1、US-08 AC-08-1/AC-08-4、ADR-09
    """

    is_configured = serializers.BooleanField(read_only=True)
    last_validated_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        # ISO 8601 UTC 格式，与前端约定一致
        format="%Y-%m-%dT%H:%M:%SZ",
    )


class TestAndSaveSerializer(serializers.Serializer):
    """
    POST /users/me/services/<service_type>/test-and-save/ 请求体校验。

    安全约束：
      - api_key 字段标记 write_only=True，禁止出现在任何序列化输出中。
      - min_length=1 确保空值被拒绝于 Serializer 层（不进入 validate_doubao_key）。
      - 字段错误消息不 echo api_key 内容（使用通用提示语）。

    关联需求：FR-6.3、US-08 AC-08-3、ADR-10
    """

    api_key = serializers.CharField(
        min_length=1,
        max_length=512,
        write_only=True,
        trim_whitespace=True,
        error_messages={
            "blank": "API Key 不能为空",
            "min_length": "API Key 长度不足",
            "max_length": "API Key 长度超出限制",
            "required": "请提供 API Key",
        },
        help_text="Ark API Key（仅用于验证和保存，不出现在响应体中）",
    )
