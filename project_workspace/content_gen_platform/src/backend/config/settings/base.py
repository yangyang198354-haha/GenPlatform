"""
Base Django settings for content_gen_platform.
"""
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production")

DEBUG = False

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost 127.0.0.1").split()

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # required by BLACKLIST_AFTER_ROTATION=True
    "corsheaders",
    "channels",
    "django_celery_beat",
    "django_celery_results",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.knowledge_base",
    "apps.llm_gateway",
    "apps.content",
    "apps.publisher",
    "apps.video_generator",
    "apps.notifications",
    "apps.settings_vault",
    "apps.media_library",
    "apps.image_generator",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "content_gen"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── REST Framework ──────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/hour",
        "document_status": "120/minute",
        "media_list": "300/minute",
        "llm_generate": "10/minute",
        "publish": "30/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ── Celery ───────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Must match the -Q flag in docker-compose.yml celery_worker command.
# Celery's built-in default queue is named "celery", but our worker
# listens to "default". Without this setting, all tasks without an
# explicit queue= are sent to "celery" and never processed.
CELERY_TASK_DEFAULT_QUEUE = "default"

# ── Django Channels ───────────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# ── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173 http://localhost:3000"
).split()
CORS_ALLOW_CREDENTIALS = True

# ── File Storage ──────────────────────────────────────────────────────────────
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")  # local | minio

if STORAGE_BACKEND == "minio":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = os.environ.get("MINIO_ACCESS_KEY")
    AWS_SECRET_ACCESS_KEY = os.environ.get("MINIO_SECRET_KEY")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("MINIO_BUCKET", "content-gen")
    AWS_S3_ENDPOINT_URL = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = "private"

# ── Knowledge Base / Embedding ────────────────────────────────────────────────
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
EMBEDDING_DEVICE = os.environ.get("EMBEDDING_DEVICE", "cpu")
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
USER_STORAGE_QUOTA_BYTES = 2 * 1024 ** 3    # 2 GB

# 目录批量上传硬上限（业务层）+ Django 解析层 override
# INC-2026-05-16：Django 4.1+ 默认 DATA_UPLOAD_MAX_NUMBER_FILES=100，目录上传
# 超过 100 文件时请求在 view 入口前就被 Django 拒绝（空 body 400），用户看到
# "目录上传失败"无任何业务信息。下面三个值必须同步提升，缺一不可。
MAX_BATCH_UPLOAD_FILES = 2000
DATA_UPLOAD_MAX_NUMBER_FILES = MAX_BATCH_UPLOAD_FILES        # 每个文件占 1 field
DATA_UPLOAD_MAX_NUMBER_FIELDS = MAX_BATCH_UPLOAD_FILES + 100  # 余量供 relative_paths 等

# ── Encryption ────────────────────────────────────────────────────────────────
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")  # 32-byte base64 key; set in production

# ── 豆包 Ark 图片生成配置（NFR-3，ADR-06）──────────────────────────────────────
# ARK_API_KEY 不在此处硬编码，必须通过 settings_vault 存储（AES-256-GCM 加密）
# 以下为运行时默认值（不含任何密钥），覆盖后在 Celery task 中通过 UserServiceConfig 获取
DOUBAO_ARK_BASE_URL = os.environ.get(
    "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
)
# 单批次并发模式开关（ADR-03，降级方案开关）
# "single_request"：单次 Ark 请求返回 n 张（优先方案）
# "multi_request"：串行多次 Ark 请求（降级方案，若 Ark 不支持 n>1 参数时使用）
DOUBAO_BATCH_MODE = os.environ.get("DOUBAO_BATCH_MODE", "single_request")

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
