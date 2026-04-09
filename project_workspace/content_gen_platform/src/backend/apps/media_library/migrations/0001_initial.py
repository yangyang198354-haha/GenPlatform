"""Initial migration for media_library app."""
import apps.media_library.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MediaItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("media_type", models.CharField(
                    choices=[("image", "图片"), ("video", "视频"), ("audio", "音频")],
                    max_length=10,
                )),
                ("source", models.CharField(
                    choices=[("ai_generated", "AI 生成"), ("uploaded", "用户上传")],
                    max_length=20,
                )),
                ("file", models.FileField(upload_to=apps.media_library.models._upload_to)),
                ("thumbnail", models.FileField(
                    blank=True,
                    null=True,
                    upload_to=apps.media_library.models._thumbnail_upload_to,
                )),
                ("title", models.CharField(max_length=255)),
                ("file_size", models.BigIntegerField(default=0)),
                ("duration_sec", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="media_items",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "media_item",
                "ordering": ["-created_at"],
            },
        ),
    ]
