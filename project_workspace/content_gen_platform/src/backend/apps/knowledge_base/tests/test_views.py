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
