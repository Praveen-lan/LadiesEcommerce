"""Regression tests: the shopper session must be browser-specific.

Bug: the cart was persisted in the database keyed on the customer account, so
state created while signed in in one browser was shared with every other
browser. Everything about a visitor now lives in that visitor's own session,
and the session key is rotated when the login succeeds.
"""

import pytest
from django.apps import apps
from django.test import Client
from django.urls import reverse

from store.models import Customer


def sign_in(client, name="Test Shopper", phone="9876543210"):
    return client.post(reverse("store:login"), {"name": name, "phone": phone})


@pytest.fixture
def shopper(db, site_settings):
    return Customer.objects.create(name="Test Shopper", phone="9876543210")


def test_no_shared_cart_model_exists(db):
    """The account-wide cart table is gone; nothing is keyed on the customer."""
    with pytest.raises(LookupError):
        apps.get_model("store", "CartItem")
    assert "CartItem" not in {model.__name__ for model in apps.get_app_config("store").get_models()}


@pytest.mark.django_db
def test_guest_navigation_and_cart_actions_redirect_to_login(chiffon_saree):
    guest = Client()
    login_url = reverse("store:login")

    assert guest.get(reverse("store:home")).status_code == 200
    for route_name in ("catalog", "about", "cart", "profile", "checkout"):
        response = guest.get(reverse(f"store:{route_name}"))
        assert response.status_code == 302
        assert response["Location"] == login_url

    response = guest.post(
        reverse("store:add_to_cart"),
        {"saree_id": chiffon_saree.pk, "quantity": "1"},
    )
    assert response.status_code == 302
    assert response["Location"] == login_url
    assert not guest.session.get("cart")

    sign_in(guest)
    for route_name in ("catalog", "about", "cart"):
        assert guest.get(reverse(f"store:{route_name}")).status_code == 200


@pytest.mark.django_db
def test_second_browser_starts_as_a_guest(shopper, site_settings, chiffon_saree):
    chrome = Client()
    edge = Client()

    sign_in(chrome)
    chrome.post(reverse("store:add_to_cart"), {"saree_id": chiffon_saree.pk, "quantity": "2"})

    edge_home = edge.get(reverse("store:home"))
    edge_content = edge_home.content.decode()

    chrome_home = chrome.get(reverse("store:home"))
    assert chrome_home.context["customer"].pk == shopper.pk
    assert edge_home.context["customer"] is None
    assert edge_home.context["cart_count"] == 0
    assert "customer_id" not in edge.session
    assert not edge.session.get("cart")
    assert "Edit Profile" not in edge_content
    assert "Log out" not in edge_content
    assert "Test Shopper" not in edge_content

    cache_directives = {
        directive.strip().lower()
        for directive in chrome_home["Cache-Control"].split(",")
    }
    assert {"private", "no-store", "max-age=0"} <= cache_directives
    assert "cookie" in chrome_home["Vary"].lower()


@pytest.mark.django_db
def test_two_authenticated_browsers_keep_separate_cart_contents(
    shopper, site_settings, chiffon_saree, silk_saree
):
    chrome = Client()
    edge = Client()

    sign_in(chrome)
    sign_in(edge)
    chrome.post(reverse("store:add_to_cart"), {"saree_id": chiffon_saree.pk, "quantity": "2"})
    edge.post(reverse("store:add_to_cart"), {"saree_id": silk_saree.pk, "quantity": "1"})

    chrome_cart = chrome.get(reverse("store:cart"))
    edge_cart = edge.get(reverse("store:cart"))

    assert chrome_cart.context["cart_count"] == 2
    assert [item["saree"].pk for item in chrome_cart.context["cart_items"]] == [chiffon_saree.pk]
    assert edge_cart.context["cart_count"] == 1
    assert [item["saree"].pk for item in edge_cart.context["cart_items"]] == [silk_saree.pk]


@pytest.mark.django_db
def test_guest_cart_action_requires_login_then_works_after_login(shopper, site_settings, chiffon_saree):
    browser = Client()

    response = browser.post(
        reverse("store:add_to_cart"),
        {"saree_id": chiffon_saree.pk, "quantity": "3"},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("store:login")
    assert not browser.session.get("cart")

    sign_in(browser)
    browser.post(reverse("store:add_to_cart"), {"saree_id": chiffon_saree.pk, "quantity": "3"})

    cart = browser.get(reverse("store:cart"))
    assert cart.context["cart_count"] == 3
    assert [item["saree"].pk for item in cart.context["cart_items"]] == [chiffon_saree.pk]


@pytest.mark.django_db
def test_session_key_is_rotated_on_login(db, site_settings):
    browser = Client()
    browser.get(reverse("store:home"))
    before = browser.session.session_key

    sign_in(browser)
    after = browser.session.session_key

    assert before is not None
    assert after is not None
    assert before != after


@pytest.mark.django_db
def test_login_needs_no_second_verification_step(db, site_settings):
    browser = Client()

    response = sign_in(browser)

    assert response.status_code == 302
    assert response["Location"] == reverse("store:home")
    assert browser.session["customer_id"] == Customer.objects.get(phone="9876543210").pk


@pytest.mark.django_db
def test_login_does_not_leak_pre_authentication_state(db, site_settings):
    browser = Client()

    sign_in(browser)

    for key in ("otp_pending", "dev_otp", "visitor_name", "visitor_phone"):
        assert key not in browser.session


@pytest.mark.django_db
def test_logout_clears_the_browser_session(shopper, site_settings):
    browser = Client()
    sign_in(browser)
    browser.get(reverse("store:home"))

    browser.get(reverse("store:logout"))

    assert "customer_id" not in browser.session
    assert browser.get(reverse("store:home")).context["customer"] is None


@pytest.mark.django_db
def test_two_browsers_can_hold_different_accounts(db, site_settings):
    first = Client()
    second = Client()
    one = Customer.objects.create(name="One", phone="9876543210")
    two = Customer.objects.create(name="Two", phone="9123456789")

    sign_in(first, name="One", phone=one.phone)
    sign_in(second, name="Two", phone=two.phone)

    assert first.get(reverse("store:home")).context["customer"].pk == one.pk
    assert second.get(reverse("store:home")).context["customer"].pk == two.pk
