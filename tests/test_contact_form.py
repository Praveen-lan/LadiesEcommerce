import re

import pytest
from django.urls import reverse

from store.forms import ContactForm


def test_contact_form_shows_requested_required_field_messages():
    form = ContactForm(data={})

    assert not form.is_valid()
    assert form.errors["name"] == ["Please give correct username."]
    assert form.errors["email"] == ["Please give correct email address."]
    assert form.errors["subject"] == ["Please give correct subject."]
    assert form.errors["message"] == ["Please give correct message."]


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
    assert form.errors["email"] == ["Please give correct email address."]


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
        "Please give correct username.",
        "Please give correct email address.",
        "Please give correct subject.",
        "Please give correct message.",
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
        "Please give correct username.",
        "Please give correct email address.",
        "Please give correct subject.",
        "Please give correct message.",
    ):
        assert message in html
