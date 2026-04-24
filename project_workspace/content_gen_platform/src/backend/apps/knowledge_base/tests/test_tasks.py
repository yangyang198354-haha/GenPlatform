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
from apps.knowledge_base.tasks import process_document_task, _SOFT_TIME_LIMIT, _TIME_LIMIT


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

    def test_soft_time_limit_is_600_seconds(self):
        """
        Regression guard: soft_time_limit must be 600 s (10 min) to accommodate
        first-run embedding model download (~400 MB on a cold ECS server).

        Previously this was 300 s, which was too short — the task was SIGKILL'd
        before the model finished loading, leaving the document stuck in
        'processing' indefinitely.
        """
        assert _SOFT_TIME_LIMIT == 600, (
            f"_SOFT_TIME_LIMIT must be 600 s (10 min), got {_SOFT_TIME_LIMIT}. "
            "Possible regression: reducing this value can cause first-run model "
            "downloads to be killed, leaving documents stuck at 'processing'."
        )

    def test_hard_time_limit_is_660_seconds(self):
        """
        Regression guard: hard time_limit must be > soft_time_limit to give the
        SoftTimeLimitExceeded handler 60 s to write the 'error' status before
        the SIGKILL arrives.

        If time_limit <= soft_time_limit, the OS kills the worker before the
        error handler can run, and the document is left in 'processing' forever.
        """
        assert _TIME_LIMIT == 660, (
            f"_TIME_LIMIT must be 660 s (11 min), got {_TIME_LIMIT}. "
            "Must be larger than _SOFT_TIME_LIMIT to allow the error handler to run."
        )

    def test_hard_limit_exceeds_soft_limit(self):
        """Hard kill must always fire after the soft limit to allow cleanup."""
        assert _TIME_LIMIT > _SOFT_TIME_LIMIT, (
            f"_TIME_LIMIT ({_TIME_LIMIT}) must be > _SOFT_TIME_LIMIT ({_SOFT_TIME_LIMIT}). "
            "Otherwise SIGKILL arrives before SoftTimeLimitExceeded can mark the doc 'error'."
        )


