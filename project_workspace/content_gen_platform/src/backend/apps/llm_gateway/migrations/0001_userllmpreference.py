"""
新增 UserLLMPreference 表。

记录用户最近一次成功生成时使用的 provider+model 组合，
供下次进入 WorkspaceView 时自动预选（由后端 generate 成功后原子写入）。

回滚：
    python manage.py migrate llm_gateway zero

创建时间：2026-05-15
关联需求：PR-1（LLM 模型选择功能）
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserLLMPreference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "service_type",
                    models.CharField(
                        max_length=32,
                        help_text="e.g. 'llm_deepseek'，与 UserServiceConfig.service_type 同域",
                    ),
                ),
                (
                    "model",
                    models.CharField(
                        max_length=64,
                        help_text="e.g. 'deepseek-chat'",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="llm_preference",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "llm_gateway_user_preference",
            },
        ),
    ]
