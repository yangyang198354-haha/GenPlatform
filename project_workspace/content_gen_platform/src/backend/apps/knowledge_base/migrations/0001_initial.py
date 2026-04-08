import django.db.models.deletion
import pgvector.django
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Document",
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
                ("name", models.CharField(max_length=255)),
                ("original_filename", models.CharField(max_length=255)),
                ("file_path", models.CharField(max_length=1024)),
                ("file_size_bytes", models.BigIntegerField()),
                (
                    "file_type",
                    models.CharField(
                        choices=[
                            ("pdf", "PDF"),
                            ("docx", "Word"),
                            ("txt", "TXT"),
                            ("md", "Markdown"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("processing", "处理中"),
                            ("available", "可用"),
                            ("error", "错误"),
                        ],
                        default="processing",
                        max_length=20,
                    ),
                ),
                ("chunk_count", models.IntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "kb_document",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DocumentChunk",
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
                ("chunk_index", models.IntegerField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(dimensions=1024)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="knowledge_base.document",
                    ),
                ),
            ],
            options={
                "db_table": "kb_document_chunk",
                "ordering": ["chunk_index"],
            },
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=models.Index(
                fields=["document", "chunk_index"],
                name="kb_document_chunk_doc_idx",
            ),
        ),
    ]
