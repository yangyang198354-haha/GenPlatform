"""
新增 UserServiceConfig.last_validated_at 字段。

该字段由 TestAndSaveView 在 API Key 验证通过并保存时写入，
用于前端展示"上次验证时间"（FR-6.3，ADR-10）。

回滚：
    回滚此迁移会删除 last_validated_at 列。
    所有已存储的"验证时间"数据将丢失，但加密配置本身不受影响。

创建时间：2026-05-14
关联需求：FR-6.3、US-08 AC-08-4、ADR-10
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("settings_vault", "0002_add_doubao_image_service"),
    ]

    operations = [
        migrations.AddField(
            model_name="userserviceconfig",
            name="last_validated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="最近一次成功验证 Key 有效性的时间（由 TestAndSaveView 写入，ADR-10）",
            ),
        ),
    ]
