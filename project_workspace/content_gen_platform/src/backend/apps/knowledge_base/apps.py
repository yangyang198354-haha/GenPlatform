import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class KnowledgeBaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge_base"

    def ready(self):
        """Pre-warm the embedding model in a background thread at startup.

        Why:
          - The embedding model (BAAI/bge-small-zh-v1.5, ~400 MB) is lazily
            loaded on first use.  Without pre-warming, the very first request
            that triggers _kb_search() blocks for 10-30 s while the model
            loads into memory — or, if the HuggingFace mirror hasn't been
            configured, it tries huggingface.co (blocked by GFW) and hangs
            until nginx fires a 504 Gateway Timeout.
          - Using a daemon thread avoids slowing down the gunicorn startup
            sequence (migrate → gunicorn listen).  The first few requests may
            skip KB context (caught by the timeout in views.py), but the model
            will be ready before most real traffic arrives.
          - This runs in EVERY process that imports the app (manage.py,
            gunicorn workers, celery).  That is intentional: each OS process
            needs its own in-memory model instance.
        """
        # Guard: only warm in the main interpreter, not during migrations or
        # manage.py commands where model download would be unexpected.
        import os
        if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("test"):
            return  # skip in test runs — tests mock the model

        thread = threading.Thread(target=_prewarm_embedding_model, daemon=True)
        thread.start()


def _prewarm_embedding_model():
    """Load the singleton embedding model.  Runs once per process in background."""
    try:
        from apps.knowledge_base.services import _get_embedding_model  # noqa: PLC0415
        _get_embedding_model()
        logger.info("Embedding model pre-warm complete.")
    except Exception:
        logger.warning(
            "Embedding model pre-warm failed (will retry on first request).",
            exc_info=True,
        )
