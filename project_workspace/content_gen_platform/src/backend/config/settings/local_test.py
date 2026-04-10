"""
Local test settings: SQLite-backed, no external services required.
Used for running tests in Claude Code / developer laptops without PostgreSQL.
Knowledge-base app excluded because it requires pgvector (PostgreSQL-only).
"""
from .test import *  # noqa

# SQLite — no PostgreSQL needed locally
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Exclude knowledge_base: its DocumentChunk model uses pgvector VectorField
# which is incompatible with SQLite. KB tests are still run in CI against PG.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "apps.knowledge_base"]  # noqa: F821

# Use /tmp for file uploads (already set in test.py, restated for clarity)
import tempfile, os
MEDIA_ROOT = os.path.join(tempfile.gettempdir(), "local_test_media")

# Disable throttling so test isolation is not affected by shared locmem cache
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F821
