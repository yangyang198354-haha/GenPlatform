"""Unit tests for knowledge_base services (text extraction, chunking, processing)."""
import os
import pytest
from unittest.mock import patch, MagicMock
from apps.knowledge_base.services import _chunk_text, _extract_text, process_document
from apps.knowledge_base.models import Document


# ── _chunk_text ────────────────────────────────────────────────────────────

class TestChunkText:
    def test_basic_chunking(self):
        text = "a" * 1000
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) > 1
        assert all(len(c) <= 512 for c in chunks)

    def test_single_chunk_when_short(self):
        text = "short text"
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    def test_overlap_creates_redundancy(self):
        text = "a" * 600
        chunks = _chunk_text(text, chunk_size=512, overlap=100)
        # With overlap, adjacent chunks share content
        assert len(chunks) == 2
        # Second chunk starts at 512-100=412, ends at 924 (or end of text)
        assert chunks[1] == text[412:]

    def test_empty_text_returns_empty(self):
        chunks = _chunk_text("", chunk_size=512, overlap=64)
        assert chunks == []

    def test_whitespace_only_filtered(self):
        text = "   \n\t  "
        chunks = _chunk_text(text, chunk_size=512, overlap=64)
        assert chunks == []

    def test_exact_chunk_size(self):
        text = "x" * 512
        chunks = _chunk_text(text, chunk_size=512, overlap=0)
        assert len(chunks) == 1

    def test_no_overlap(self):
        text = "abcdefghij"
        chunks = _chunk_text(text, chunk_size=4, overlap=0)
        assert chunks == ["abcd", "efgh", "ij"]


# ── _extract_text ──────────────────────────────────────────────────────────

class TestExtractText:
    def test_extract_txt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello, world!", encoding="utf-8")
        result = _extract_text(str(f), "txt")
        assert result == "Hello, world!"

    def test_extract_md(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\nSome content.", encoding="utf-8")
        result = _extract_text(str(f), "md")
        assert "Title" in result

    def test_unsupported_type_raises(self, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("data", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported file type"):
            _extract_text(str(f), "xyz")


# ── process_document ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessDocument:
    def _make_doc(self, user, tmp_path, content="Hello world, this is a test document."):
        f = tmp_path / "doc.txt"
        f.write_text(content, encoding="utf-8")
        return Document.objects.create(
            user=user,
            name="test doc",
            original_filename="doc.txt",
            file_path=str(f),
            file_size_bytes=len(content),
            file_type="txt",
            status="processing",
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_success(self, mock_get_model, user, tmp_path):
        # Mock the embedding model to return fake vectors
        mock_model = MagicMock()
        import numpy as np
        mock_model.encode.return_value = np.zeros((1, 1024), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "available"
        assert doc.chunk_count >= 1
        assert doc.error_message == ""

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_creates_chunks(self, mock_get_model, user, tmp_path):
        from apps.knowledge_base.models import DocumentChunk
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((1, 1024), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)

        assert DocumentChunk.objects.filter(document=doc).count() >= 1

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_replaces_existing_chunks(self, mock_get_model, user, tmp_path):
        from apps.knowledge_base.models import DocumentChunk
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((1, 1024), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)
        first_count = DocumentChunk.objects.filter(document=doc).count()

        # Re-process — old chunks should be deleted first
        process_document(doc.pk)
        second_count = DocumentChunk.objects.filter(document=doc).count()
        assert second_count == first_count  # same count, not doubled

    def test_process_document_not_found(self):
        # Should not raise; logs error and returns
        process_document(99999)  # nonexistent ID

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_extract_failure_sets_error(self, mock_get_model, user, db):
        # Point to a file that doesn't exist
        doc = Document.objects.create(
            user=user,
            name="bad doc",
            original_filename="bad.txt",
            file_path="/nonexistent/path/bad.txt",
            file_size_bytes=100,
            file_type="txt",
            status="processing",
        )
        process_document(doc.pk)
        doc.refresh_from_db()
        assert doc.status == "error"
        assert doc.error_message != ""
