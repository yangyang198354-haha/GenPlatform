import os

from .development import *  # noqa

# Use a separate DB for tests; allow override via env var for CI
DATABASES["default"]["NAME"] = os.environ.get("POSTGRES_DB", "test_content_gen")  # noqa: F821

# Run Celery tasks synchronously so we can assert side effects
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Speed up password hashing in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use /tmp for file uploads
MEDIA_ROOT = "/tmp/test_media"

# Avoid Redis dependency in unit tests (no Redis service in CI unit test job)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery in-process broker — no Redis needed
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# No Redis channel layer needed in tests
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}
