"""Regression test for the Home hero "Shop Collection" button.

Bug: the button fell back to the Contact Us page (``/contact/``) whenever a banner
had no custom link, so the primary call to action never reached the catalog.
"""

import re

import pytest
from django.urls import reverse

from store.models import Banner, Category, Customer, Saree


@pytest.fixture
def hero_banner(db, settings, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = str(tmp_path / "media")
    image = SimpleUploadedFile("hero.png", b"not-a-real-png", content_type="image/png")
    return Banner.objects.create(
        title="Heritage Handlooms",
        subtitle="Woven by hand, made to last",
        image=image,
        is_active=True,
        order=0,
    )


def hero_shop_buttons(content):
    """Return every hero CTA href that reads "Shop Collection"."""
    return re.findall(r'<a href="([^"]*)"[^>]*>\s*Shop Collection', content)


def test_shop_collection_button_points_at_the_catalog(client, hero_banner, category):
    response = client.get(reverse("store:home"))
    content = response.content.decode()

    assert response.status_code == 200
    hrefs = hero_shop_buttons(content)
    assert hrefs, "hero CTA not found on the home page"
    assert hrefs[0] == reverse("store:catalog")
    assert reverse("store:contact") not in hrefs[0]
    assert reverse("store:contact_us") not in hrefs[0]


def test_shop_collection_button_requires_login_then_lands_on_catalog(
    client, hero_banner, category, chiffon_saree
):
    href = hero_shop_buttons(client.get(reverse("store:home")).content.decode())[0]

    response = client.get(href)

    assert response.status_code == 302
    assert response["Location"] == reverse("store:login")

    client.post(
        reverse("store:login"),
        {"name": "CTA Shopper", "phone": "9876543210"},
    )
    response = client.get(href)

    assert response.status_code == 200
    assert response.templates[0].name == "store/catalog.html"
    assert b"Chiffon Sunset Saree" in response.content


def test_banner_without_a_link_never_falls_back_to_contact(client, hero_banner, category):
    assert not Banner.objects.get(pk=hero_banner.pk).link

    content = client.get(reverse("store:home")).content.decode()

    assert f'href="{reverse("store:contact")}" class="btn btn-gold btn-lg rounded-pill px-4"' not in content


def test_explicit_banner_link_is_still_honoured(client, hero_banner, category):
    hero_banner.link = reverse("store:category_detail", args=[category.slug])
    hero_banner.save()

    href = hero_shop_buttons(client.get(reverse("store:home")).content.decode())[0]

    assert href == reverse("store:category_detail", args=[category.slug])


def test_every_collection_layer_cta_goes_to_the_catalog(client, hero_banner, category):
    Saree.objects.create(
        category=category,
        name="Featured Silk Saree",
        price="1999.00",
        image_url="https://images.example/featured.jpg",
        is_featured=True,
    )
    premium = Category.objects.create(title="Premium Collection", tier=Category.Tier.MEDIUM, order=2)
    Saree.objects.create(
        category=premium,
        name="Featured Cotton Saree",
        price="1499.00",
        image_url="https://images.example/cotton.jpg",
        is_featured=True,
    )

    content = client.get(reverse("store:home")).content.decode()

    assert f'class="btn btn-outline-gold btn-sm rounded-pill ms-2"' in content
    assert reverse("store:category_detail", args=[category.slug]) in content
    assert reverse("store:category_detail", args=[premium.slug]) in content


def test_catalog_collection_filter_opens_only_the_selected_collection(client, db):
    customer = Customer.objects.create(name="Catalog Shopper", phone="9876543210")
    session = client.session
    session["customer_id"] = customer.pk
    session.save()

    premium = Category.objects.create(title="Premium Collection", tier=Category.Tier.HIGH)
    luxury = Category.objects.create(title="Luxury Collection", tier=Category.Tier.HIGH)
    Saree.objects.create(
        category=premium,
        name="Premium Silk Saree",
        price="4999",
        image_url="https://images.example/premium.jpg",
    )
    Saree.objects.create(
        category=luxury,
        name="Luxury Silk Saree",
        price="6999",
        image_url="https://images.example/luxury.jpg",
    )

    catalog = client.get(reverse("store:catalog"))
    premium_url = reverse("store:category_detail", args=[premium.slug])
    catalog_content = catalog.content.decode()

    assert f'href="{premium_url}" class="btn filter-btn"' in catalog_content
    assert f'href="{reverse("store:catalog")}?tier=high"' not in catalog_content

    response = client.get(premium_url)
    content = response.content.decode()

    assert response.status_code == 200
    assert response.templates[0].name == "store/category_detail.html"
    assert "Premium Silk Saree" in content
    assert "Luxury Silk Saree" not in content
    assert 'class="filter-bar"' not in content
