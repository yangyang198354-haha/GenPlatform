"""Unit tests for knowledge_base services (text extraction, chunking, processing)."""
import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from apps.knowledge_base.services import (
    _chunk_text, _extract_text, _ocr_pdf, process_document, search, _update_progress,
)
from apps.knowledge_base.models import Document, DocumentChunk


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

    # ── DOCX extraction (regression for cf06bef) ───────────────────────────

    def test_extract_docx_paragraphs(self, tmp_path):
        """DOCX paragraph text is extracted correctly."""
        docx_mod = pytest.importorskip("docx", reason="python-docx not installed")
        doc = docx_mod.Document()
        doc.add_paragraph("First paragraph.")
        doc.add_paragraph("Second paragraph.")
        path = tmp_path / "test.docx"
        doc.save(str(path))

        result = _extract_text(str(path), "docx")
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_extract_docx_table_cells(self, tmp_path):
        """
        Regression for cf06bef: DOCX table cell text must be included.
        Before the fix, table content was silently dropped.
        """
        docx_mod = pytest.importorskip("docx", reason="python-docx not installed")
        doc = docx_mod.Document()
        doc.add_paragraph("Intro paragraph.")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Header A"
        table.cell(0, 1).text = "Header B"
        table.cell(1, 0).text = "Cell 1"
        table.cell(1, 1).text = "Cell 2"
        path = tmp_path / "with_table.docx"
        doc.save(str(path))

        result = _extract_text(str(path), "docx")
        assert "Intro paragraph." in result
        assert "Header A" in result
        assert "Header B" in result
        assert "Cell 1" in result
        assert "Cell 2" in result

    def test_extract_docx_empty_cells_skipped(self, tmp_path):
        """Empty DOCX table cells must not produce blank lines in output."""
        docx_mod = pytest.importorskip("docx", reason="python-docx not installed")
        doc = docx_mod.Document()
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Content"
        table.cell(0, 1).text = ""  # empty — should be skipped
        path = tmp_path / "empty_cell.docx"
        doc.save(str(path))

        result = _extract_text(str(path), "docx")
        assert "Content" in result
        # Empty cell should not produce a blank entry
        lines = [ln for ln in result.splitlines() if ln.strip() == ""]
        assert len(lines) == 0

    def test_extract_docx_missing_file_raises(self, tmp_path):
        """Pointing at a non-existent DOCX raises RuntimeError."""
        pytest.importorskip("docx", reason="python-docx not installed")
        with pytest.raises(RuntimeError, match="DOCX extraction failed"):
            _extract_text(str(tmp_path / "ghost.docx"), "docx")

    # ── PDF extraction ─────────────────────────────────────────────────────

    def test_extract_pdf_text(self, tmp_path):
        """Text embedded in a PDF page is returned by _extract_text."""
        pypdf = pytest.importorskip("pypdf", reason="pypdf not installed")
        writer = pypdf.PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        path = tmp_path / "test.pdf"
        with open(str(path), "wb") as f:
            writer.write(f)

        # pypdf can at least read back a blank page without raising
        result = _extract_text(str(path), "pdf")
        assert isinstance(result, str)

    def test_extract_pdf_with_text_content(self, tmp_path):
        """
        PDF with embedded text layers returns the text.
        We write a page with text via reportlab if available,
        otherwise skip and rely on the blank-page test above.
        """
        pytest.importorskip("pypdf", reason="pypdf not installed")
        reportlab = pytest.importorskip("reportlab", reason="reportlab not installed")
        from reportlab.pdfgen import canvas as rl_canvas

        path = tmp_path / "text.pdf"
        c = rl_canvas.Canvas(str(path))
        c.drawString(100, 700, "Hello PDF World")
        c.save()

        result = _extract_text(str(path), "pdf")
        assert "Hello PDF World" in result

    def test_extract_pdf_missing_file_raises(self, tmp_path):
        """Pointing at a non-existent PDF raises RuntimeError."""
        pytest.importorskip("pypdf", reason="pypdf not installed")
        with pytest.raises(RuntimeError, match="PDF extraction failed"):
            _extract_text(str(tmp_path / "ghost.pdf"), "pdf")

    # ── OCR fallback for scanned PDFs ──────────────────────────────────────

    def test_extract_pdf_triggers_ocr_when_text_layer_empty(self, tmp_path):
        """
        A PDF whose every page has an empty text layer must trigger the OCR
        fallback (_ocr_pdf).  We verify the dispatch logic without needing
        real OCR binaries installed by patching _ocr_pdf.
        """
        pytest.importorskip("pypdf", reason="pypdf not installed")

        # Build a minimal blank-page PDF (no text layer)
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = tmp_path / "scanned.pdf"
        with open(str(path), "wb") as f:
            writer.write(f)

        with patch("apps.knowledge_base.services._ocr_pdf", return_value="OCR result") as mock_ocr:
            result = _extract_text(str(path), "pdf")

        mock_ocr.assert_called_once_with(str(path))
        assert result == "OCR result"

    def test_extract_pdf_does_not_trigger_ocr_when_text_exists(self, tmp_path):
        """
        A PDF whose pages already have text must NOT invoke OCR —
        unnecessary OCR adds latency and may degrade quality.
        """
        pytest.importorskip("pypdf", reason="pypdf not installed")

        # Use a text-layer PDF (reportlab if available, else skip with a note)
        reportlab = pytest.importorskip("reportlab", reason="reportlab not installed — skipping no-OCR test")
        from reportlab.pdfgen import canvas as rl_canvas
        path = tmp_path / "textual.pdf"
        c = rl_canvas.Canvas(str(path))
        c.drawString(100, 700, "Hello no OCR needed")
        c.save()

        with patch("apps.knowledge_base.services._ocr_pdf") as mock_ocr:
            result = _extract_text(str(path), "pdf")

        mock_ocr.assert_not_called()
        assert "Hello no OCR needed" in result

    def test_ocr_pdf_graceful_when_libraries_missing(self, tmp_path):
        """
        When pdf2image or pytesseract is not installed, _ocr_pdf must return
        "" and log a warning instead of raising ImportError.
        """
        pytest.importorskip("pypdf", reason="pypdf not installed")
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = tmp_path / "blank.pdf"
        with open(str(path), "wb") as f:
            writer.write(f)

        # Simulate missing pdf2image
        with patch.dict("sys.modules", {"pdf2image": None, "pytesseract": None}):
            result = _ocr_pdf(str(path))

        assert result == "", "When OCR libs are absent _ocr_pdf must return empty string, not crash."

    def test_ocr_pdf_returns_text_when_available(self, tmp_path):
        """
        When OCR libraries are present, _ocr_pdf must return pytesseract's
        output.  We mock both pdf2image and pytesseract so this test runs
        without system binaries installed.
        """
        pytest.importorskip("pypdf", reason="pypdf not installed")
        import pypdf
        from unittest.mock import MagicMock

        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = tmp_path / "scanned2.pdf"
        with open(str(path), "wb") as f:
            writer.write(f)

        fake_image = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [fake_image]

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "扫描识别的文字 OCR text"

        with patch.dict("sys.modules", {
            "pdf2image": mock_pdf2image,
            "pytesseract": mock_pytesseract,
        }):
            result = _ocr_pdf(str(path))

        mock_pdf2image.convert_from_path.assert_called_once_with(str(path), dpi=200)
        mock_pytesseract.image_to_string.assert_called_once_with(
            fake_image, lang="chi_sim+eng"
        )
        assert "扫描识别的文字 OCR text" in result

    def test_ocr_pdf_uses_chi_sim_and_eng_language(self, tmp_path):
        """
        OCR must be called with lang='chi_sim+eng' to support both
        Simplified Chinese and English content in the same document.
        """
        pytest.importorskip("pypdf", reason="pypdf not installed")
        import pypdf
        from unittest.mock import MagicMock

        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = tmp_path / "lang_test.pdf"
        with open(str(path), "wb") as f:
            writer.write(f)

        fake_image = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [fake_image]
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "text"

        with patch.dict("sys.modules", {
            "pdf2image": mock_pdf2image,
            "pytesseract": mock_pytesseract,
        }):
            _ocr_pdf(str(path))

        _, kwargs = mock_pytesseract.image_to_string.call_args
        assert kwargs.get("lang") == "chi_sim+eng", (
            "Tesseract must use lang='chi_sim+eng' for Chinese+English documents."
        )

    def test_ocr_pdf_uses_200_dpi(self, tmp_path):
        """DPI=200 must be used — lower values cause recognition errors."""
        pytest.importorskip("pypdf", reason="pypdf not installed")
        import pypdf
        from unittest.mock import MagicMock

        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = tmp_path / "dpi_test.pdf"
        with open(str(path), "wb") as f:
            writer.write(f)

        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [MagicMock()]
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = ""

        with patch.dict("sys.modules", {
            "pdf2image": mock_pdf2image,
            "pytesseract": mock_pytesseract,
        }):
            _ocr_pdf(str(path))

        _, kwargs = mock_pdf2image.convert_from_path.call_args
        assert kwargs.get("dpi") == 200, "pdf2image must convert at DPI=200."


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
        # Mock returns (N, 512) shaped array matching the number of input chunks.
        # Using side_effect instead of return_value so multi-chunk documents
        # get a correctly-shaped embedding matrix — a fixed (1, 512) return_value
        # would silently truncate to 1 chunk via zip() for longer documents.
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
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

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)

        assert DocumentChunk.objects.filter(document=doc).count() >= 1

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_replaces_existing_chunks(self, mock_get_model, user, tmp_path):
        from apps.knowledge_base.models import DocumentChunk

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)
        first_count = DocumentChunk.objects.filter(document=doc).count()

        # Re-process — old chunks should be deleted first
        process_document(doc.pk)
        second_count = DocumentChunk.objects.filter(document=doc).count()
        assert second_count == first_count  # same count, not doubled

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_encode_uses_batch_size(self, mock_get_model, user, tmp_path):
        """
        model.encode() must be called with batch_size=32.

        Regression guard: without batch_size the worker encodes all chunks in a
        single forward pass, causing peak RAM to spike on large documents and
        triggering the Linux OOM killer (SIGKILL).  SIGKILL bypasses all Python
        exception handlers, leaving the document stuck at status='processing' forever.
        """
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)

        assert mock_model.encode.called, "model.encode() must be called during processing"
        _, call_kwargs = mock_model.encode.call_args
        assert call_kwargs.get("batch_size") == 32, (
            "model.encode() must be called with batch_size=32 to cap peak RAM usage. "
            "Without this, large documents can OOM-kill the Celery worker and leave "
            "the document stuck at status='processing' indefinitely."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_docx_success(self, mock_get_model, user, tmp_path):
        """
        Regression: DOCX documents must reach status='available' after processing.

        Before the fix, large DOCX files could trigger OOM kill of the Celery worker
        (because model.encode() was called without batch_size, holding all chunk
        tensors in RAM at once).  The worker being SIGKILL'd bypasses Python exception
        handlers, leaving the document stuck at status='processing' forever.

        This test exercises the full process_document() pipeline with a real DOCX file
        (created via python-docx) to catch any DOCX-specific code path regressions.
        """
        docx_mod = pytest.importorskip("docx", reason="python-docx not installed")

        # Build a minimal DOCX with paragraphs and a table
        word_doc = docx_mod.Document()
        word_doc.add_paragraph("第一段：本文件用于知识库单元测试。")
        word_doc.add_paragraph("第二段：Word 文档应当正确提取段落文本。")
        table = word_doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "表头A"
        table.cell(0, 1).text = "表头B"
        table.cell(1, 0).text = "单元格1"
        table.cell(1, 1).text = "单元格2"
        docx_path = tmp_path / "test_kb.docx"
        word_doc.save(str(docx_path))

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = Document.objects.create(
            user=user,
            name="test_kb.docx",
            original_filename="test_kb.docx",
            file_path=str(docx_path),
            file_size_bytes=docx_path.stat().st_size,
            file_type="docx",
            status="processing",
        )

        process_document(doc.pk)

        doc.refresh_from_db()
        assert doc.status == "available", (
            f"DOCX document must reach status='available', got '{doc.status}'. "
            f"error_message={doc.error_message!r}. "
            "Possible regression: DOCX extraction path not covered by process_document()."
        )
        assert doc.chunk_count >= 1, "DOCX with content must produce at least 1 chunk"
        assert doc.error_message == ""

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

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_sets_progress_100_on_success(self, mock_get_model, user, tmp_path):
        """
        On success, document.progress must be 100 and progress_message non-empty.

        This is the key fix for the frontend "always processing" bug: the frontend
        polls the document endpoint and stops when progress=100 / status=available.
        """
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)
        process_document(doc.pk)

        doc.refresh_from_db()
        assert doc.progress == 100, (
            f"progress must be 100 after success, got {doc.progress}. "
            "The frontend polls this field to decide when to stop the progress bar."
        )
        assert doc.progress_message, "progress_message must be non-empty after processing"

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_progress_written_incrementally(self, mock_get_model, user, tmp_path):
        """
        _update_progress must be called multiple times during processing, not
        just at the start and end.  This ensures the frontend progress bar
        visibly advances through intermediate stages.
        """
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        doc = self._make_doc(user, tmp_path)

        with patch("apps.knowledge_base.services._update_progress", wraps=_update_progress) as mock_prog:
            process_document(doc.pk)

        # Must have been called at least 3 times (text extraction, chunking, embedding, write)
        assert mock_prog.call_count >= 3, (
            f"_update_progress was called {mock_prog.call_count} times; "
            "expected at least 3 incremental progress updates."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_process_document_error_sets_progress_message(self, mock_get_model, user, db):
        """
        On failure, progress_message must be set to a non-empty string so the
        frontend tooltip can display useful context alongside the error tag.
        """
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
        assert doc.progress_message, (
            "progress_message must be set on error so the frontend tooltip shows "
            "context alongside the 'failed' tag."
        )


# ── search ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSearch:
    """
    Tests for search() — the semantic retrieval function.

    Embedding model is mocked; real pgvector L2Distance query is executed
    so we verify the SQL path, filtering logic, and result ordering.
    """

    # ── helpers ────────────────────────────────────────────────────────────

    def _make_available_doc(self, user, tmp_path, name="doc"):
        f = tmp_path / f"{name}.txt"
        f.write_text(f"Content of {name}", encoding="utf-8")
        return Document.objects.create(
            user=user,
            name=name,
            original_filename=f"{name}.txt",
            file_path=str(f),
            file_size_bytes=20,
            file_type="txt",
            status="available",
        )

    def _make_chunk(self, doc, index, content, embedding_vec):
        """Create a DocumentChunk with a concrete 512-dim embedding vector."""
        vec = np.array(embedding_vec, dtype="float32")
        if vec.shape != (512,):
            vec = np.resize(vec, (512,))
        return DocumentChunk.objects.create(
            document=doc,
            chunk_index=index,
            content=content,
            embedding=vec.tolist(),
        )

    # ── basic retrieval ────────────────────────────────────────────────────

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_returns_list(self, mock_get_model, user, tmp_path):
        """search() must return a list (possibly empty) without raising."""
        query_vec = np.zeros(512, dtype="float32")
        mock_model = MagicMock()
        mock_model.encode.return_value = query_vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        result = search(user.pk, "anything", top_k=3)
        assert isinstance(result, list)

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_returns_most_similar_chunk(self, mock_get_model, user, tmp_path):
        """
        Given two chunks with distinct embeddings, the chunk whose embedding
        is closest to the query vector (L2 distance) must appear first.
        """
        doc = self._make_available_doc(user, tmp_path)

        # chunk A: embedding all 1s → far from query (all 0s)
        vec_far = np.ones(512, dtype="float32")
        # chunk B: embedding all 0s → identical to query
        vec_near = np.zeros(512, dtype="float32")
        self._make_chunk(doc, 0, "far chunk",  vec_far)
        chunk_near = self._make_chunk(doc, 1, "near chunk", vec_near)

        # Query embedding = all 0s → chunk B is the nearest neighbour
        mock_model = MagicMock()
        mock_model.encode.return_value = vec_near.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "test query", top_k=5)
        assert len(results) >= 1
        assert results[0].pk == chunk_near.pk, (
            "The chunk closest to the query vector must be returned first."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_respects_top_k(self, mock_get_model, user, tmp_path):
        """search() must return at most top_k results."""
        doc = self._make_available_doc(user, tmp_path)
        for i in range(5):
            vec = np.full(512, float(i), dtype="float32")
            self._make_chunk(doc, i, f"chunk {i}", vec)

        query_vec = np.zeros(512, dtype="float32")
        mock_model = MagicMock()
        mock_model.encode.return_value = query_vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "query", top_k=2)
        assert len(results) <= 2

    # ── filtering: only own user's available documents ─────────────────────

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_excludes_other_users_chunks(self, mock_get_model, user, user2, tmp_path):
        """
        Chunks belonging to a different user must never appear in search results.
        """
        doc_user1 = self._make_available_doc(user,  tmp_path, name="doc1")
        doc_user2 = self._make_available_doc(user2, tmp_path, name="doc2")

        vec = np.zeros(512, dtype="float32")
        self._make_chunk(doc_user1, 0, "user1 private chunk", vec)
        self._make_chunk(doc_user2, 0, "user2 private chunk", vec)

        mock_model = MagicMock()
        mock_model.encode.return_value = vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results_user1 = search(user.pk, "query", top_k=10)
        content_list = [r.content for r in results_user1]

        assert "user1 private chunk" in content_list
        assert "user2 private chunk" not in content_list, (
            "search() must not return chunks belonging to a different user."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_excludes_processing_documents(self, mock_get_model, user, tmp_path):
        """
        Chunks from documents still being processed (status != 'available')
        must not appear in search results.
        """
        # Create an available doc with a chunk
        doc_ok = self._make_available_doc(user, tmp_path, name="ok")
        vec = np.zeros(512, dtype="float32")
        self._make_chunk(doc_ok, 0, "available chunk", vec)

        # Create a processing doc with a chunk
        f = tmp_path / "proc.txt"
        f.write_text("processing content", encoding="utf-8")
        doc_proc = Document.objects.create(
            user=user, name="proc", original_filename="proc.txt",
            file_path=str(f), file_size_bytes=18, file_type="txt",
            status="processing",
        )
        self._make_chunk(doc_proc, 0, "processing chunk", vec)

        mock_model = MagicMock()
        mock_model.encode.return_value = vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "query", top_k=10)
        content_list = [r.content for r in results]

        assert "available chunk" in content_list
        assert "processing chunk" not in content_list, (
            "search() must filter out chunks from non-available documents."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_returns_empty_when_no_docs(self, mock_get_model, user, db):
        """search() for a user with no documents must return an empty list."""
        vec = np.zeros(512, dtype="float32")
        mock_model = MagicMock()
        mock_model.encode.return_value = vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "anything", top_k=3)
        assert results == []

    # ── content of returned objects ────────────────────────────────────────

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_result_has_content_field(self, mock_get_model, user, tmp_path):
        """Each result must expose a .content attribute with the chunk text."""
        doc = self._make_available_doc(user, tmp_path)
        vec = np.zeros(512, dtype="float32")
        self._make_chunk(doc, 0, "expected chunk text", vec)

        mock_model = MagicMock()
        mock_model.encode.return_value = vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "query", top_k=1)
        assert results
        assert results[0].content == "expected chunk text"

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_result_has_document_id(self, mock_get_model, user, tmp_path):
        """Each result must expose a .document_id so callers can cite the source."""
        doc = self._make_available_doc(user, tmp_path)
        vec = np.zeros(512, dtype="float32")
        chunk = self._make_chunk(doc, 0, "cited chunk", vec)

        mock_model = MagicMock()
        mock_model.encode.return_value = vec.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "query", top_k=1)
        assert results
        assert results[0].document_id == doc.pk

    # ── hybrid search: anchor chunk injection ─────────────────────────────────

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_anchor_chunk_always_included(self, mock_get_model, user, tmp_path):
        """
        Regression: chunk_index=0 of any document that scores a semantic hit
        must always appear in results, even if it is semantically distant from
        the query.

        This is the "community name" scenario:
          - chunk 0 contains the document title / named entities (e.g. community
            name "红枫岭枫和苑") — semantically distant from the query topic
          - chunk 1 is about voting rules — semantically close to the query
          - Pure semantic search would only return chunk 1 and miss the name.
          - With anchor injection, chunk 0 is always included alongside chunk 1.
        """
        doc = self._make_available_doc(user, tmp_path)

        # chunk 0: document header with community name — embedding all 1s (far)
        vec_far  = np.ones(512,  dtype="float32")
        # chunk 1: voting rules — embedding all 0s (identical to query → nearest)
        vec_near = np.zeros(512, dtype="float32")
        anchor_chunk  = self._make_chunk(doc, 0, "红枫岭枫和苑小区议事规则总则", vec_far)
        content_chunk = self._make_chunk(doc, 1, "业主大会投票权数计算方法",       vec_near)

        # Query embedding = all 0s → only chunk 1 would be returned by pure semantic
        mock_model = MagicMock()
        mock_model.encode.return_value = vec_near.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "业主大会投票权数", top_k=1)
        result_pks = {r.pk for r in results}

        assert content_chunk.pk in result_pks, (
            "The nearest semantic chunk (voting rules) must always be returned."
        )
        assert anchor_chunk.pk in result_pks, (
            "chunk_index=0 (document header with community name) must be injected "
            "even when it is semantically distant from the query (anchor injection)."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_keyword_fallback_finds_exact_term_chunk(self, mock_get_model, user, tmp_path):
        """
        Keyword fallback must surface chunks that contain query terms verbatim
        even when those chunks are far from the query embedding.

        Scenario: the query explicitly mentions "车位" (parking space).
        One chunk is semantically close but doesn't contain the word "车位".
        Another chunk is semantically distant but does contain "车位".
        The keyword chunk must appear in the merged results.
        """
        doc = self._make_available_doc(user, tmp_path)

        vec_near = np.zeros(512, dtype="float32")
        vec_far  = np.ones(512,  dtype="float32")
        # index 1: near but does NOT mention 车位
        sem_chunk = self._make_chunk(doc, 1, "投票权数的一般性规定", vec_near)
        # index 2: far but DOES mention 车位 — keyword fallback must rescue this
        kw_chunk  = self._make_chunk(doc, 2, "车位面积不计入业主投票权数", vec_far)

        mock_model = MagicMock()
        mock_model.encode.return_value = vec_near.reshape(1, 512)
        mock_get_model.return_value = mock_model

        results = search(user.pk, "车位是否计入投票权数", top_k=2)
        result_pks = {r.pk for r in results}

        assert kw_chunk.pk in result_pks, (
            "Chunk containing the query keyword '车位' must be returned via "
            "keyword fallback even when its embedding is semantically distant."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_extract_cn_keywords_returns_chinese_ngrams(self, mock_get_model, user):
        """_extract_cn_keywords() must return multi-char Chinese ngrams."""
        from apps.knowledge_base.services import _extract_cn_keywords
        kws = _extract_cn_keywords("业主大会中车位是否计入投票权数")
        # Must contain at least some 2-char and 4-char Chinese terms
        assert any(len(k) == 4 for k in kws), "Expected 4-char ngrams"
        assert any(len(k) == 2 for k in kws), "Expected 2-char ngrams"
        # The specific terms important for the community-name scenario
        assert "车位" in kws
        assert "业主大会" in kws


# ── VectorField dimension smoke test ─────────────────────────────────────────

class TestVectorFieldDimension:
    """
    Smoke test: DocumentChunk.embedding VectorField dimensions must match the
    embedding model output dimension (512 for bge-small-zh-v1.5).

    Regression guard for SD-L011 / be2ab07: when the model was switched from
    bge-m3 (1024-dim) to bge-small-zh-v1.5 (512-dim), a mismatch between the
    VectorField declaration and the model output would cause pgvector to reject
    bulk_create() inserts with a dimension error.  This test catches the mismatch
    at import time (no DB required) so any future model change that forgets to
    update the VectorField is immediately surfaced.

    Rule: whenever EMBEDDING_MODEL or its output dimension changes, ALL of the
    following must be updated in the same commit:
      1. VectorField(dimensions=N) in models.py
      2. A new migration to ALTER the column type
      3. This test's expected dimension constant
      4. All mock arrays: np.zeros((len(texts), N), ...)
    """

    EXPECTED_DIM = 512  # bge-small-zh-v1.5 output dimension

    def test_vector_field_dimension_matches_embedding_model(self):
        """
        DocumentChunk.embedding must declare dimensions=512, matching
        bge-small-zh-v1.5 output.  Update EXPECTED_DIM here if the model changes
        (and remember to also create a migration + update mock arrays).
        """
        from apps.knowledge_base.models import DocumentChunk
        field = DocumentChunk._meta.get_field("embedding")
        assert field.dimensions == self.EXPECTED_DIM, (
            f"DocumentChunk.embedding VectorField has dimensions={field.dimensions}, "
            f"expected {self.EXPECTED_DIM} (bge-small-zh-v1.5 output). "
            "If you changed the embedding model, also update: "
            "(1) VectorField(dimensions=N) in models.py, "
            "(2) create a migration, "
            "(3) update EXPECTED_DIM in this test, "
            "(4) update all mock arrays to np.zeros((len(texts), N))."
        )
