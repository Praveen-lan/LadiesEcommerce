from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from store.admin import SareeInlineForm
from store.forms import PRODUCT_ID_HELP_TEXT
from store.models import (
    CartItem,
    Category,
    Customer,
    LoginPage,
    Order,
    OrderItem,
    OTPRequest,
    Product,
    ProductType,
    Saree,
    SiteSettings,
    ShoppingCart,
    TermsPage,
)


def png_upload(name="product.png"):
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "purple").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture
def product_type(db):
    return ProductType.objects.get_or_create(
        slug="jewellery",
        defaults={"name": "Jewellery"},
    )[0]


@pytest.fixture
def necklace(product_type):
    return Product.objects.create(
        product_type=product_type,
        name="Gold Tone Necklace",
        slug="goldtonenecklace",
        description="A lightweight necklace for celebrations.",
        price=Decimal("1200.00"),
        image="products/necklace.jpg",
    )


@pytest.fixture
def shopper_client(client, db):
    customer = Customer.objects.create(name="Shopper", phone="9876543210")
    session = client.session
    session["customer_id"] = customer.pk
    session.save()
    return client


@pytest.mark.django_db
def test_product_categories_are_not_registered_in_admin(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    assert ProductType not in admin.site._registry
    assert "Product Categories" not in response.content.decode()


@pytest.mark.django_db
def test_customer_admin_does_not_expose_email(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("admin:store_customer_changelist"))

    assert response.status_code == 200
    customer_admin = admin.site._registry[Customer]
    assert "email" not in response.context["cl"].list_display
    assert "email" not in customer_admin.search_fields
    assert "email" not in [field.name for field in Customer._meta.fields]


@pytest.mark.django_db
def test_sarees_are_labeled_products_in_admin(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    assert Product not in admin.site._registry
    assert "Products" in response.content.decode()
    assert "Sarees" not in response.content.decode()


@pytest.mark.django_db
def test_product_admin_optional_fields_can_be_left_blank(client, admin_user, category):
    client.force_login(admin_user)
    add_url = reverse("admin:store_saree_add")

    form_response = client.get(add_url)
    form = form_response.context["adminform"].form
    optional_fields = (
        "subcategory",
        "mrp",
        "discount_percent",
        "delivery_charge",
        "gst_percent",
        "length",
        "dispatch_note",
    )
    assert all(not form.fields[field].required for field in optional_fields)
    assert all(not form.fields[field].help_text for field in optional_fields)
    assert form.fields["product_id"].help_text == PRODUCT_ID_HELP_TEXT
    assert PRODUCT_ID_HELP_TEXT in form_response.content.decode()
    assert not any(
        text in form_response.content.decode()
        for text in (
            "Only sub categories belonging to the selected category",
            "original amount before any discount",
            "discount = original amount",
            "Additional delivery charge",
            "GST percentage applied",
            "Shown on the saree card",
            "Dispatch message shown",
        )
    )

    inline_form = SareeInlineForm()
    assert inline_form.fields["product_id"].help_text == PRODUCT_ID_HELP_TEXT
    inline_optional_fields = set(optional_fields).intersection(inline_form.fields)
    assert all(not inline_form.fields[field].required for field in inline_optional_fields)
    assert all(not inline_form.fields[field].help_text for field in inline_optional_fields)

    response = client.post(
        add_url,
        {
            "category": category.pk,
            "subcategory": "",
            "name": "Optional details saree",
            "product_id": "SD-OPT-1001",
            "slug": "OptionalDetailsSaree1",
            "price": "1499.00",
            "mrp": "",
            "discount_percent": "",
            "delivery_charge": "",
            "gst_percent": "",
            "fabric": "",
            "length": "",
            "dispatch_note": "",
            "description": "",
            "image_url": "https://images.example/optional-details.jpg",
        },
    )

    assert response.status_code == 302
    saree = Saree.objects.get(product_id="SD-OPT-1001")
    assert saree.subcategory is None
    assert saree.discount_percent is None
    assert saree.delivery_charge == Decimal("0.00")
    assert saree.gst_percent == Decimal("5.00")
    assert saree.length == ""
    assert saree.dispatch_note == ""


@pytest.mark.django_db
def test_store_admin_models_keep_add_buttons_and_hide_otp_requests(client, admin_user):
    client.force_login(admin_user)
    SiteSettings.objects.create()
    LoginPage.objects.create()
    TermsPage.objects.create()

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    store_app = next(app for app in response.context["app_list"] if app["app_label"] == "store")
    assert all(model["add_url"] for model in store_app["models"])
    assert OTPRequest not in admin.site._registry
    assert all(model["object_name"] != "OTPRequest" for model in store_app["models"])

    settings_form = client.get(reverse("admin:store_sitesettings_add"))
    assert settings_form.status_code == 200
    assert "Map-Iframe" in settings_form.content.decode()


@pytest.mark.django_db
def test_all_products_page_lists_and_filters_legacy_and_generic_products(shopper_client, necklace):
    category = Category.objects.create(title="Luxury Silk", tier=Category.Tier.HIGH)
    saree = Saree.objects.create(
        category=category,
        name="Kanjivaram Saree",
        price="2500.00",
        image_url="https://images.example/saree.jpg",
        is_featured=True,
    )

    response = shopper_client.get(reverse("store:all_products"))

    assert response.status_code == 200
    assert {item.name for item in response.context["all_items"]} == {saree.name, necklace.name}
    assert "Kanjivaram Saree" in response.content.decode()
    assert "Gold Tone Necklace" in response.content.decode()

    filtered = shopper_client.get(reverse("store:all_products"), {"category": "product:jewellery"})
    assert [item.name for item in filtered.context["all_items"]] == [necklace.name]
    assert "Kanjivaram Saree" not in filtered.content.decode()


@pytest.mark.django_db
def test_sarees_are_only_public_when_featured(shopper_client):
    category = Category.objects.create(title="Featured Collection", tier=Category.Tier.HIGH)
    hidden = Saree.objects.create(
        category=category,
        name="Hidden Saree",
        price="1800.00",
        image_url="https://images.example/hidden.jpg",
    )
    featured = Saree.objects.create(
        category=category,
        name="Featured Saree",
        price="2200.00",
        image_url="https://images.example/featured.jpg",
        is_featured=True,
    )

    for url in (
        reverse("store:catalog"),
        reverse("store:category_detail", args=[category.slug]),
        reverse("store:all_products"),
    ):
        response = shopper_client.get(url)
        assert response.status_code == 200
        assert "Hidden Saree" not in response.content.decode()
        assert "Featured Saree" in response.content.decode()

    assert shopper_client.get(reverse("store:saree_detail", args=[hidden.slug])).status_code == 404
    assert shopper_client.get(reverse("store:saree_detail", args=[featured.slug])).status_code == 200


@pytest.mark.django_db
def test_collections_services_menu_lists_product_categories_and_products(shopper_client, necklace):
    response = shopper_client.get(reverse("store:home"))

    assert response.status_code == 200
    assert necklace.product_type in response.context["navigation_product_types"]
    content = response.content.decode()
    assert necklace.product_type.name in content
    assert necklace.name in content
    assert necklace.get_absolute_url() in content


@pytest.mark.django_db
def test_product_detail_and_cart_support_generic_products(shopper_client, necklace):
    detail = shopper_client.get(reverse("store:product_detail", args=[necklace.slug]))
    assert detail.status_code == 200
    assert "Gold Tone Necklace" in detail.content.decode()

    added = shopper_client.post(
        reverse("store:add_to_cart"),
        {"item_type": "product", "item_id": str(necklace.pk), "quantity": "2"},
    )
    assert added.status_code == 302
    account_cart = ShoppingCart.objects.get(customer_id=shopper_client.session["customer_id"])
    assert CartItem.objects.get(cart=account_cart, product=necklace).quantity == 2

    cart = shopper_client.get(reverse("store:cart"))
    assert cart.status_code == 200
    assert "Jewellery" in cart.content.decode()
    assert "Gold Tone Necklace" in cart.content.decode()

    shopper_client.post(reverse("store:update_cart_item", args=["product", necklace.pk]), {"quantity": "3"})
    assert CartItem.objects.get(cart=account_cart, product=necklace).quantity == 3
    shopper_client.post(reverse("store:remove_cart_item", args=["product", necklace.pk]))
    assert not CartItem.objects.filter(cart=account_cart, product=necklace).exists()


@pytest.mark.django_db
def test_product_cart_moves_into_customer_cart_alongside_legacy_sarees(client, necklace):
    category = Category.objects.create(title="Everyday Collection", tier=Category.Tier.BASIC)
    saree = Saree.objects.create(
        category=category,
        name="Cotton Saree",
        price="900.00",
        image_url="https://images.example/cotton.jpg",
    )
    customer = Customer.objects.create(name="Shopper", phone="9876543210")
    session = client.session
    session["cart"] = {str(saree.pk): 1, f"product:{necklace.pk}": 2}
    session["customer_id"] = customer.pk
    session.save()

    client.get(reverse("store:cart"))
    account_cart = ShoppingCart.objects.get(customer=customer)
    assert CartItem.objects.get(cart=account_cart, saree=saree).quantity == 1
    assert CartItem.objects.get(cart=account_cart, product=necklace).quantity == 2
    assert "cart" not in client.session


@pytest.mark.django_db
def test_checkout_saves_a_generic_product_on_the_order_line(shopper_client, necklace, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    shopper_client.post(
        reverse("store:add_to_cart"),
        {"item_type": "product", "item_id": str(necklace.pk), "quantity": "2"},
    )

    response = shopper_client.post(
        reverse("store:checkout"),
        {
            "name": "Test Shopper",
            "phone": "9876543210",
            "email": "shopper@example.com",
            "address": "18 Heritage Street",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600040",
            "payment_reference": "UTR123456",
            "payment_screenshot": png_upload("receipt.png"),
        },
    )

    assert response.status_code == 302
    order = Order.objects.get()
    line = OrderItem.objects.get(order=order)
    assert line.product == necklace
    assert line.saree is None
    assert line.name == necklace.name
    assert line.quantity == 2
