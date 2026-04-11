"""
Change embedding vector dimension from 1024 (bge-m3) to 512 (bge-small-zh-v1.5).

bge-small-zh-v1.5 is 90 MB vs 2.3 GB for bge-m3, making it practical to
pre-download during Docker build and load on servers with limited RAM (~250 MB).

Since all existing DocumentChunk rows were produced when Celery was broken
(tasks never ran), there are no valid chunk rows in production, so the dimension
change is purely a schema migration with no data loss.
"""
import pgvector.django
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge_base", "0001_initial"),
    ]

    operations = [
        # Drop existing chunks (dimension change requires column recreation)
        migrations.RunSQL(
            sql="DELETE FROM kb_document_chunk;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="documentchunk",
            name="embedding",
            field=pgvector.django.VectorField(dimensions=512),
        ),
    ]
