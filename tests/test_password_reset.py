"""Tests for verified Django admin username and password recovery."""

import re

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from store.models import AdminRecoveryCode

pytestmark = pytest.mark.django_db

NEW_USERNAME = "recovered-admin"
NEW_PASSWORD = "N3w-Adm1n-Pass!"


class BrokenEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionRefusedError("SMTP server unreachable")


@pytest.fixture
def staff_user(db):
    return User.objects.create_superuser("yash", "yash@example.com", "Old-Adm1n-Pass!")


def request_recovery_code(client, staff_user):
    response = client.post(
        reverse("admin_password_reset"),
        {"email": staff_user.email},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("admin_password_reset_verify")
    assert len(mail.outbox) == 1
    match = re.search(r"\b[0-9]{6}\b", mail.outbox[0].body)
    assert match
    return match.group()


def verify_recovery_code(client, code):
    return client.post(reverse("admin_password_reset_verify"), {"code": code})


def test_admin_recovery_pages_use_django_admin_chrome(client, staff_user):
    response = client.get(reverse("admin_password_reset"))

    assert response.status_code == 200
    assert "admin/store/admin_recovery_request.html" in [
        template.name for template in response.templates
    ]
    assert "admin/base_site.html" in [template.name for template in response.templates]
    assert "main-navbar" not in response.content.decode()


def test_admin_login_links_to_recovery_inside_admin(client):
    response = client.get(reverse("admin:login"))

    assert response.status_code == 200
    assert b"Forgotten your password or username?" in response.content
    assert reverse("admin_password_reset") in response.content.decode()


def test_email_code_resets_both_username_and_password_and_new_credentials_login(client, staff_user):
    code = request_recovery_code(client, staff_user)
    message = mail.outbox[0]
    assert message.to == [staff_user.email]
    assert message.from_email == settings.DEFAULT_FROM_EMAIL

    response = verify_recovery_code(client, code)
    assert response.status_code == 302
    assert response["Location"] == reverse("admin_password_reset_change")

    response = client.post(
        reverse("admin_password_reset_change"),
        {
            "username": NEW_USERNAME,
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("password_reset_complete")

    staff_user.refresh_from_db()
    assert staff_user.username == NEW_USERNAME
    assert staff_user.check_password(NEW_PASSWORD)

    response = client.post(
        reverse("admin:login"),
        {
            "username": NEW_USERNAME,
            "password": NEW_PASSWORD,
            "next": reverse("admin:index"),
        },
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("admin:index")


def test_recovery_code_is_single_use(client, staff_user):
    code = request_recovery_code(client, staff_user)
    assert verify_recovery_code(client, code).status_code == 302

    replay = verify_recovery_code(client, code)

    assert replay.status_code == 200
    assert b"invalid or expired" in replay.content


def test_invalid_code_is_rejected_and_attempts_are_limited(client, staff_user):
    correct_code = request_recovery_code(client, staff_user)
    wrong_code = "999999" if correct_code != "999999" else "888888"
    recovery = AdminRecoveryCode.objects.get(user=staff_user)

    for _ in range(5):
        response = verify_recovery_code(client, wrong_code)
        assert response.status_code == 200
    recovery.refresh_from_db()
    assert recovery.attempts == 5
    assert recovery.used_at is not None


def test_expired_code_cannot_authorize_credential_changes(client, staff_user):
    code = request_recovery_code(client, staff_user)
    recovery = AdminRecoveryCode.objects.get(user=staff_user)
    recovery.expires_at = timezone.now()
    recovery.save(update_fields=("expires_at",))

    response = verify_recovery_code(client, code)

    assert response.status_code == 200
    assert b"invalid or expired" in response.content
    assert client.get(reverse("admin_password_reset_change")).status_code == 302


def test_unknown_email_does_not_send_code_or_disclose_account_existence(client, db):
    response = client.post(
        reverse("admin_password_reset"),
        {"email": "nobody@example.com"},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("admin_password_reset_verify")
    assert mail.outbox == []
    verify = client.post(reverse("admin_password_reset_verify"), {"code": "123456"})
    assert verify.status_code == 200
    assert b"invalid or expired" in verify.content


def test_invalid_email_is_rejected_on_the_admin_recovery_page(client, db):
    response = client.post(reverse("admin_password_reset"), {"email": "not-an-email"})

    assert response.status_code == 200
    assert response.context["form"].errors["email"]
    assert "admin/base_site.html" in [template.name for template in response.templates]
    assert mail.outbox == []


def test_mail_failure_is_reported_and_no_recovery_code_is_created(client, staff_user):
    with override_settings(EMAIL_BACKEND="tests.test_password_reset.BrokenEmailBackend"):
        response = client.post(
            reverse("admin_password_reset"),
            {"email": staff_user.email},
        )

    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert b"could not send a recovery code" in response.content
    assert not AdminRecoveryCode.objects.filter(user=staff_user).exists()


def test_credentials_change_requires_verified_email_code(client, staff_user):
    response = client.post(
        reverse("admin_password_reset_change"),
        {
            "username": NEW_USERNAME,
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("admin_password_reset")
    staff_user.refresh_from_db()
    assert staff_user.username == "yash"
    assert staff_user.check_password("Old-Adm1n-Pass!")


def test_username_collision_and_password_mismatch_do_not_update_account(client, staff_user, db):
    User.objects.create_user("already-used", "another@example.com", "Other-Pass-123!")
    code = request_recovery_code(client, staff_user)
    assert verify_recovery_code(client, code).status_code == 302

    response = client.post(
        reverse("admin_password_reset_change"),
        {
            "username": "already-used",
            "password1": NEW_PASSWORD,
            "password2": "different-password",
        },
    )

    assert response.status_code == 200
    assert response.context["form"].errors
    staff_user.refresh_from_db()
    assert staff_user.username == "yash"
    assert staff_user.check_password("Old-Adm1n-Pass!")
