from django.conf import settings
from django.db import models


class UserLLMPreference(models.Model):
    """
    用户 LLM 使用偏好。

    在 generate 成功后由后端原子写入（update_or_create），
    供下次进入 WorkspaceView 时自动预选 provider+model。

    设计决策：
    - 不在 UserServiceConfig 中加字段（职责隔离：配置 vs 偏好）
    - 不加 FK 指向 UserServiceConfig（松耦合，偏好失效由 selectors.py 运行时校验）
    - OneToOneField 保证一个用户只有一条偏好记录
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="llm_preference",
    )
    service_type = models.CharField(
        max_length=32,
        help_text="e.g. 'llm_deepseek'，与 UserServiceConfig.service_type 同域",
    )
    model = models.CharField(
        max_length=64,
        help_text="e.g. 'deepseek-chat'",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "llm_gateway_user_preference"

    def __str__(self):
        return f"{self.user} — {self.service_type}/{self.model}"
