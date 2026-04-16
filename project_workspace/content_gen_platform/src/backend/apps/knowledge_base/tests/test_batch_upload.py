"""
Tests for the new KB features:
  - F-01: Directory / batch upload (DocumentBatchUploadView)
  - F-02: User isolation (cross-user access controls)
  - F-03: Default filename naming + rename (PATCH)

Covered user stories: US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-008
"""
import io
import json
import pytest
from unittest.mock import patch
from rest_framework import status
from apps.knowledge_base.models import Document

DOCS_URL = "/api/v1/knowledge/documents/"
BATCH_URL = "/api/v1/knowledge/documents/batch-upload/"


def _make_url(pk):
    return f"{DOCS_URL}{pk}/"


def _fake_file(name="test.txt", content=b"Hello world", size=None):
    f = io.BytesIO(content)
    f.name = name
    f.size = size if size is not None else len(content)
    return f


# ═══════════════════════════════════════════════════════════════════════════════
# F-01: Batch upload — DocumentBatchUploadView
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDocumentBatchUploadView:
    """US-001, US-002, US-003 — batch upload endpoint."""

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_success_creates_documents(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-001 Scenario 1: 成功上传含嵌套子目录的目录
        Three supported files → 3 Document rows, status=processing, 3 tasks fired.
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        files = [
            _fake_file("doc1.pdf", b"pdf content"),
            _fake_file("doc2.docx", b"docx content"),
            _fake_file("doc3.txt", b"txt content"),
        ]
        rel_paths = ["root/doc1.pdf", "root/sub/doc2.docx", "root/sub/sub2/doc3.txt"]

        resp = client.post(
            BATCH_URL,
            data={
                "files": files,
                "relative_paths": json.dumps(rel_paths),
            },
            format="multipart",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data["accepted"]) == 3
        assert len(resp.data["skipped"]) == 0
        assert len(resp.data["rejected"]) == 0
        assert resp.data["quota_exhausted"] is False
        assert Document.objects.filter(user=user).count() == 3
        assert mock_task.delay.call_count == 3
        for doc in Document.objects.filter(user=user):
            assert doc.status == "processing"

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_skips_unsupported_formats(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-001 Scenario 2: 目录中含不支持格式文件时跳过
        report.pdf is accepted; image.jpg and script.exe are skipped.
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        files = [
            _fake_file("report.pdf", b"pdf content"),
            _fake_file("image.jpg", b"jpg data"),
            _fake_file("script.exe", b"binary"),
        ]
        resp = client.post(BATCH_URL, data={"files": files}, format="multipart")

        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data["accepted"]) == 1
        assert len(resp.data["skipped"]) == 2
        skipped_names = {s["name"] for s in resp.data["skipped"]}
        assert skipped_names == {"image.jpg", "script.exe"}
        assert all(s["reason"] == "format_not_supported" for s in resp.data["skipped"])
        assert Document.objects.filter(user=user).count() == 1
        mock_task.delay.assert_called_once()

    def test_batch_upload_no_supported_files_returns_400(self, auth_client, settings):
        """
        US-001 Scenario 3: 目录中无受支持文件 → HTTP 400
        """
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        client, _ = auth_client
        files = [_fake_file("photo.png", b"png"), _fake_file("data.xlsx", b"xlsx")]
        resp = client.post(BATCH_URL, data={"files": files}, format="multipart")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "未包含受支持的文档" in resp.data["error"]

    def test_batch_upload_no_files_returns_400(self, auth_client):
        """Empty request body → HTTP 400."""
        client, _ = auth_client
        resp = client.post(BATCH_URL, data={}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_unauthenticated_returns_401(self, mock_task, api_client, settings):
        """Unauthenticated request → 401."""
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        files = [_fake_file("doc.txt", b"hello")]
        resp = api_client.post(BATCH_URL, data={"files": files}, format="multipart")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_rejects_oversized_file(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-003 Scenario 1: 单个文件超过 50MB 被跳过，其余正常入库
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 100  # 100 bytes limit for test speed

        client, user = auth_client
        small = _fake_file("small.txt", b"x" * 10)
        large = _fake_file("large.pdf", b"y" * 200)  # exceeds 100-byte limit

        resp = client.post(
            BATCH_URL,
            data={"files": [small, large]},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data["accepted"]) == 1
        assert resp.data["accepted"][0]["name"] == "small.txt"
        assert len(resp.data["rejected"]) == 1
        assert resp.data["rejected"][0]["name"] == "large.pdf"
        assert resp.data["rejected"][0]["reason"] == "file_too_large"
        assert Document.objects.filter(user=user).count() == 1
        mock_task.delay.assert_called_once()

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_stops_on_quota_exhausted(
        self, mock_task, auth_client, user, settings, tmp_path
    ):
        """
        US-003 Scenario 2: 配额不足时优先入库已遍历到的文件，超出后停止
        quota = 5 bytes; files are 3+3+1 bytes → only first 3-byte file fits.
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        # Set a tiny quota for the test
        user.storage_quota_bytes = 5
        user.used_storage_bytes = 0
        user.save()

        client, _ = auth_client

        a = _fake_file("a.txt", b"aaa")   # 3 bytes
        b = _fake_file("b.txt", b"bbb")   # 3 bytes — quota exhausted after a
        c = _fake_file("c.txt", b"c")     # 1 byte  — never reaches this

        resp = client.post(
            BATCH_URL,
            data={"files": [a, b, c]},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data["accepted"]) == 1
        assert resp.data["accepted"][0]["name"] == "a.txt"
        assert resp.data["quota_exhausted"] is True

        quota_rejected = [r for r in resp.data["rejected"] if r["reason"] == "quota_exceeded"]
        assert len(quota_rejected) == 2  # b.txt and c.txt

        assert Document.objects.filter(user=user).count() == 1

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_filename_from_relative_path(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-002 Scenario 2: 嵌套路径中的文件名正确提取（仅纯文件名，不含路径）
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        f = _fake_file("report.pdf", b"data")
        resp = client.post(
            BATCH_URL,
            data={
                "files": [f],
                "relative_paths": json.dumps(["root/docs/2024/report.pdf"]),
            },
            format="multipart",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        doc = Document.objects.get(user=user)
        assert doc.name == "report.pdf"               # US-002: pure filename, no path
        assert doc.original_filename == "report.pdf"

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_default_name_equals_filename(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-002 Scenario 1: 批量上传后文档名默认为文件名
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        files = [
            _fake_file("annual_report.pdf", b"pdf"),
            _fake_file("meeting_notes.docx", b"docx"),
        ]
        rel_paths = ["root/annual_report.pdf", "root/meeting_notes.docx"]

        resp = client.post(
            BATCH_URL,
            data={"files": files, "relative_paths": json.dumps(rel_paths)},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        docs = {d.original_filename: d for d in Document.objects.filter(user=user)}
        assert docs["annual_report.pdf"].name == "annual_report.pdf"
        assert docs["meeting_notes.docx"].name == "meeting_notes.docx"
        for doc in docs.values():
            assert doc.name == doc.original_filename

    @patch("apps.knowledge_base.views.process_document_task")
    def test_batch_upload_summary_text(self, mock_task, auth_client, settings, tmp_path):
        """Response summary string is non-empty and informative."""
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, _ = auth_client
        files = [_fake_file("ok.txt", b"ok"), _fake_file("skip.jpg", b"jpg")]
        resp = client.post(BATCH_URL, data={"files": files}, format="multipart")

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["summary"]  # non-empty
        assert len(resp.data["summary"]) > 5


# ═══════════════════════════════════════════════════════════════════════════════
# F-02: User isolation — cross-user access control
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserIsolation:
    """US-004, US-005, US-006 — all KB operations respect user boundaries."""

    def _create_doc(self, user, tmp_path):
        """Helper: directly create a Document for a given user."""
        f = tmp_path / f"doc_{user.pk}.txt"
        f.write_text("content", encoding="utf-8")
        return Document.objects.create(
            user=user,
            name="isolation_test_doc",
            original_filename=f.name,
            file_path=str(f),
            file_size_bytes=7,
            file_type="txt",
            status="available",
        )

    def test_list_returns_only_own_documents(
        self, auth_client, auth_client2, tmp_path
    ):
        """
        US-004 Scenario 1: 文档列表只返回当前用户的文档
        """
        client1, user1 = auth_client
        _, user2 = auth_client2

        self._create_doc(user1, tmp_path)
        self._create_doc(user2, tmp_path)

        resp = client1.get(DOCS_URL)
        assert resp.status_code == status.HTTP_200_OK
        ids = [d["id"] for d in (resp.data.get("results") or resp.data)]
        user1_ids = set(Document.objects.filter(user=user1).values_list("pk", flat=True))
        user2_ids = set(Document.objects.filter(user=user2).values_list("pk", flat=True))
        assert all(i in user1_ids for i in ids)
        assert not any(i in user2_ids for i in ids)

    def test_unauthenticated_list_returns_401(self, api_client):
        """US-004 Scenario 2: 未认证请求 → 401"""
        resp = api_client.get(DOCS_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_other_user_cannot_get_document(
        self, auth_client, auth_client2, tmp_path
    ):
        """
        US-005 Scenario 1: 访问他人文档详情返回 404（不暴露资源存在）
        """
        _, user1 = auth_client
        client2, _ = auth_client2
        doc = self._create_doc(user1, tmp_path)

        resp = client2.get(_make_url(doc.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_other_user_cannot_delete_document(
        self, auth_client, auth_client2, tmp_path
    ):
        """
        US-005 Scenario 2: 尝试删除他人文档返回 404，文档仍然存在
        """
        _, user1 = auth_client
        client2, _ = auth_client2
        doc = self._create_doc(user1, tmp_path)

        resp = client2.delete(_make_url(doc.pk))
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert Document.objects.filter(pk=doc.pk).exists()

    def test_other_user_cannot_rename_document(
        self, auth_client, auth_client2, tmp_path
    ):
        """
        US-005 Scenario 3 / US-008 Scenario 3:
        尝试重命名他人文档返回 404，name 未改变
        """
        _, user1 = auth_client
        client2, _ = auth_client2
        doc = self._create_doc(user1, tmp_path)
        original_name = doc.name

        resp = client2.patch(_make_url(doc.pk), {"name": "hacked"}, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        doc.refresh_from_db()
        assert doc.name == original_name

    def test_batch_upload_isolates_to_requesting_user(
        self, auth_client, auth_client2, settings, tmp_path
    ):
        """
        Batch-uploaded documents belong exclusively to the uploading user.
        The other user's list must not contain them.
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client1, user1 = auth_client
        client2, user2 = auth_client2

        with patch("apps.knowledge_base.views.process_document_task"):
            client1.post(
                BATCH_URL,
                data={"files": [_fake_file("user1_doc.txt", b"data")]},
                format="multipart",
            )

        # user2 list must be empty
        resp = client2.get(DOCS_URL)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data.get("results") or resp.data
        assert len(data) == 0

        # user1 list must have exactly one document
        resp1 = client1.get(DOCS_URL)
        data1 = resp1.data.get("results") or resp1.data
        assert len(data1) == 1
        assert data1[0]["original_filename"] == "user1_doc.txt"


# ═══════════════════════════════════════════════════════════════════════════════
# F-03: Default filename naming + rename
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFilenameDefaultAndRename:
    """US-007, US-008 — single-file upload naming and PATCH rename."""

    @patch("apps.knowledge_base.views.process_document_task")
    def test_single_upload_default_name_is_filename(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-007 Scenario 1: 不填写标题时 name 默认为文件名
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        f = _fake_file("financial_report.pdf", b"data")
        resp = client.post(DOCS_URL, {"file": f}, format="multipart")

        assert resp.status_code == status.HTTP_201_CREATED
        doc = Document.objects.get(pk=resp.data["id"])
        assert doc.name == "financial_report.pdf"
        assert doc.original_filename == "financial_report.pdf"

    @patch("apps.knowledge_base.views.process_document_task")
    def test_single_upload_custom_title_overrides_filename(
        self, mock_task, auth_client, settings, tmp_path
    ):
        """
        US-007 Scenario 2: 填写标题时 name 使用用户输入
        """
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        client, user = auth_client
        f = _fake_file("financial_report.pdf", b"data")
        resp = client.post(
            DOCS_URL,
            {"file": f, "name": "2024财报"},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        doc = Document.objects.get(pk=resp.data["id"])
        assert doc.name == "2024财报"
        assert doc.original_filename == "financial_report.pdf"

    def test_rename_own_document_succeeds(self, auth_client, tmp_path, settings):
        """
        US-008 Scenario 1: 成功重命名自己的文档
        """
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        client, user = auth_client

        f = tmp_path / "sample.txt"
        f.write_text("hello", encoding="utf-8")
        doc = Document.objects.create(
            user=user,
            name="旧名称",
            original_filename="sample.txt",
            file_path=str(f),
            file_size_bytes=5,
            file_type="txt",
            status="available",
        )
        original_filename_before = doc.original_filename
        original_chunk_count = doc.chunk_count

        resp = client.patch(
            _make_url(doc.pk),
            {"name": "新名称"},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        doc.refresh_from_db()
        assert doc.name == "新名称"
        # original_filename must NOT change (REQ-NFUNC-002)
        assert doc.original_filename == original_filename_before
        # chunk_count must NOT change
        assert doc.chunk_count == original_chunk_count
        assert resp.data["name"] == "新名称"
        assert resp.data["original_filename"] == original_filename_before

    def test_rename_cannot_change_readonly_fields(self, auth_client, tmp_path, settings):
        """
        REQ-NFUNC-002: PATCH cannot change file_path, original_filename, file_type.
        These fields are in read_only_fields and must be silently ignored.
        """
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        client, user = auth_client

        f = tmp_path / "orig.txt"
        f.write_text("content", encoding="utf-8")
        doc = Document.objects.create(
            user=user,
            name="原名",
            original_filename="orig.txt",
            file_path=str(f),
            file_size_bytes=7,
            file_type="txt",
            status="available",
        )

        resp = client.patch(
            _make_url(doc.pk),
            {
                "name": "新名",
                "original_filename": "hacked.exe",
                "file_type": "exe",
                "file_path": "/etc/passwd",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        doc.refresh_from_db()
        assert doc.name == "新名"
        assert doc.original_filename == "orig.txt"   # unchanged
        assert doc.file_type == "txt"                # unchanged
        assert doc.file_path == str(f)               # unchanged

    def test_rename_empty_name_returns_400(self, auth_client, tmp_path, settings):
        """Sending an empty string for name should fail validation."""
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024
        client, user = auth_client

        f = tmp_path / "s.txt"
        f.write_text("hi", encoding="utf-8")
        doc = Document.objects.create(
            user=user, name="original", original_filename="s.txt",
            file_path=str(f), file_size_bytes=2, file_type="txt", status="available",
        )

        resp = client.patch(_make_url(doc.pk), {"name": ""}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ═══════════════════════════════════════════════════════════════════════════════
# User isolation on search() service — US-006
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSearchUserIsolation:
    """
    US-006: search() must not return DocumentChunks belonging to other users.
    This is tested at the service layer (search() function directly).
    """

    @patch("apps.knowledge_base.services._get_embedding_model")
    def test_search_excludes_other_users_chunks(
        self, mock_get_model, auth_client, auth_client2, settings, tmp_path
    ):
        """
        US-006: 以 user_A 的 user_id 调用 search()，结果中不含 user_B 的 chunks
        """
        import numpy as np
        from unittest.mock import MagicMock
        from apps.knowledge_base.services import search
        from apps.knowledge_base.models import DocumentChunk

        settings.MEDIA_ROOT = str(tmp_path)
        settings.MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

        _, user_a = auth_client
        _, user_b = auth_client2

        fixed_vec = np.ones(512, dtype="float32") * 0.5
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts, **kw: np.tile(fixed_vec, (len(texts), 1))
        mock_get_model.return_value = mock_model

        # Create documents + chunks for both users
        def make_doc_with_chunk(user, content_text):
            fpath = tmp_path / f"doc_{user.pk}_{content_text[:5]}.txt"
            fpath.write_text(content_text, encoding="utf-8")
            doc = Document.objects.create(
                user=user, name=content_text[:20], original_filename=fpath.name,
                file_path=str(fpath), file_size_bytes=len(content_text),
                file_type="txt", status="available",
            )
            DocumentChunk.objects.create(
                document=doc, chunk_index=0,
                content=content_text, embedding=fixed_vec.tolist(),
            )
            return doc

        make_doc_with_chunk(user_a, "Alice的机密报告内容")
        make_doc_with_chunk(user_b, "Bob的机密报告内容")

        results = search(user_a.pk, "机密报告", top_k=10)

        result_contents = [r.content for r in results]
        assert any("Alice" in c for c in result_contents), "Alice's chunk must appear"
        assert not any("Bob" in c for c in result_contents), "Bob's chunk must NOT appear"
