"""
迁移：新增 image_batch 表，ImageGenerationRequest 新增 batch / model / provider 字段。

关联需求：FR-5、ADR-04、OQ-4（DB CHECK 约束保证单批次 ≤ 4 张）
创建时间：2026-05-13

回滚方法（Django 命令）：
    python manage.py migrate image_generator 0001_initial

回滚 SQL（PostgreSQL，仅在无法使用 Django 管理命令时使用）：
    ALTER TABLE image_generation_request DROP COLUMN IF EXISTS batch_id;
    ALTER TABLE image_generation_request DROP COLUMN IF EXISTS model;
    ALTER TABLE image_generation_request DROP COLUMN IF EXISTS provider;
    DROP TABLE IF EXISTS image_batch;
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("image_generator", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. 创建 image_batch 表（全新表，无循环依赖）
        migrations.CreateModel(
            name="ImageBatch",
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
                ("name", models.CharField(max_length=255, verbose_name="批次名称")),
                ("model", models.CharField(max_length=64, verbose_name="豆包模型版本")),
                ("prompt", models.TextField(verbose_name="提示词")),
                ("is_img2img", models.BooleanField(default=False, verbose_name="是否图生图")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "等待中"),
                            ("processing", "生成中"),
                            ("completed", "已完成"),
                            ("partial_failed", "部分失败"),
                            ("failed", "失败"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="批次状态",
                    ),
                ),
                ("total_count", models.IntegerField(verbose_name="预计生成张数（1-4）")),
                ("completed_count", models.IntegerField(default=0, verbose_name="已完成张数")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="image_batches",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="所属用户",
                    ),
                ),
            ],
            options={
                "verbose_name": "图片批次",
                "verbose_name_plural": "图片批次",
                "db_table": "image_batch",
                "ordering": ["-created_at"],
            },
        ),
        # 2. 添加 DB-level CHECK 约束：total_count 在 1-4 之间（OQ-4）
        migrations.AddConstraint(
            model_name="imagebatch",
            constraint=models.CheckConstraint(
                check=models.Q(total_count__gte=1) & models.Q(total_count__lte=4),
                name="image_batch_total_count_1_to_4",
            ),
        ),
        # 3. ImageGenerationRequest 新增 batch FK（历史数据 SET_NULL，OQ-5）
        migrations.AddField(
            model_name="imagegenerationrequest",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="requests",
                to="image_generator.imagebatch",
                verbose_name="所属批次",
            ),
        ),
        # 4. ImageGenerationRequest 新增 model 字段（历史数据默认空字符串）
        migrations.AddField(
            model_name="imagegenerationrequest",
            name="model",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="豆包模型名",
            ),
            preserve_default=False,
        ),
        # 5. ImageGenerationRequest 新增 provider 字段（历史数据默认空字符串，OQ-5）
        migrations.AddField(
            model_name="imagegenerationrequest",
            name="provider",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
                verbose_name="生成来源",
            ),
            preserve_default=False,
        ),
    ]
