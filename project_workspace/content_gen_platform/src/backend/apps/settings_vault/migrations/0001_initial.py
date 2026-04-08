import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserServiceConfig",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "service_type",
                    models.CharField(
                        choices=[
                            ("llm_deepseek", "DeepSeek LLM"),
                            ("llm_volcano", "火山引擎（豆包）"),
                            ("jimeng", "即梦视频生成"),
                        ],
                        max_length=30,
                    ),
                ),
                ("encrypted_config", models.BinaryField()),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_configs",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "settings_service_config",
                "unique_together": {("user", "service_type")},
            },
        ),
    ]
