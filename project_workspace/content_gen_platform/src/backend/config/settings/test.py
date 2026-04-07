from .development import *  # noqa

# Use a separate DB for tests
DATABASES["default"]["NAME"] = "test_content_gen"  # noqa: F821

# Run Celery tasks synchronously so we can assert side effects
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Speed up password hashing in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use /tmp for file uploads
MEDIA_ROOT = "/tmp/test_media"
