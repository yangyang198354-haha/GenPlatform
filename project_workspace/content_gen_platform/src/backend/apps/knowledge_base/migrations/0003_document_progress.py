"""
Add progress (0-100) and progress_message fields to Document.

These fields allow the Celery task to report real-time processing
progress so the frontend can display a progress bar instead of a
static "处理中" tag.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge_base", "0002_alter_documentchunk_embedding_dimension"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="progress",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="document",
            name="progress_message",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
