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
            name="VideoProject",
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
                            ("draft", "草稿"),
                            ("generating", "生成中"),
                            ("completed", "已完成"),
                            ("failed", "失败"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("final_video_path", models.CharField(blank=True, max_length=1024)),
                ("jimeng_task_id", models.CharField(blank=True, max_length=255)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="video_projects",
                        to="content.content",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="video_projects",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "video_project",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Scene",
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
                ("scene_index", models.IntegerField()),
                ("scene_prompt", models.TextField()),
                ("narration", models.TextField()),
                ("voice_style", models.JSONField(default=dict)),
                ("duration_sec", models.IntegerField(default=5)),
                (
                    "transition",
                    models.CharField(
                        choices=[
                            ("cut", "硬切"),
                            ("fade", "淡入淡出"),
                            ("push_pull", "推拉"),
                        ],
                        default="cut",
                        max_length=20,
                    ),
                ),
                ("jimeng_clip_url", models.URLField(blank=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "video_project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scenes",
                        to="video_generator.videoproject",
                    ),
                ),
            ],
            options={
                "db_table": "video_scene",
                "ordering": ["scene_index"],
            },
        ),
    ]
