from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib import admin
from django.urls import reverse
from PIL import Image

from store.models import (
    CartItem,
    Category,
    Customer,
    Order,
    OrderItem,
    Product,
    ProductType,
    Saree,
    ShoppingCart,
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
def test_sarees_are_labeled_products_in_admin(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    assert Product not in admin.site._registry
    assert "Products" in response.content.decode()
    assert "Sarees" not in response.content.decode()


@pytest.mark.django_db
def test_all_products_page_lists_and_filters_legacy_and_generic_products(shopper_client, necklace):
    category = Category.objects.create(title="Luxury Silk", tier=Category.Tier.HIGH)
    saree = Saree.objects.create(
        category=category,
        name="Kanjivaram Saree",
        price="2500.00",
        image_url="https://images.example/saree.jpg",
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
