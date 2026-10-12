import re
from html import unescape
import json

import pytest
from django.urls import reverse
from django.contrib.staticfiles.finders import find
from django.utils import timezone

from store.models import Customer, SEO, TermsPage


@pytest.mark.django_db
def test_terms_admin_renders_rich_text_editor(client, admin_user):
    terms = TermsPage.objects.create(
        title="Terms",
        content="<p>Existing <strong>formatted</strong> content</p>",
    )
    client.force_login(admin_user)

    response = client.get(reverse("admin:store_termspage_change", args=[terms.pk]))

    content = response.content.decode()
    assert response.status_code == 200
    assert 'data-django-prose-editor-configurable=' in content
    assert 'type="module"' in content
    assert "django_prose_editor/configurable.js" in content
    assert "&lt;strong&gt;formatted&lt;/strong&gt;" in content
    assert content.index("<h2>Last updated</h2>") < content.index("<h2>Created at</h2>")
    assert 'name="created_date"' in content
    assert 'name="created_time"' in content
    assert 'name="last_updated_date"' in content
    assert 'name="last_updated_time"' in content
    assert 'class="vDateField"' in content
    assert 'class="vTimeField"' in content
    assert "/static/admin/js/admin/DateTimeShortcuts.js" in content
    assert "/static/admin/js/calendar.js" in content
    form = response.context["adminform"].form
    assert str(form.fields["created_date"].label) == "<strong>Date</strong>"
    assert str(form.fields["created_time"].label) == "<strong>Time</strong>"
    assert str(form.fields["last_updated_date"].label) == "<strong>Date</strong>"
    assert str(form.fields["last_updated_time"].label) == "<strong>Time</strong>"
    assert form.fields["last_updated_date"].widget.__class__.__name__ == "AdminDateWidget"
    assert form.fields["last_updated_time"].widget.__class__.__name__ == "AdminTimeWidget"
    editor_config = re.search(
        r'data-django-prose-editor-configurable="([^"]+)"',
        content,
    )
    assert editor_config is not None
    extensions = json.loads(unescape(editor_config.group(1)))["extensions"]
    assert extensions["Bold"] is True
    assert extensions["OrderedList"] is True
    assert extensions["Heading"] == {"levels": [2, 3, 4]}
    assert extensions["TextAlign"] is True
    assert find("django_prose_editor/configurable.js")


@pytest.mark.django_db
def test_terms_admin_sanitizes_saved_rich_text_and_public_page(client, admin_user):
    terms = TermsPage.objects.create(title="Terms")
    client.force_login(admin_user)
    session = client.session
    session["customer_id"] = Customer.objects.create(
        name="Terms Reader",
        phone="9876543210",
    ).pk
    session.save()
    response = client.post(
        reverse("admin:store_termspage_change", args=[terms.pk]),
        {
            "title": "Terms",
            "subtitle": "Read carefully",
            "content": (
                '<p class="unsafe">Hello <strong>world</strong>'
                '<script>alert("xss")</script><a href="javascript:alert(1)">link</a></p>'
            ),
            "created_date": "2025-02-01",
            "created_time": "09:25:00",
            "last_updated_date": "2026-10-10",
            "last_updated_time": "14:35:00",
        },
    )

    assert response.status_code == 302
    terms.refresh_from_db()
    assert terms.content == '<p>Hello <strong>world</strong>link</p>'
    assert timezone.localtime(terms.created_at).strftime("%Y-%m-%d %H:%M:%S") == "2025-02-01 09:25:00"
    assert timezone.localtime(terms.updated_at).strftime("%Y-%m-%d %H:%M:%S") == "2026-10-10 14:35:00"

    public_page = client.get(reverse("store:terms"))
    assert public_page.status_code == 200
    content = public_page.content.decode()
    assert "<strong>world</strong>" in content
    assert 'alert("xss")' not in content
    assert 'class="unsafe"' not in content
    assert "javascript:" not in content


@pytest.mark.django_db
def test_rich_text_assets_load_only_for_terms_admin(client, admin_user):
    """Verify editor assets load only on Terms admin, not on SEO admin."""
    terms = TermsPage.objects.create(title="Terms", content="<p>Test</p>")
    seo = SEO.objects.create(
        page_name="Test Page",
        site_name="Swathi Designers",
        default_title="Test",
    )

    client.force_login(admin_user)

    # Check Terms admin - should have editor
    terms_response = client.get(reverse("admin:store_termspage_change", args=[terms.pk]))
    terms_content = terms_response.content.decode()
    assert 'data-django-prose-editor-configurable=' in terms_content
    assert 'type="module"' in terms_content
    assert "django_prose_editor" in terms_content

    # Check SEO admin - should NOT have editor
    seo_response = client.get(reverse("admin:store_seo_change", args=[seo.pk]))
    seo_content = seo_response.content.decode()
    assert 'data-django-prose-editor-configurable=' not in seo_content
    assert "django_prose_editor/configurable.js" not in seo_content


@pytest.mark.django_db
def test_terms_admin_can_delete_terms_page(client, admin_user):
    terms = TermsPage.objects.create(title="Terms to delete")
    client.force_login(admin_user)
    change_url = reverse("admin:store_termspage_change", args=[terms.pk])
    delete_url = reverse("admin:store_termspage_delete", args=[terms.pk])

    change_response = client.get(change_url)
    assert change_response.status_code == 200
    assert delete_url in change_response.content.decode()

    confirmation_response = client.get(delete_url)
    assert confirmation_response.status_code == 200
    assert "Are you sure" in confirmation_response.content.decode()

    delete_response = client.post(delete_url, {"post": "yes"})
    assert delete_response.status_code == 302
    assert not TermsPage.objects.filter(pk=terms.pk).exists()


@pytest.mark.django_db
def test_terms_admin_list_hides_selection_checkboxes_and_bulk_delete(client, admin_user):
    terms = TermsPage.objects.create(title="Terms")
    client.force_login(admin_user)
    changelist_url = reverse("admin:store_termspage_changelist")

    changelist_response = client.get(changelist_url)
    content = changelist_response.content.decode()
    assert changelist_response.status_code == 200
    assert f'name="_selected_action" value="{terms.pk}"' not in content
    assert 'name="action"' not in content
    assert "Delete selected" not in content
