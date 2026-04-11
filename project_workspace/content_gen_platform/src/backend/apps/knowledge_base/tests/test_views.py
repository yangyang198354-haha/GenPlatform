"""Integration tests for knowledge_base API views."""
import io
import os
import pytest
from unittest.mock import patch
from rest_framework import status
from apps.knowledge_base.models import Document

DOCS_URL = "/api/v1/knowledge/documents/"


def _make_url(pk):
    return f"{DOCS_URL}{pk}/"


def _fake_file(name="test.txt", content=b"Hello world", size=None):
    f = io.BytesIO(content)
    f.name = name
    f.size = size if size is not None else len(content)
    return f


@pytest.mark.django_db
class TestDocumentListCreateView:
    @patch("apps.knowledge_base.views.process_document_task")
    def test_upload_success(self, mock_task, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        f = _fake_file("doc.txt", b"some content")
        resp = client.post(DOCS_URL, {"file": f}, format="multipart")

        assert resp.status_code == status.HTTP_201_CREATED
        assert Document.objects.filter(user=user).count() == 1
        assert resp.data["status"] == "processing"
        mock_task.delay.assert_called_once()

    def test_upload_no_file(self, auth_client):
        client, _ = auth_client
        resp = client.post(DOCS_URL, {}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "文件不能为空" in resp.data["error"]

    def test_upload_invalid_extension(self, auth_client, settings):
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        client, _ = auth_client
        f = _fake_file("script.exe", b"binary")
        resp = client.post(DOCS_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "不支持的文件格式" in resp.data["error"]

    def test_upload_file_too_large(self, auth_client, settings):
        settings.MAX_DOCUMENT_SIZE_BYTES = 100  # 100 bytes limit
        client, _ = auth_client
        f = _fake_file("big.txt", b"x" * 101)
        resp = client.post(DOCS_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "50MB" in resp.data["error"]

    def test_upload_quota_exceeded(self, auth_client, user, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        # Fill quota
        user.used_storage_bytes = user.storage_quota_bytes
        user.save()

        client, _ = auth_client
        f = _fake_file("doc.txt", b"some content")
        resp = client.post(DOCS_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "存储空间不足" in resp.data["error"]

    @patch("apps.knowledge_base.views.process_document_task")
    def test_list_documents_own_only(self, mock_task, auth_client, auth_client2, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client1, user1 = auth_client
        client2, user2 = auth_client2

        # user1 uploads a file
        client1.post(DOCS_URL, {"file": _fake_file("a.txt", b"aaa")}, format="multipart")
        # user2 uploads a file
        client2.post(DOCS_URL, {"file": _fake_file("b.txt", b"bbb")}, format="multipart")

        # user1 should only see their own doc
        resp = client1.get(DOCS_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]["original_filename"] == "a.txt"

    @patch("apps.knowledge_base.views.process_document_task")
    def test_search_documents(self, mock_task, auth_client, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, _ = auth_client
        client.post(DOCS_URL, {"file": _fake_file("alpha.txt", b"aaa"), "name": "alpha report"}, format="multipart")
        client.post(DOCS_URL, {"file": _fake_file("beta.txt", b"bbb"), "name": "beta report"}, format="multipart")

        resp = client.get(DOCS_URL + "?search=alpha")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert "alpha" in resp.data[0]["name"]

    def test_list_unauthenticated(self, api_client):
        resp = api_client.get(DOCS_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestDocumentDetailView:
    def _create_doc(self, user, tmp_path, settings):
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        f = tmp_path / "sample.txt"
        f.write_text("hello", encoding="utf-8")
        return Document.objects.create(
            user=user,
            name="sample",
            original_filename="sample.txt",
            file_path=str(f),
            file_size_bytes=5,
            file_type="txt",
            status="available",
        )

    def test_rename_document(self, auth_client, tmp_path, settings):
        client, user = auth_client
        settings.MEDIA_ROOT = str(tmp_path)
        doc = self._create_doc(user, tmp_path, settings)
        resp = client.patch(_make_url(doc.pk), {"name": "renamed"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        doc.refresh_from_db()
        assert doc.name == "renamed"

    def test_delete_document_releases_quota(self, auth_client, tmp_path, settings):
        client, user = auth_client
        settings.MEDIA_ROOT = str(tmp_path)
        doc = self._create_doc(user, tmp_path, settings)
        user.consume_storage(doc.file_size_bytes)

        resp = client.delete(_make_url(doc.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        user.refresh_from_db()
        assert user.used_storage_bytes == 0
        assert not Document.objects.filter(pk=doc.pk).exists()

    def test_delete_removes_file(self, auth_client, tmp_path, settings):
        client, user = auth_client
        settings.MEDIA_ROOT = str(tmp_path)
        doc = self._create_doc(user, tmp_path, settings)
        file_path = doc.file_path

        client.delete(_make_url(doc.pk))
        assert not os.path.exists(file_path)

    def test_other_user_cannot_access(self, auth_client2, auth_client, tmp_path, settings):
        _, user1 = auth_client
        client2, _ = auth_client2
        settings.MEDIA_ROOT = str(tmp_path)
        doc = self._create_doc(user1, tmp_path, settings)

        resp = client2.get(_make_url(doc.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_other_user_cannot_delete(self, auth_client2, auth_client, tmp_path, settings):
        _, user1 = auth_client
        client2, _ = auth_client2
        settings.MEDIA_ROOT = str(tmp_path)
        doc = self._create_doc(user1, tmp_path, settings)

        resp = client2.delete(_make_url(doc.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert Document.objects.filter(pk=doc.pk).exists()


# ── End-to-end chain: upload → Celery task → DocumentChunks in DB ─────────

@pytest.mark.django_db
class TestUploadToVectorChainIntegration:
    """
    Full pipeline integration test:
        POST /api/v1/knowledge/documents/
            → Document created (status=processing)
            → process_document_task fired (ALWAYS_EAGER → runs synchronously)
            → _extract_text called on the uploaded file
            → _chunk_text splits the text
            → _get_embedding_model mock returns 512-dim vectors
            → DocumentChunk rows bulk-created in the database
            → Document status updated to 'available'

    This test is the only one that verifies the COMPLETE chain without
    mocking the Celery task itself.  All previous tests either mock the
    task or test individual services in isolation.
    """

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_upload_txt_creates_chunks_in_db(self, mock_get_model, auth_client, settings, tmp_path):
        """
        Uploading a .txt file triggers Celery (ALWAYS_EAGER), which runs
        process_document() synchronously.  After the request returns,
        DocumentChunk rows must exist in the database.
        """
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        # encode() is called with a list of chunk strings; return one 512-dim
        # vector per chunk (shape = [n_chunks, 512])
        def fake_encode(texts, **kwargs):
            return np.zeros((len(texts), 512), dtype="float32")
        mock_model.encode.side_effect = fake_encode
        mock_get_model.return_value = mock_model

        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        content = b"This is a test document with enough words to produce at least one chunk."
        f = io.BytesIO(content)
        f.name = "chain_test.txt"
        f.size = len(content)

        resp = client.post(DOCS_URL, {"file": f}, format="multipart")

        assert resp.status_code == status.HTTP_201_CREATED
        doc_id = resp.data["id"]

        # After CELERY_TASK_ALWAYS_EAGER the task has already run
        doc = Document.objects.get(pk=doc_id)
        assert doc.status == "available", (
            f"Expected status='available' after eager task, got '{doc.status}'. "
            f"error_message={doc.error_message!r}"
        )
        assert doc.chunk_count >= 1

        from apps.knowledge_base.models import DocumentChunk
        chunks = DocumentChunk.objects.filter(document=doc)
        assert chunks.exists(), "At least one DocumentChunk must be created after processing."
        assert chunks.count() == doc.chunk_count

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_upload_md_creates_chunks_in_db(self, mock_get_model, auth_client, settings, tmp_path):
        """Markdown file upload goes through the full chain successfully."""
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, _ = auth_client
        content = b"# Title\n\nThis is markdown content with **bold** and _italic_ text."
        f = io.BytesIO(content)
        f.name = "readme.md"
        f.size = len(content)

        resp = client.post(DOCS_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED

        doc = Document.objects.get(pk=resp.data["id"])
        assert doc.status == "available"

        from apps.knowledge_base.models import DocumentChunk
        assert DocumentChunk.objects.filter(document=doc).exists()

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_uploaded_chunks_have_correct_embedding_dimension(
        self, mock_get_model, auth_client, settings, tmp_path
    ):
        """
        Regression for be2ab07: after migrating from bge-m3 (1024-dim) to
        bge-small-zh-v1.5 (512-dim), stored embeddings must be 512-dimensional.
        """
        import numpy as np
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
        mock_get_model.return_value = mock_model

        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, _ = auth_client
        content = b"Dimension regression test content for pgvector chunk storage."
        f = io.BytesIO(content)
        f.name = "dim_test.txt"
        f.size = len(content)

        resp = client.post(DOCS_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED

        from apps.knowledge_base.models import DocumentChunk
        chunk = DocumentChunk.objects.filter(
            document_id=resp.data["id"]
        ).first()
        assert chunk is not None
        assert len(chunk.embedding) == 512, (
            f"Expected 512-dim embedding (bge-small-zh-v1.5), got {len(chunk.embedding)}. "
            "Possible regression of be2ab07."
        )

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_chain_after_upload_then_search_returns_chunk(
        self, mock_get_model, auth_client, settings, tmp_path
    ):
        """
        Full round-trip: upload → process → search.
        After a document is processed the search() function must be able
        to find its chunks via vector similarity.
        """
        import numpy as np
        from unittest.mock import MagicMock
        from apps.knowledge_base.services import search

        # Fixed vector so both storage and query use the same direction
        fixed_vec = np.ones(512, dtype="float32") * 0.5

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.tile(fixed_vec, (len(texts), 1))
        mock_get_model.return_value = mock_model

        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        content = b"Unique searchable content about knowledge retrieval."
        f = io.BytesIO(content)
        f.name = "search_test.txt"
        f.size = len(content)

        resp = client.post(DOCS_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED

        doc = Document.objects.get(pk=resp.data["id"])
        assert doc.status == "available"

        # Now search — mock returns the same vector for the query
        results = search(user.pk, "knowledge retrieval", top_k=3)
        assert results, "search() must find at least one chunk after the document was processed."
        assert any("knowledge" in r.content.lower() or "retrieval" in r.content.lower()
                   for r in results)
