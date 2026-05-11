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

        Also registers the worker_ready signal so every Celery worker startup
        triggers a sweep of stale 'processing' documents — see
        `_sweep_stale_documents_on_worker_ready` for the rationale.
        """
        # Guard: only warm in the main interpreter, not during migrations or
        # manage.py commands where model download would be unexpected.
        import os
        if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("test"):
            return  # skip in test runs — tests mock the model

        thread = threading.Thread(target=_prewarm_embedding_model, daemon=True)
        thread.start()

        # Connect once at AppConfig ready; the celery import is cheap.
        # weak=False because the connected function is module-scoped and
        # safe to hold strongly.
        from celery.signals import worker_ready  # noqa: PLC0415
        worker_ready.connect(_sweep_stale_documents_on_worker_ready, weak=False)


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


def _sweep_stale_documents_on_worker_ready(sender=None, **kwargs):
    """Reap orphaned 'processing' documents whenever a Celery worker starts.

    Why this signal:
      - Documents whose worker was SIGKILL'd by the OS OOM killer never get
        a status='error' update because the kill happens outside Python.
      - The next time *any* Celery worker boots (deploy, OOM recovery,
        manual restart) is the natural moment to clean up the corpses:
        the surviving worker has DB access and Django context is set up.
      - This is intentionally global (no user_id filter) — at startup the
        worker has no notion of "current user".
    """
    try:
        from apps.knowledge_base.services import reap_stale_processing_documents  # noqa: PLC0415
        n = reap_stale_processing_documents()
        if n:
            logger.info(
                "Celery worker_ready sweep reaped %d orphaned 'processing' documents", n
            )
    except Exception:
        # A failed sweep must NEVER prevent the worker from accepting tasks.
        logger.exception("worker_ready stale-document sweep failed; continuing")
