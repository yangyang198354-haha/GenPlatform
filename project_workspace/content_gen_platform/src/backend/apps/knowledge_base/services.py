"""Knowledge base processing: chunking, embedding, and RAG retrieval."""
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List

from django.conf import settings
from pgvector.django import L2Distance

from .models import Document, DocumentChunk

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Lazy-loaded singleton embedding model
_embedding_model: "SentenceTransformer | None" = None


def _get_embedding_model() -> "SentenceTransformer":
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(
            settings.EMBEDDING_MODEL, device=settings.EMBEDDING_DEVICE
        )
    return _embedding_model


def _ocr_pdf(file_path: str) -> str:
    """
    OCR fallback for scanned PDFs (no embedded text layer).

    Converts each PDF page to a raster image via pdf2image (wraps poppler),
    then runs pytesseract to extract text.  Both libraries must be installed
    AND the corresponding system binaries must be present:
      - poppler-utils  (for pdf2image / pdftoppm)
      - tesseract-ocr + tesseract-ocr-chi-sim + tesseract-ocr-eng
        (for pytesseract)

    If either library is missing the function logs a warning and returns ""
    so the caller can surface a meaningful empty result rather than crashing.
    """
    try:
        from pdf2image import convert_from_path   # noqa: PLC0415
        import pytesseract                        # noqa: PLC0415
    except ImportError as exc:
        logger.warning(
            "OCR unavailable for scanned PDF '%s': %s — "
            "install pdf2image, pytesseract, and system packages "
            "poppler-utils + tesseract-ocr + tesseract-ocr-chi-sim",
            file_path, exc,
        )
        return ""

    try:
        # DPI=200: good balance between accuracy and memory for A4 pages.
        # lang="chi_sim+eng": mixed Chinese/English documents are common.
        images = convert_from_path(file_path, dpi=200)
        texts = [
            pytesseract.image_to_string(img, lang="chi_sim+eng")
            for img in images
        ]
        return "\n".join(t for t in texts if t.strip())
    except Exception as exc:
        raise RuntimeError(f"PDF OCR failed: {exc}") from exc


def _extract_text(file_path: str, file_type: str) -> str:
    """Extract plain text from a document file.

    For PDF files the extraction is two-stage:
      1. Try pypdf's text-layer extraction (fast, zero extra dependencies).
      2. If every page returns empty text (i.e. the file is a scanned /
         image-only PDF), fall back to OCR via pdf2image + pytesseract.
    """
    path = Path(file_path)
    if file_type == "txt" or file_type == "md":
        return path.read_text(encoding="utf-8", errors="replace")

    if file_type == "pdf":
        try:
            import pypdf  # noqa: PLC0415
            reader = pypdf.PdfReader(str(path))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages_text)

            # If all pages have no text it is almost certainly a scanned PDF.
            # Fall back to OCR so users get content instead of an empty chunk.
            if not text.strip():
                logger.info(
                    "PDF '%s' has no embedded text layer — falling back to OCR",
                    file_path,
                )
                text = _ocr_pdf(file_path)

            return text
        except Exception as e:
            raise RuntimeError(f"PDF extraction failed: {e}") from e

    if file_type == "docx":
        try:
            import docx  # noqa: PLC0415
            doc = docx.Document(str(path))
            texts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            texts.append(cell.text)
            return "\n".join(texts)
        except Exception as e:
            raise RuntimeError(f"DOCX extraction failed: {e}") from e

    raise ValueError(f"Unsupported file type: {file_type}")


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks by character count."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


def process_document(document_id: int) -> None:
    """
    Celery task body: extract text → chunk → embed → store in pgvector.
    Marks document status as 'available' on success, 'error' on failure.
    """
    try:
        doc = Document.objects.get(pk=document_id)
        doc.status = "processing"
        doc.save(update_fields=["status"])

        text = _extract_text(doc.file_path, doc.file_type)
        chunks = _chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

        model = _get_embedding_model()
        embeddings = model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)

        # Delete existing chunks (re-processing case)
        DocumentChunk.objects.filter(document=doc).delete()

        chunk_objects = [
            DocumentChunk(
                document=doc,
                chunk_index=i,
                content=chunk,
                embedding=embedding.tolist(),
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        DocumentChunk.objects.bulk_create(chunk_objects)

        doc.status = "available"
        doc.chunk_count = len(chunk_objects)
        doc.error_message = ""
        doc.save(update_fields=["status", "chunk_count", "error_message"])
        logger.info("Document %d processed: %d chunks", document_id, len(chunk_objects))

    except Document.DoesNotExist:
        logger.error("Document %d not found", document_id)
    except Exception as e:
        logger.exception("Document %d processing failed", document_id)
        Document.objects.filter(pk=document_id).update(status="error", error_message=str(e))


def search(user_id: int, query: str, top_k: int = 3) -> List[DocumentChunk]:
    """
    Semantic search in a user's knowledge base.
    Returns top_k most similar chunks ordered by L2 distance.
    """
    model = _get_embedding_model()
    query_embedding = model.encode([query], normalize_embeddings=True)[0].tolist()

    chunks = (
        DocumentChunk.objects.filter(
            document__user_id=user_id,
            document__status="available",
        )
        .annotate(distance=L2Distance("embedding", query_embedding))
        .order_by("distance")[:top_k]
    )
    return list(chunks)
