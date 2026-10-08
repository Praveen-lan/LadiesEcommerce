"""Tests for collection sub categories.

Every collection carries the starter set from ``DEFAULT_SUBCATEGORIES`` (Silk
Sarees, Cotton Sarees, ...), the nav dropdown nests them under their collection,
each one owns a themed listing page, and staff can create them inline from the
category admin page.
"""

from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from store.models import DEFAULT_SUBCATEGORIES, Category, Saree, SubCategory, guess_subcategory

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def silk_category(db):
    return Category.objects.create(title="Luxury Pure Silk", tier=Category.Tier.HIGH)


@pytest.fixture
def silk_subcategory(silk_category):
    return SubCategory.objects.create(
        category=silk_category,
        title="Silk Sarees",
        subtitle="Pure mulberry and Kanjivaram weaves.",
    )


@pytest.fixture
def cotton_subcategory(silk_category):
    return SubCategory.objects.create(category=silk_category, title="Cotton Sarees")


@pytest.fixture
def signed_in(client, db):
    customer_session = client.session
    customer_session["customer_id"] = 1
    customer_session.save()
    return client


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("staff", "staff@example.com", "pw12345!")


# --------------------------------------------------------------------------- #
# Model behaviour
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_subcategory_slug_is_generated_and_unique_per_category(db):
    first = Category.objects.create(title="First", tier=Category.Tier.HIGH)
    second = Category.objects.create(title="Second", tier=Category.Tier.BASIC)

    one = SubCategory.objects.create(category=first, title="Silk Sarees")
    two = SubCategory.objects.create(category=second, title="Silk Sarees")

    assert one.slug == "silk-sarees"
    assert two.slug == "silk-sarees"


@pytest.mark.django_db
def test_duplicate_title_inside_one_category_gets_a_numbered_slug(silk_category):
    first = SubCategory.objects.create(category=silk_category, title="Silk Sarees")
    second = SubCategory.objects.create(category=silk_category, title="Silk Sarees")

    assert first.slug == "silk-sarees"
    assert second.slug == "silk-sarees-2"


@pytest.mark.django_db
def test_subcategory_url_is_nested_under_its_collection(silk_category, silk_subcategory):
    assert silk_subcategory.get_absolute_url() == reverse(
        "store:subcategory_detail",
        kwargs={"category_slug": silk_category.slug, "slug": silk_subcategory.slug},
    )


@pytest.mark.django_db
def test_deleting_a_subcategory_keeps_its_sarees(silk_category, silk_subcategory, db):
    saree = Saree.objects.create(
        category=silk_category,
        subcategory=silk_subcategory,
        name="Kanjivaram Antique Gold",
        price="8999",
        image_url="https://images.example/kanjivaram.jpg",
    )

    silk_subcategory.delete()

    saree.refresh_from_db()
    assert saree.subcategory is None
    assert Saree.objects.filter(pk=saree.pk).exists()


# --------------------------------------------------------------------------- #
# Auto assignment
# --------------------------------------------------------------------------- #


def guess(text, fabric=""):
    catalogue = [
        {"keywords": keywords, "subcategory": title}
        for title, _subtitle, keywords in DEFAULT_SUBCATEGORIES
    ]
    saree = Saree(name=text, description="", fabric=fabric)
    match = guess_subcategory(saree, catalogue)
    return match["subcategory"] if match else None


@pytest.mark.parametrize(
    "name,fabric,expected",
    [
        ("Kanjivaram Antique Gold", "Silk", "Silk Sarees"),
        ("Everyday Cotton Comfort", "Cotton", "Cotton Sarees"),
        ("Party Georgette Drape", "Georgette", "Modern & Synthetic Fabric Sarees"),
        ("Block Print Handloom", "", "Printed & Embroidery Sarees"),
        ("Zardozi Zari Bridal", "", "Printed & Embroidery Sarees"),
        ("Handspun Khadi Comfort", "", "Cotton Sarees"),
        ("Mystery Item", "", None),
    ],
)
def test_sarees_are_filed_by_fabric_first_then_name(db, name, fabric, expected):
    assert guess(name, fabric) == expected


@pytest.mark.django_db
def test_fabric_outranks_a_style_word_in_the_name(db):
    """A "fusion" cotton saree files under Cotton Sarees: fabric is the stronger signal."""
    assert guess("Indo Western Fusion Saree", "Cotton") == "Cotton Sarees"


@pytest.mark.django_db
def test_the_starter_catalogue_covers_the_five_expected_styles(db):
    titles = [title for title, _subtitle, _keywords in DEFAULT_SUBCATEGORIES]

    assert titles == [
        "Silk Sarees",
        "Cotton Sarees",
        "Modern & Synthetic Fabric Sarees",
        "Printed & Embroidery Sarees",
        "Modern Fusion Sarees",
    ]


