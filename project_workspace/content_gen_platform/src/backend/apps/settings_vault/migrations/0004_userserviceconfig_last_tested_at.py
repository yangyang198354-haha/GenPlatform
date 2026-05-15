"""
新增 UserServiceConfig.last_tested_at 字段。

语义：最近一次连通性探活时间（预留字段）。
与 last_validated_at（TestAndSaveView 主动 key 验证）语义不同：
  - last_validated_at：用户主动点击"测试并保存"时写入
  - last_tested_at：（预留）供未来连通性探活使用，本期仅加字段不填充值

回滚：
    python manage.py migrate settings_vault 0003_userserviceconfig_last_validated_at

创建时间：2026-05-15
关联需求：PR-1（LLM 模型选择功能）
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("settings_vault", "0003_userserviceconfig_last_validated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="userserviceconfig",
            name="last_tested_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="最近一次连通性探活时间（预留字段，本期 migration 加字段但不填充值）",
            ),
        ),
    ]
