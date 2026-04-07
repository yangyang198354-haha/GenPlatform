"""Unit tests for knowledge_base models."""
import pytest
from apps.knowledge_base.models import Document


@pytest.mark.django_db
class TestDocumentModel:
    def test_document_creation(self, user):
        doc = Document.objects.create(
            user=user,
            name="My Doc",
            original_filename="my_doc.pdf",
            file_path="/tmp/my_doc.pdf",
            file_size_bytes=1024,
            file_type="pdf",
        )
        assert doc.pk is not None
        assert doc.status == "processing"
        assert doc.chunk_count == 0
        assert doc.error_message == ""

    def test_document_str(self, user):
        doc = Document.objects.create(
            user=user,
            name="Hello",
            original_filename="hello.txt",
            file_path="/tmp/hello.txt",
            file_size_bytes=100,
            file_type="txt",
        )
        assert "Hello" in str(doc)
        assert user.email in str(doc)

    def test_document_ordering_newest_first(self, user):
        d1 = Document.objects.create(
            user=user, name="A", original_filename="a.txt",
            file_path="/tmp/a.txt", file_size_bytes=10, file_type="txt",
        )
        d2 = Document.objects.create(
            user=user, name="B", original_filename="b.txt",
            file_path="/tmp/b.txt", file_size_bytes=10, file_type="txt",
        )
        docs = list(Document.objects.filter(user=user))
        assert docs[0].pk == d2.pk  # newest first

    def test_document_status_choices(self, user):
        for s in ("processing", "available", "error"):
            doc = Document(
                user=user, name="x", original_filename="x.txt",
                file_path="/tmp/x.txt", file_size_bytes=10, file_type="txt",
                status=s,
            )
            doc.full_clean()  # should not raise
