import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformAccount",
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
                    "platform",
                    models.CharField(
                        choices=[
                            ("weibo", "微博"),
                            ("xiaohongshu", "小红书"),
                            ("wechat_mp", "微信公众号"),
                            ("wechat_video", "微信视频号"),
                            ("toutiao", "今日头条"),
                        ],
                        max_length=20,
                    ),
                ),
                ("display_name", models.CharField(max_length=255)),
                (
                    "auth_type",
                    models.CharField(
                        choices=[("oauth", "OAuth"), ("api_key", "API Key")],
                        max_length=10,
                    ),
                ),
                ("encrypted_credentials", models.BinaryField()),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="platform_accounts",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "publisher_platform_account",
            },
        ),
        migrations.CreateModel(
            name="PublishTask",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "待发布"),
                            ("publishing", "发布中"),
                            ("success", "成功"),
                            ("failed", "失败"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "platform_post_id",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("platform_post_url", models.URLField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("retry_count", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "content",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="publish_tasks",
                        to="content.content",
                    ),
                ),
                (
                    "platform_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="publisher.platformaccount",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="publish_tasks",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "publisher_publish_task",
                "ordering": ["-created_at"],
            },
        ),
    ]
