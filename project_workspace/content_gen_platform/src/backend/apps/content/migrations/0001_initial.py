import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Content",
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
                ("title", models.CharField(blank=True, max_length=255)),
                ("body", models.TextField()),
                (
                    "platform_type",
                    models.CharField(
                        choices=[
                            ("weibo", "微博"),
                            ("xiaohongshu", "小红书"),
                            ("wechat_mp", "微信公众号"),
                            ("wechat_video", "微信视频号"),
                            ("toutiao", "今日头条"),
                            ("general", "通用"),
                        ],
                        default="general",
                        max_length=20,
                    ),
                ),
                (
                    "style",
                    models.CharField(
                        choices=[
                            ("professional", "专业"),
                            ("casual", "口语"),
                            ("humorous", "幽默"),
                            ("promotion", "种草"),
                        ],
                        default="professional",
                        max_length=20,
                    ),
                ),
                ("word_limit", models.IntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "草稿"),
                            ("confirmed", "已确认"),
                            ("published", "已发布"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("generation_prompt", models.TextField(blank=True)),
                ("used_document_ids", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contents",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "content_content",
                "ordering": ["-created_at"],
            },
        ),
    ]
