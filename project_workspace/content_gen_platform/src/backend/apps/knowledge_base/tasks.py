"""Celery tasks for knowledge base processing."""
import logging

from celery import shared_task

from .models import Document
from .services import process_document as _process_document

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def process_document_task(self, document_id: int) -> None:
    """Async document processing: extract → chunk → embed.

    _process_document() handles all exceptions internally and marks the
    document status as 'available' or 'error'. We set max_retries=0 here
    to avoid retrying after the document status has already been set to
    'error' — retrying would silently reset it to 'processing' again.
    """
    try:
        _process_document(document_id)
    except Exception as exc:
        # Fallback: if _process_document raised unexpectedly (e.g. DB down),
        # still mark the document as error so the user sees a clear status.
        logger.exception("Unexpected error in process_document_task for doc %d", document_id)
        Document.objects.filter(pk=document_id).update(
            status="error", error_message=f"Task error: {exc}"
        )
