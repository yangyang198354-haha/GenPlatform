"""Celery tasks for knowledge base processing."""
import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from .models import Document
from .services import process_document as _process_document

logger = logging.getLogger(__name__)

# 5-minute soft limit: raises SoftTimeLimitExceeded (caught below → status="error")
# instead of letting the worker be SIGKILL'd by the OS OOM killer, which bypasses
# all Python exception handlers and leaves the document stuck in "processing".
_SOFT_TIME_LIMIT = 300


@shared_task(bind=True, max_retries=0, soft_time_limit=_SOFT_TIME_LIMIT)
def process_document_task(self, document_id: int) -> None:
    """Async document processing: extract → chunk → embed.

    _process_document() handles all exceptions internally and marks the
    document status as 'available' or 'error'. We set max_retries=0 here
    to avoid retrying after the document status has already been set to
    'error' — retrying would silently reset it to 'processing' again.

    soft_time_limit=300 ensures that if the task exceeds 5 minutes
    (e.g. model loading hangs or encoding a huge document takes too long),
    SoftTimeLimitExceeded is raised and the document is marked 'error'
    rather than being left in 'processing' indefinitely.
    """
    try:
        _process_document(document_id)
    except SoftTimeLimitExceeded:
        # Raised by Celery when the task exceeds soft_time_limit seconds.
        # Mark the document as error so the user gets clear feedback instead
        # of the status staying "processing" forever.
        logger.error(
            "process_document_task timed out after %ds for doc %d",
            _SOFT_TIME_LIMIT,
            document_id,
        )
        Document.objects.filter(pk=document_id).update(
            status="error",
            error_message="处理超时，请重试或联系管理员（文档可能过大）",
        )
    except Exception as exc:
        # Fallback: if _process_document raised unexpectedly (e.g. DB down),
        # still mark the document as error so the user sees a clear status.
        logger.exception("Unexpected error in process_document_task for doc %d", document_id)
        Document.objects.filter(pk=document_id).update(
            status="error", error_message=f"Task error: {exc}"
        )