# --------------------------------------------------------------------------- #
# Storefront
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_nav_dropdown_hides_subcategories_without_products(signed_in):
    categories = Category.objects.order_by("order", "id")
    visible_category = categories.first()
    visible_subcategory = visible_category.subcategories.first()
    Saree.objects.create(
        category=visible_category,
        subcategory=visible_subcategory,
        name="Visible Nav Saree",
        price="999",
        image_url="https://images.example/nav-saree.jpg",
    )

    response = signed_in.get(reverse("store:home"))
    navigation_categories = response.context["navigation_categories"]
    expected_titles = [
        "Premium Collection",
        "Luxury Collection",
        "Base Collection",
        "Everyday Comfort",
        "Budget Collection",
    ]

    assert [category.title for category in navigation_categories] == expected_titles
    assert all(category.subcategories.count() == (1 if category.pk == visible_category.pk else 0)
               for category in navigation_categories)

    content = response.content.decode()
    assert 'class="dropdown-menu collections-menu"' in content
    assert 'data-bs-auto-close="outside"' in content
    for category in navigation_categories:
        if category.subcategories.exists():
            assert f'aria-controls="collection-submenu-{category.slug}"' in content
            assert f'id="collection-submenu-{category.slug}"' in content
            for subcategory in category.subcategories.all():
                assert subcategory.get_absolute_url() in content
        else:
            assert f'aria-controls="collection-submenu-{category.slug}"' not in content
            assert f'id="collection-submenu-{category.slug}"' not in content
            assert f'class="dropdown-item collections-category-link collections-category-label"' in content
    assert "No styles added yet" not in content


@pytest.mark.django_db
def test_collections_submenu_is_capped_and_scrollable_when_many_styles_exist(signed_in):
    category = Category.objects.first()
    for index in range(12):
        subcategory = SubCategory.objects.create(category=category, title=f"Style {index:02}")
        Saree.objects.create(
            category=category,
            subcategory=subcategory,
            name=f"Style Saree {index:02}",
            price="999",
            image_url=f"https://images.example/style-{index:02}.jpg",
        )

    content = signed_in.get(reverse("store:home")).content.decode()
    submenu = content.split(f'id="collection-submenu-{category.slug}"', 1)[1].split("</ul>", 1)[0]

    assert submenu.count('class="dropdown-item collections-child"') == 12
    css = open("static/css/style.css", encoding="utf-8").read()
    assert "max-height: min(70vh, 320px)" in css
    assert "overflow-y: auto" in css
    assert "Visible Nav Saree" not in content


@pytest.mark.django_db
def test_subcategory_page_lists_only_its_own_sarees(
    signed_in, silk_category, silk_subcategory, cotton_subcategory
):
    silk = Saree.objects.create(
        category=silk_category,
        subcategory=silk_subcategory,
        name="Kanjivaram Antique Gold",
        price="8999",
        image_url="https://images.example/kanjivaram.jpg",
    )
    Saree.objects.create(
        category=silk_category,
        subcategory=cotton_subcategory,
        name="Everyday Cotton Comfort",
        price="1499",
        image_url="https://images.example/cotton.jpg",
    )

    response = signed_in.get(silk_subcategory.get_absolute_url())

    assert response.status_code == 200
    assert response.templates[0].name == "store/subcategory_detail.html"
    content = response.content.decode()
    assert "Kanjivaram Antique Gold" in content
    assert "Everyday Cotton Comfort" not in content
    assert silk.pk in {s.pk for s in response.context["sarees"]}


@pytest.mark.django_db
def test_subcategory_page_uses_the_same_theme_and_breadcrumb_trail(
    signed_in, silk_category, silk_subcategory
):
    response = signed_in.get(silk_subcategory.get_absolute_url())
    content = response.content.decode()

    assert 'class="page-banner image-page-banner"' in content
    assert '<a href="%s">Home</a>' % reverse("store:home") in content
    assert '<a href="%s">%s</a>' % (
        reverse("store:category_detail", args=[silk_category.slug]),
        silk_category.title,
    ) in content
    assert silk_subcategory.subtitle in content


@pytest.mark.django_db
def test_subcategory_page_offers_the_sibling_styles(signed_in, silk_category, silk_subcategory, cotton_subcategory):
    for subcategory, name in (
        (silk_subcategory, "Silk subcategory product"),
        (cotton_subcategory, "Cotton subcategory product"),
    ):
        Saree.objects.create(
            category=silk_category,
            subcategory=subcategory,
            name=name,
            price="999",
            image_url=f"https://images.example/{subcategory.slug}.jpg",
        )
    content = signed_in.get(silk_subcategory.get_absolute_url()).content.decode()

    assert cotton_subcategory.get_absolute_url() in content
    assert "subcategory-chip active" in content


