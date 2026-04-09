"""Initial migration for image_generator app."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("media_library", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImageGenerationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prompt", models.TextField()),
                ("ref_image_path", models.CharField(blank=True, max_length=1024)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "等待中"),
                        ("processing", "生成中"),
                        ("completed", "已完成"),
                        ("failed", "失败"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("jimeng_task_id", models.CharField(blank=True, max_length=255)),
                ("result_image_url", models.CharField(blank=True, max_length=1024)),
                ("error_message", models.TextField(blank=True)),
                ("progress", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="image_generation_requests",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("media_item", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="image_generation_requests",
                    to="media_library.mediaitem",
                )),
            ],
            options={
                "db_table": "image_generation_request",
                "ordering": ["-created_at"],
            },
        ),
    ]
