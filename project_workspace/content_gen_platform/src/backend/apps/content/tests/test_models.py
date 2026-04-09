"""Unit tests for Content model."""
import pytest
from apps.content.models import Content


@pytest.mark.django_db
class TestContentModel:
    def test_default_status_is_draft(self, user):
        c = Content.objects.create(user=user, body="some text")
        assert c.status == "draft"

    def test_default_platform_is_general(self, user):
        c = Content.objects.create(user=user, body="some text")
        assert c.platform_type == "general"

    def test_default_style_is_professional(self, user):
        c = Content.objects.create(user=user, body="some text")
        assert c.style == "professional"

    def test_confirmed_at_null_by_default(self, user):
        c = Content.objects.create(user=user, body="some text")
        assert c.confirmed_at is None

    def test_str_with_title(self, user):
        c = Content.objects.create(user=user, title="Hello", body="body text")
        assert "Hello" in str(c)

    def test_str_without_title_uses_body(self, user):
        c = Content.objects.create(user=user, body="body text without title")
        assert "body text" in str(c)

    def test_ordering_newest_first(self, user):
        c1 = Content.objects.create(user=user, body="first")
        c2 = Content.objects.create(user=user, body="second")
        contents = list(Content.objects.filter(user=user).order_by("-pk"))
        assert contents[0].pk == c2.pk

    def test_used_document_ids_default_empty(self, user):
        c = Content.objects.create(user=user, body="text")
        assert c.used_document_ids == []
