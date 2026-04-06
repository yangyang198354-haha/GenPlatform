"""Celery tasks for knowledge base processing."""
from celery import shared_task
from .services import process_document as _process_document


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_document_task(self, document_id: int) -> None:
    """Async document processing: extract → chunk → embed."""
    try:
        _process_document(document_id)
    except Exception as exc:
        raise self.retry(exc=exc)
