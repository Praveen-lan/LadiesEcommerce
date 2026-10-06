import re

import pytest
from django.urls import reverse

from store.forms import ContactForm


def test_contact_form_shows_requested_required_field_messages():
    form = ContactForm(data={})

    assert not form.is_valid()
    assert form.errors["name"] == ["Please enter username."]
    assert form.errors["email"] == ["Please enter Email."]
    assert form.errors["phone"] == ["Please enter phone number."]
    assert form.errors["subject"] == ["Please enter subject."]
    assert form.errors["message"] == ["Please enter Message."]


def test_contact_form_shows_requested_message_for_invalid_email():
    form = ContactForm(
        data={
            "name": "A Shopper",
            "email": "not-an-email",
            "phone": "",
            "subject": "Product question",
            "message": "Please contact me.",
        }
    )

    assert not form.is_valid()
    assert form.errors["email"] == ["Please enter Email."]


@pytest.mark.parametrize(
    "phone",
    ["", "5123456789", "612345678", "61234567890", "abcdefghij", "abc6123456789", "61234-56789"],
)
def test_contact_form_requires_a_ten_digit_mobile_starting_with_six_to_nine(phone):
    form = ContactForm(
        data={
            "name": "A Shopper",
            "email": "shopper@example.com",
            "phone": phone,
            "subject": "Product question",
            "message": "Please contact me.",
        }
    )

    assert not form.is_valid()
    assert "phone" in form.errors


@pytest.mark.parametrize("phone", ["6123456789", "7123456789", "8123456789", "9876543210"])
def test_contact_form_accepts_ten_digit_mobile_numbers_starting_with_six_to_nine(phone):
    form = ContactForm(
        data={
            "name": "A Shopper",
            "email": "shopper@example.com",
            "phone": phone,
            "subject": "Product question",
            "message": "Please contact me.",
        }
    )

    assert form.is_valid(), form.errors


@pytest.mark.parametrize("method", ["get", "post"])
def test_contact_page_never_asks_the_browser_for_a_required_message(client, db, method):
    session = client.session
    session["customer_id"] = 1
    session.save()
    url = reverse("store:contact")

    if method == "post":
        response = client.post(
            url,
            {"name": "", "email": "", "phone": "", "subject": "", "message": ""},
        )
    else:
        response = client.get(url)

    html = response.content.decode()
    form_html = html[html.find('class="contact-form"') : html.find("</form>")]
    assert "This field is required" not in form_html
    assert not re.search(r'<(input|textarea)\b[^>]*\brequired\b', form_html)


def test_contact_page_shows_the_requested_messages(client, db):
    session = client.session
    session["customer_id"] = 1
    session.save()

    response = client.post(
        reverse("store:contact"),
        {"name": "", "email": "", "phone": "", "subject": "", "message": ""},
    )

    html = response.content.decode()
    for message in (
        "Please enter username.",
        "Please enter Email.",
        "Please enter phone number.",
        "Please enter subject.",
        "Please enter Message.",
    ):
        assert message in html


def test_empty_contact_post_is_bound_and_shows_required_messages(client, db):
    session = client.session
    session["customer_id"] = 1
    session.save()

    response = client.post(reverse("store:contact"), {})
    html = response.content.decode()

    assert response.status_code == 200
    for message in (
        "Please enter username.",
        "Please enter Email.",
        "Please enter phone number.",
        "Please enter subject.",
        "Please enter Message.",
    ):
        assert message in html