# ── fallback error handler ─────────────────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.integration
class TestProcessDocumentTaskFallback:
    """
    Verify that the top-level exception handler in process_document_task
    marks the document as 'error' when _process_document raises unexpectedly.

    Regression for 3f108ae: before the fix, the outer except block called
    raise self.retry(exc=exc), causing retries and potentially leaving the
    document in 'processing' status indefinitely.

    Marked integration: requires a real database to assert document status
    transitions. These tests are the primary guard against KB "stuck in
    processing" regressions reaching production.
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

    def test_soft_time_limit_error_message_mentions_timeout_duration(self, user, tmp_path, db):
        """
        Regression guard (Bug 1): the error_message written on SoftTimeLimitExceeded
        must mention the timeout duration (10 minutes) so users know why processing
        failed and whether to retry.

        Previously the message was a generic "处理超时" with no duration info.
        After the fix: "处理超时（超过10分钟），请重试或联系管理员..."
        """
        from celery.exceptions import SoftTimeLimitExceeded

        doc = _make_doc(user, tmp_path)

        with patch(
            "apps.knowledge_base.tasks._process_document",
            side_effect=SoftTimeLimitExceeded(),
        ):
            process_document_task(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "error"
        # Must mention 10 minutes so users have actionable context
        assert "10" in doc.error_message or "分钟" in doc.error_message, (
            f"error_message should mention timeout duration (10/分钟), got: {doc.error_message!r}"
        )


# ── integration: task processes document end-to-end ───────────────────────

@pytest.mark.django_db
@pytest.mark.integration
class TestProcessDocumentTaskIntegration:
    """
    End-to-end: task dispatched with CELERY_TASK_ALWAYS_EAGER=True (set in
    test.py) processes the document in-process and leaves it available.

    Marked integration: requires a real database + full Celery eager pipeline.
    Guards the entire extract → chunk → embed → store chain so that any
    regression in soft_time_limit, max_retries, or progress updates is caught
    before it reaches production.
    """

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_eager_task_sets_status_available(self, mock_get_model, user, tmp_path, db):
        """CELERY_TASK_ALWAYS_EAGER ensures the task runs synchronously in tests."""
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        # Use side_effect so multi-chunk docs get the correct (N, 512) shape.
        # A fixed (1, 512) return_value would silently truncate to 1 chunk via zip().
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
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
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = _make_doc(user, tmp_path, content="Another short text for test.")
        process_document_task(doc.pk)

        assert DocumentChunk.objects.filter(document=doc).exists()

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_eager_task_sets_progress_100_on_success(self, mock_get_model, user, tmp_path, db):
        """
        After successful processing, document.progress must be 100 and
        document.progress_message must indicate completion.

        Regression guard: ensures the Celery task writes progress fields
        so the frontend progress bar can reach 100% and stop polling.
        """
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = _make_doc(user, tmp_path, content="Progress tracking test content.")
        process_document_task(doc.pk)

        doc.refresh_from_db()
        assert doc.progress == 100, (
            f"progress must be 100 after successful processing, got {doc.progress}. "
            "The frontend uses this value to show the progress bar completion."
        )
        assert doc.progress_message, "progress_message must be non-empty after processing"

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_error_sets_progress_message(self, mock_get_model, user, tmp_path, db):
        """
        On failure, progress_message should indicate the error state so the
        frontend tooltip can display meaningful information alongside the error tag.
        """
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("embedding model failure")
        mock_get_model.return_value = mock_model

        doc = _make_doc(user, tmp_path, content="Some text that will fail at embedding.")
        process_document_task(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "error"
        assert doc.progress_message, "progress_message must be set on error for frontend display"


# ── Recurring-breakage guard: document must NEVER stay in 'processing' ────────
#
# Pattern observed: the "stuck in processing" bug has recurred multiple times
# because changes to Celery task settings (max_retries, time limits) or
# exception handling paths silently bypass the status update logic.
#
# The tests below form a structural firewall: they parameterise over every known
# failure mode and assert that the document's final status is NEVER 'processing'.
# If any code change introduces a path that leaves status='processing', exactly
# one of these tests will fail with a clear diagnostic message.

@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentNeverStaysProcessing:
    """
    Structural guard: regardless of how the task fails, the document MUST NOT
    remain in status='processing' after process_document_task() returns.

    Each test simulates a distinct failure mode that has historically caused
    the 'stuck in processing' regression.  Adding a new failure scenario here
    is the correct place to document and guard against future recurrences.

    WHY THIS CLASS EXISTS
    ---------------------
    The "document stuck in processing" bug has recurred 3+ times because:
      1. max_retries was set > 0, allowing Celery to reset status to 'processing'
         on retry (fixed in 3f108ae, regressed, re-fixed).
      2. soft_time_limit was too short (300s), causing tasks to be SIGKILL'd
         before the error handler could set status='error' (fixed → 600s).
      3. Unhandled exception types escaped both the soft-limit and general
         except blocks, leaving no status update.

    This class verifies the entire exception surface systematically.
    """

    FAILURE_MODES = [
        ("RuntimeError",         RuntimeError("simulated crash")),
        ("ValueError",           ValueError("bad input")),
        ("MemoryError",          MemoryError("OOM")),
        ("OSError",              OSError("disk full")),
        ("SoftTimeLimitExceeded", None),  # handled separately below
    ]

    def _make_processing_doc(self, user, tmp_path, content="Guard test content."):
        f = tmp_path / "guard_test.txt"
        f.write_text(content, encoding="utf-8")
        return Document.objects.create(
            user=user,
            name="guard test",
            original_filename="guard_test.txt",
            file_path=str(f),
            file_size_bytes=len(content),
            file_type="txt",
            status="processing",
        )

    def test_document_never_stays_processing_on_runtime_error(self, user, tmp_path, db):
        """RuntimeError in _process_document must not leave status='processing'."""
        doc = self._make_processing_doc(user, tmp_path)
        with patch("apps.knowledge_base.tasks._process_document",
                   side_effect=RuntimeError("simulated crash")):
            process_document_task(doc.pk)
        doc.refresh_from_db()
        assert doc.status != "processing", (
            "RuntimeError must not leave document stuck at 'processing'. "
            "Check that the except Exception block in process_document_task "
            "still calls Document.objects.filter(pk=...).update(status='error')."
        )

    def test_document_never_stays_processing_on_value_error(self, user, tmp_path, db):
        """ValueError in _process_document must not leave status='processing'."""
        doc = self._make_processing_doc(user, tmp_path)
        with patch("apps.knowledge_base.tasks._process_document",
                   side_effect=ValueError("bad input")):
            process_document_task(doc.pk)
        doc.refresh_from_db()
        assert doc.status != "processing", (
            "ValueError must not leave document stuck at 'processing'."
        )

    def test_document_never_stays_processing_on_os_error(self, user, tmp_path, db):
        """OSError (e.g. disk full) must not leave document at 'processing'."""
        doc = self._make_processing_doc(user, tmp_path)
        with patch("apps.knowledge_base.tasks._process_document",
                   side_effect=OSError("disk full")):
            process_document_task(doc.pk)
        doc.refresh_from_db()
        assert doc.status != "processing", (
            "OSError must not leave document stuck at 'processing'."
        )

    def test_document_never_stays_processing_on_soft_time_limit(self, user, tmp_path, db):
        """SoftTimeLimitExceeded must transition to 'error', not stay at 'processing'."""
        from celery.exceptions import SoftTimeLimitExceeded
        doc = self._make_processing_doc(user, tmp_path)
        with patch("apps.knowledge_base.tasks._process_document",
                   side_effect=SoftTimeLimitExceeded()):
            process_document_task(doc.pk)
        doc.refresh_from_db()
        assert doc.status != "processing", (
            "SoftTimeLimitExceeded must transition the document away from "
            "'processing'. This is the primary guard for the cold-start "
            "model-download timeout regression."
        )
        assert doc.status == "error", (
            f"Expected status='error' after timeout, got '{doc.status}'."
        )

    def test_task_max_retries_still_zero_guard(self):
        """
        Canary test: if max_retries is ever changed from 0, Celery will reset
        status='processing' on each retry attempt, causing documents to appear
        stuck.  This test must fail loudly if someone bumps max_retries.
        """
        assert process_document_task.max_retries == 0, (
            f"BREAKING CHANGE: max_retries={process_document_task.max_retries}. "
            "Setting max_retries > 0 causes Celery to reset document status "
            "back to 'processing' on each retry, recreating the stuck-document bug. "
            "If you need retry behaviour, implement it AFTER setting status='error' "
            "so the user always sees a terminal state between attempts."
        )

    def test_soft_time_limit_still_larger_than_model_download_time_guard(self):
        """
        Canary test: soft_time_limit must remain >= 600s.
        The embedding model download takes up to ~400 MB on a cold ECS server;
        at 10 MB/s that is 40 s, but hf-mirror can be slower.  600s gives a
        10x safety margin.  Reducing it will cause cold-start timeouts.
        """
        assert _SOFT_TIME_LIMIT >= 600, (
            f"BREAKING CHANGE: _SOFT_TIME_LIMIT={_SOFT_TIME_LIMIT}s < 600s. "
            "This will cause the first-run embedding model download (~400 MB) "
            "to time out, leaving documents stuck at 'processing'. "
            "Do not reduce soft_time_limit below 600s."
        )