@pytest.mark.django_db
def test_subcategory_page_404s_for_an_unknown_style(signed_in, silk_category):
    response = signed_in.get(
        reverse("store:subcategory_detail", args=[silk_category.slug, "no-such-style"])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_subcategory_page_404s_when_the_style_belongs_to_another_collection(
    signed_in, silk_category, cotton_subcategory
):
    other = Category.objects.create(title="Everyday Comfort", tier=Category.Tier.BASIC)

    response = signed_in.get(
        reverse("store:subcategory_detail", args=[other.slug, cotton_subcategory.slug])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_empty_subcategory_page_shows_no_collection_browse_message(signed_in, silk_subcategory):
    response = signed_in.get(silk_subcategory.get_absolute_url())
    content = response.content.decode()

    assert response.status_code == 200
    assert "Browse the full" not in content
    assert "No sarees in" not in content
    assert 'class="empty-state' not in content


@pytest.mark.django_db
def test_collection_page_links_to_each_of_its_subcategories(
    signed_in, silk_category, silk_subcategory, cotton_subcategory
):
    for subcategory in (silk_subcategory, cotton_subcategory):
        Saree.objects.create(
            category=silk_category,
            subcategory=subcategory,
            name=f"{subcategory.title} product",
            price="999",
            image_url=f"https://images.example/{subcategory.slug}.jpg",
        )
    response = signed_in.get(reverse("store:category_detail", args=[silk_category.slug]))

    assert response.status_code == 200
    content = response.content.decode()
    assert silk_subcategory.get_absolute_url() in content
    assert cotton_subcategory.get_absolute_url() in content


@pytest.mark.django_db
def test_collection_page_displays_subcategories_as_image_cards_and_keeps_all_sarees(
    signed_in, silk_category, silk_subcategory, cotton_subcategory
):
    Saree.objects.create(
        category=silk_category,
        subcategory=silk_subcategory,
        name="Kanjivaram Antique Gold",
        price="8999",
        image_url="https://images.example/kanjivaram.jpg",
    )

    response = signed_in.get(reverse("store:category_detail", args=[silk_category.slug]))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'class="collection-style-card"' in content
    assert silk_subcategory.title in content
    assert cotton_subcategory.title not in content
    assert "All sarees in this collection" in content
    assert "Kanjivaram Antique Gold" in content


@pytest.mark.django_db
def test_collection_saree_card_shows_admin_product_id_on_image(signed_in, silk_category, silk_subcategory):
    Saree.objects.create(
        category=silk_category,
        subcategory=silk_subcategory,
        name="Product ID Saree",
        product_id="SD-SRK-1001",
        price="2999.00",
        image_url="https://images.example/product-id-saree.jpg",
    )

    response = signed_in.get(reverse("store:category_detail", args=[silk_category.slug]))
    content = response.content.decode()

    assert response.status_code == 200
    assert '<span class="saree-product-id">Product ID: SD-SRK-1001</span>' in content


@pytest.mark.django_db
def test_saree_page_links_to_its_subcategory_without_a_breadcrumb(
    signed_in, silk_category, silk_subcategory
):
    saree = Saree.objects.create(
        category=silk_category,
        subcategory=silk_subcategory,
        name="Patola Heritage Silk",
        price="12999",
        image_url="https://images.example/patola.jpg",
    )

    content = signed_in.get(saree.get_absolute_url()).content.decode()

    assert "<ol class=\"breadcrumb\">" not in content
    assert silk_subcategory.get_absolute_url() in content
    assert silk_subcategory.title in content


@pytest.mark.django_db
def test_saree_without_a_subcategory_still_renders(signed_in, silk_category):
    saree = Saree.objects.create(
        category=silk_category,
        name="Unfiled Saree",
        price="999",
        image_url="https://images.example/unfiled.jpg",
    )

    response = signed_in.get(saree.get_absolute_url())

    assert response.status_code == 200
    assert "Unfiled Saree" in response.content.decode()


@pytest.mark.django_db
def test_guests_are_sent_to_login_before_reaching_a_subcategory(signed_in, silk_category, silk_subcategory):
    from django.test import Client

    guest = Client()

    response = guest.get(silk_subcategory.get_absolute_url())

    assert response.status_code == 302
    assert response["Location"] == reverse("store:login")


@pytest.mark.django_db
def test_sitemap_lists_every_subcategory(client, silk_category, silk_subcategory, cotton_subcategory):
    content = client.get("/sitemap.xml").content.decode()

    assert silk_subcategory.get_absolute_url() in content
    assert cotton_subcategory.get_absolute_url() in content


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_admin_renders_a_subcategory_inline_on_the_category_page(client, staff, silk_category):
    client.force_login(staff)

    response = client.get(reverse("admin:store_category_change", args=[silk_category.pk]))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'name="subcategories-TOTAL_FORMS"' in content
    prefixes = [inline.formset.prefix for inline in response.context["inline_admin_formsets"]]
    assert prefixes == ["subcategories", "sarees"]


@pytest.mark.django_db
def test_staff_can_create_a_subcategory_inline_from_the_category_page(client, staff, silk_category):
    client.force_login(staff)
    change_url = reverse("admin:store_category_change", args=[silk_category.pk])
    page = client.get(change_url)
    formsets = {inline.formset.prefix: inline.formset for inline in page.context["inline_admin_formsets"]}

    data = {
        "title": silk_category.title,
        "tier": silk_category.tier,
        "slug": silk_category.slug,
        "subtitle": "",
        "image": "",
        "order": "0",
        "_save": "Save",
    }
    for prefix, formset in formsets.items():
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": str(formset.total_form_count()),
                f"{prefix}-INITIAL_FORMS": str(formset.initial_form_count()),
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            }
        )
    data.update(
        {
            "subcategories-TOTAL_FORMS": "1",
            "subcategories-0-title": "Organza Sarees",
            "subcategories-0-subtitle": "Sheer festive drapes.",
            "subcategories-0-order": "2",
        }
    )

    response = client.post(change_url, data)

    assert response.status_code == 302
    created = SubCategory.objects.get(category=silk_category, title="Organza Sarees")
    assert created.slug == "organza-sarees"
    assert created.order == 2


