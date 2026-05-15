from django.db import models
from apps.accounts.models import User


class UserServiceConfig(models.Model):
    """
    用户级服务配置（AES-256-GCM 加密存储）。

    v1.1 补丁新增：
      - last_validated_at 字段（由 TestAndSaveView 写入，FR-6.3，ADR-10）
      - _required_keys() 方法：doubao_image 分支（FR-6.3，ADR-08）
      - _test_connection() 方法：doubao_image 分支调用 ark_validator（ADR-08）

    安全约束：_test_connection() 禁止将 api_key 记录到任何日志中。
    """

    SERVICE_CHOICES = [
        ("llm_deepseek", "DeepSeek LLM"),
        ("llm_volcano", "火山引擎（豆包）"),
        ("jimeng", "即梦视频/图片生成"),
        # 豆包 Seedream 图片生成（Ark Bearer Token，ADR-06）
        ("doubao_image", "豆包图片生成"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="service_configs")
    service_type = models.CharField(max_length=30, choices=SERVICE_CHOICES)
    encrypted_config = models.BinaryField()  # AES-256-GCM encrypted JSON
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # 最近一次成功验证 Key 有效性的时间（由 TestAndSaveView 写入，v1.1 新增）
    last_validated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="最近一次成功验证 Key 有效性的时间（由 TestAndSaveView 写入，ADR-10）",
    )
    # 最近一次连通性探活时间（预留，本期仅加字段不填充值；与 last_validated_at 语义不同）
    last_tested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="最近一次连通性探活时间（预留字段，本期 migration 加字段但不填充值）",
    )

    class Meta:
        db_table = "settings_service_config"
        unique_together = [("user", "service_type")]

    def __str__(self):
        return f"{self.user.email} — {self.service_type}"

    def _required_keys(self) -> list:
        """
        返回当前 service_type 的必填配置 Key 列表。

        关联需求：FR-6.3（doubao_image 分支）、ADR-08
        """
        return {
            "doubao_image": ["api_key"],
            "llm_deepseek": ["api_key"],
            "llm_volcano": ["api_key", "model_name"],
            "jimeng": ["access_key", "secret_key"],
        }.get(self.service_type, ["api_key"])

    def _test_connection(self) -> tuple:
        """
        测试当前 service_type 的连通性。

        doubao_image 分支：调用 Ark /api/v3/models（ADR-08，OQ-6=B）。
        安全约束：不在此函数中记录任何 api_key 内容。

        返回：Tuple[bool, str]，(True, "") 或 (False, "错误码")
        """
        if self.service_type == "doubao_image":
            from apps.settings_vault.ark_validator import validate_doubao_key
            from core.encryption import decrypt
            config = decrypt(bytes(self.encrypted_config))
            api_key = config.get("api_key", "")
            return validate_doubao_key(api_key)
        # 其他 service_type 暂不支持此方法（由 ServiceConfigTestView 旧逻辑处理）
        return False, "UNSUPPORTED_SERVICE_TYPE"
