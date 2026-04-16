"""
Regression tests for apps/knowledge_base/tasks.py.

fix(celery) commit 3f108ae patched two bugs:
  1. Tasks were silently routed to the built-in 'celery' queue instead of
     'default', so the worker never consumed them.
     Fix: CELERY_TASK_DEFAULT_QUEUE = "default" in base.py.
  2. process_document_task used max_retries=3, meaning a doc whose status
     was already 'error' would be silently reset to 'processing' on retry.
     Fix: max_retries=0 + fallback error handler that marks the doc 'error'.
"""
import pytest
from unittest.mock import patch

from apps.knowledge_base.models import Document
from apps.knowledge_base.tasks import process_document_task


# ── helpers ────────────────────────────────────────────────────────────────

def _make_doc(user, tmp_path, content="Test document content.", status="processing"):
    f = tmp_path / "task_test.txt"
    f.write_text(content, encoding="utf-8")
    return Document.objects.create(
        user=user,
        name="task test doc",
        original_filename="task_test.txt",
        file_path=str(f),
        file_size_bytes=len(content),
        file_type="txt",
        status=status,
    )


# ── max_retries setting ────────────────────────────────────────────────────

class TestProcessDocumentTaskConfig:
    """
    Verify task-level Celery settings that prevent retry loops.

    Regression for 3f108ae: max_retries was 3, which silently reset a
    document from status='error' back to status='processing' on each retry.
    """

    def test_max_retries_is_zero(self):
        """process_document_task.max_retries must be 0 — no retry loops."""
        assert process_document_task.max_retries == 0, (
            "max_retries must be 0. "
            "Possible regression of 3f108ae: non-zero value causes retried tasks "
            "to silently reset document status from 'error' back to 'processing'."
        )

    def test_task_has_document_id_parameter(self):
        """Task signature must accept document_id as its first user-facing parameter."""
        import inspect
        sig = inspect.signature(process_document_task.run)
        params = list(sig.parameters.keys())
        assert "document_id" in params


# ── fallback error handler ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessDocumentTaskFallback:
    """
    Verify that the top-level exception handler in process_document_task
    marks the document as 'error' when _process_document raises unexpectedly.

    Regression for 3f108ae: before the fix, the outer except block called
    raise self.retry(exc=exc), causing retries and potentially leaving the
    document in 'processing' status indefinitely.
    """

    def test_unexpected_exception_marks_doc_error(self, user, tmp_path, db):
        """If _process_document raises, the document must be set to status='error'."""
        doc = _make_doc(user, tmp_path)

        with patch(
            "apps.knowledge_base.tasks._process_document",
            side_effect=RuntimeError("DB connection lost"),
        ):
            process_document_task(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "error", (
            "Fallback handler must set status='error'. "
            "Possible regression of 3f108ae fix."
        )

    def test_unexpected_exception_populates_error_message(self, user, tmp_path, db):
        """error_message must contain the exception text so users can see why it failed."""
        doc = _make_doc(user, tmp_path)

        with patch(
            "apps.knowledge_base.tasks._process_document",
            side_effect=RuntimeError("quota exceeded"),
        ):
            process_document_task(doc.pk)

        doc.refresh_from_db()
        assert "quota exceeded" in doc.error_message

    def test_nonexistent_document_id_does_not_raise(self, db):
        """Task with a nonexistent document_id must complete silently (doc may be deleted)."""
        # Should not raise — _process_document handles missing docs internally.
        process_document_task(99999)

    def test_soft_time_limit_exceeded_marks_doc_error(self, user, tmp_path, db):
        """
        Regression: SoftTimeLimitExceeded must set status='error' with a user-visible
        message instead of leaving the document stuck at 'processing' forever.

        Root cause scenario: Celery raises SoftTimeLimitExceeded when the task exceeds
        soft_time_limit seconds (e.g. model loading hangs, or encoding a huge DOCX).
        Without an explicit handler this exception escapes all Python error handlers
        and the document stays in 'processing' indefinitely.
        """
        from celery.exceptions import SoftTimeLimitExceeded

        doc = _make_doc(user, tmp_path)

        with patch(
            "apps.knowledge_base.tasks._process_document",
            side_effect=SoftTimeLimitExceeded(),
        ):
            process_document_task(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "error", (
            "SoftTimeLimitExceeded must transition the document to status='error'. "
            "Without this, a timed-out task leaves the document stuck at 'processing'."
        )
        assert doc.error_message, "error_message must be non-empty so the user sees an explanation"

    def test_soft_time_limit_exceeded_does_not_raise(self, user, tmp_path, db):
        """Task must swallow SoftTimeLimitExceeded rather than propagating it."""
        from celery.exceptions import SoftTimeLimitExceeded

        doc = _make_doc(user, tmp_path)

        # Must not raise — task should handle the exception internally
        with patch(
            "apps.knowledge_base.tasks._process_document",
            side_effect=SoftTimeLimitExceeded(),
        ):
            process_document_task(doc.pk)  # should complete without raising

    def test_fallback_does_not_retry(self, user, tmp_path, db):
        """On unexpected exception the task must NOT call self.retry()."""
        doc = _make_doc(user, tmp_path)

        with patch("apps.knowledge_base.tasks._process_document", side_effect=RuntimeError("boom")):
            with patch.object(process_document_task, "retry") as mock_retry:
                process_document_task(doc.pk)
                mock_retry.assert_not_called(), (
                    "self.retry() must not be called. "
                    "Regression of 3f108ae: retrying resets status to 'processing'."
                )


# ── integration: task processes document end-to-end ───────────────────────

@pytest.mark.django_db
class TestProcessDocumentTaskIntegration:
    """
    End-to-end: task dispatched with CELERY_TASK_ALWAYS_EAGER=True (set in
    test.py) processes the document in-process and leaves it available.
    """

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_eager_task_sets_status_available(self, mock_get_model, user, tmp_path, db):
        """CELERY_TASK_ALWAYS_EAGER ensures the task runs synchronously in tests."""
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((1, 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = _make_doc(user, tmp_path, content="A short but valid text for chunking.")
        process_document_task(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "available"
        assert doc.chunk_count >= 1

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_eager_task_creates_chunks(self, mock_get_model, user, tmp_path, db):
        """Task must create DocumentChunk rows (embedding pipeline ran)."""
        import numpy as np
        from unittest.mock import MagicMock
        from apps.knowledge_base.models import DocumentChunk

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((1, 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = _make_doc(user, tmp_path, content="Another short text for test.")
        process_document_task(doc.pk)

        assert DocumentChunk.objects.filter(document=doc).exists()
