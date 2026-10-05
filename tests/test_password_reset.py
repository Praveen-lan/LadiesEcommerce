"""Regression tests for the password reset flow.

Bug: submitting a registered email returned ``Server Error (500)`` and no email
was sent, because nothing configured an email backend or a sender address. The
flow now uses the storefront templates, always has a usable sender, and reports
delivery failures on the form instead of crashing.
"""

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

pytestmark = pytest.mark.django_db


class BrokenEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionRefusedError("SMTP server unreachable")


@pytest.fixture
def staff_user(db):
    return User.objects.create_superuser("yash", "yashkammili@gmail.com", "old-password")


def test_email_settings_are_configured():
    """An empty sender address or a missing backend is what caused the 500."""
    assert settings.EMAIL_BACKEND
    assert settings.DEFAULT_FROM_EMAIL
    assert settings.SERVER_EMAIL


def rendered_templates(response):
    return [template.name for template in response.templates]


def set_password_via_email_link(client, body, new_password):
    """Walk Django 6's two-step confirm flow: token link -> set-password -> done."""
    link = [word for word in body.split() if "/reset/" in word][0].rstrip(".")
    redirect = client.post(link, {"new_password1": new_password, "new_password2": new_password})

    assert redirect.status_code == 302
    set_password_url = redirect["Location"]

    page = client.get(set_password_url)
    assert page.status_code == 200
    assert "store/password_reset_confirm.html" in rendered_templates(page)

    done = client.post(
        set_password_url, {"new_password1": new_password, "new_password2": new_password}
    )
    assert done.status_code == 302
    assert done["Location"] == reverse("password_reset_complete")
    return link, set_password_url


def test_password_reset_page_renders_with_storefront_chrome(client, staff_user):
    response = client.get(reverse("admin_password_reset"))

    assert response.status_code == 200
    assert "store/password_reset_form.html" in rendered_templates(response)
    assert 'name="email"' in response.content.decode()
    assert "Swathi Designers" in response.content.decode()


def test_admin_login_links_to_the_reset_page(client):
    content = client.get(reverse("admin:login")).content.decode()

    assert reverse("admin_password_reset") in content


def test_registered_email_is_confirmed_and_the_email_is_sent(client, staff_user):
    response = client.post(reverse("admin_password_reset"), {"email": staff_user.email})

    assert response.status_code == 302
    assert response["Location"] == reverse("password_reset_done")

    done = client.get(response["Location"])
    assert done.status_code == 200
    assert b"Password reset email sent" in done.content

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [staff_user.email]
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert message.subject.strip()
    body = message.body
    assert f"/reset/{urlsafe_base64_encode(force_bytes(staff_user.pk))}/" in body


def test_reset_link_in_the_email_sets_a_new_password(client, staff_user):
    client.post(reverse("admin_password_reset"), {"email": staff_user.email})

    set_password_via_email_link(client, mail.outbox[0].body, "N3w-Str0ng-Pass!")

    staff_user.refresh_from_db()
    assert staff_user.check_password("N3w-Str0ng-Pass!")


def test_confirm_page_rejects_a_forged_token(client, staff_user):
    uid = urlsafe_base64_encode(force_bytes(staff_user.pk))

    response = client.get(reverse("password_reset_confirm", args=[uid, "not-a-real-token"]))

    assert response.status_code == 200
    assert b"no longer valid" in response.content
    staff_user.refresh_from_db()
    assert staff_user.check_password("old-password")


def test_unknown_email_redirects_without_sending(client, db):
    response = client.post(reverse("admin_password_reset"), {"email": "nobody@example.com"})

    assert response.status_code == 302
    assert response["Location"] == reverse("password_reset_done")
    assert mail.outbox == []


def test_invalid_email_is_rejected_on_the_form(client, db):
    response = client.post(reverse("admin_password_reset"), {"email": "not-an-email"})

    assert response.status_code == 200
    assert response.context["form"].errors["email"]
    assert mail.outbox == []


def test_mail_backend_failure_shows_a_form_error_instead_of_a_server_error(client, staff_user):
    with override_settings(EMAIL_BACKEND="tests.test_password_reset.BrokenEmailBackend"):
        response = client.post(reverse("admin_password_reset"), {"email": staff_user.email})

    assert response.status_code == 200
    assert "store/password_reset_form.html" in rendered_templates(response)
    assert response.context["form"].non_field_errors()
    assert b"could not send the reset email" in response.content

    staff_user.refresh_from_db()
    assert staff_user.check_password("old-password")


def test_reset_token_can_only_be_used_once(client, staff_user):
    uid = urlsafe_base64_encode(force_bytes(staff_user.pk))
    token = default_token_generator.make_token(staff_user)
    url = reverse("password_reset_confirm", args=[uid, token])

    redirect = client.post(url)
    assert redirect.status_code == 302
    set_password_url = redirect["Location"]
    assert client.post(
        set_password_url,
        {"new_password1": "N3w-Str0ng-Pass!", "new_password2": "N3w-Str0ng-Pass!"},
    ).status_code == 302

    replay = client.get(url)
    assert replay.status_code == 200
    assert b"no longer valid" in replay.content
