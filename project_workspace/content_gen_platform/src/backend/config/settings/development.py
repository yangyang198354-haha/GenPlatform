from .base import *  # noqa

DEBUG = True
SECRET_KEY = "dev-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]

DATABASES["default"].update(  # noqa: F821
    {
        "NAME": "content_gen_dev",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "localhost",
        "PORT": "5432",
    }
)

CORS_ALLOW_ALL_ORIGINS = True

# Use local filesystem in development
STORAGE_BACKEND = "local"

# Reduced token lifetime for development testing
from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

ENCRYPTION_KEY = "dev-encryption-key-32bytesXXXXXXXX"  # 32 chars for dev only