@pytest.mark.django_db
def test_subcategory_changelist_and_change_page_render(client, staff, silk_category, silk_subcategory):
    client.force_login(staff)

    assert client.get(reverse("admin:store_subcategory_changelist")).status_code == 200
    response = client.get(reverse("admin:store_subcategory_change", args=[silk_subcategory.pk]))
    assert response.status_code == 200
    assert silk_category.title in response.content.decode()


@pytest.mark.django_db
def test_saree_admin_offers_only_the_parent_collection_choices(client, staff, silk_category, silk_subcategory):
    other = Category.objects.create(title="Everyday Comfort", tier=Category.Tier.BASIC)
    other_sub = SubCategory.objects.create(category=other, title="Silk Sarees")
    client.force_login(staff)

    response = client.get(reverse("admin:store_saree_add"))
    content = response.content.decode()

    assert f'data-category="{silk_category.pk}"' in content
    assert f'data-category="{other.pk}"' in content
    assert str(silk_subcategory.pk) in content
    assert str(other_sub.pk) in content


@pytest.mark.django_db
def test_saree_admin_ships_the_filter_script_and_the_fields_it_binds_to(client, staff, silk_category):
    """subcategory-filter.js finds selects by name and pairs id_subcategory with id_category."""
    client.force_login(staff)

    content = client.get(reverse("admin:store_saree_add")).content.decode()

    assert "store/admin/subcategory-filter.js" in content
    assert 'id="id_subcategory"' in content
    assert 'id="id_category"' in content

    script = (BASE_DIR / "static" / "store" / "admin" / "subcategory-filter.js").read_text()
    assert 'select[name$="subcategory"]' in script
    assert "/subcategory$/, \"category\"" in script


@pytest.mark.django_db
def test_saree_admin_rejects_a_subcategory_from_another_collection(
    client, staff, silk_category, cotton_subcategory
):
    other = Category.objects.create(title="Everyday Comfort", tier=Category.Tier.BASIC)
    client.force_login(staff)

    response = client.post(
        reverse("admin:store_saree_add"),
        {
            "category": other.pk,
            "subcategory": cotton_subcategory.pk,
            "name": "Mismatched Saree",
            "price": "1499",
            "mrp": "",
            "fabric": "Cotton",
            "description": "",
            "image": "",
            "image_url": "https://images.example/mismatch.jpg",
            "_save": "Save",
        },
    )

    assert response.status_code == 200
    assert "belongs to" in response.content.decode()
    assert not Saree.objects.filter(name="Mismatched Saree").exists()


@pytest.mark.django_db
def test_saree_admin_saves_a_matching_subcategory(client, staff, silk_category, silk_subcategory):
    client.force_login(staff)

    response = client.post(
        reverse("admin:store_saree_add"),
        {
            "category": silk_category.pk,
            "subcategory": silk_subcategory.pk,
            "name": "Kanjivaram Antique Gold",
            "product_id": "KA-1001",
            "price": "8999",
            "mrp": "",
            "fabric": "Silk",
            "description": "",
            "image": "",
            "image_url": "https://images.example/kanjivaram.jpg",
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    assert Saree.objects.get(name="Kanjivaram Antique Gold").subcategory == silk_subcategory
