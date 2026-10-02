from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from store.models import Category, Order, OrderItem, Saree, SiteSettings


@pytest.fixture
def site_settings(db):
    return SiteSettings.objects.create(
        shop_name="Saree Elegance",
        address="18, Heritage Textile Street, Anna Nagar, Chennai",
        phone="9876543210",
        email="hello@sareeelegance.in",
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("staff", "staff@example.com", "pw12345!")


@pytest.fixture
def category(db):
    return Category.objects.create(title="Luxury Pure Silk", tier=Category.Tier.HIGH)


@pytest.fixture
def other_category(db):
    return Category.objects.create(title="Basic Collection", tier=Category.Tier.BASIC)


@pytest.fixture
def chiffon_saree(category):
    return Saree.objects.create(
        category=category,
        name="Chiffon Sunset Saree",
        price="2499.00",
        image_url="https://images.example/chiffon-sunset.jpg",
    )


@pytest.fixture
def silk_saree(category):
    return Saree.objects.create(
        category=category,
        name="Kanjivaram Silk Saree",
        price="2999.00",
        image_url="https://images.example/kanjivaram.jpg",
    )


@pytest.fixture
def basic_saree(other_category):
    return Saree.objects.create(
        category=other_category,
        name="Cotton Everyday Saree",
        price="999.00",
        image_url="https://images.example/cotton.jpg",
    )


@pytest.fixture
def order_with_three_items(db):
    order = Order.objects.create(
        order_id="SE202610011604181",
        name="Naveen",
        phone="9876543210",
        address="18, Heritage Textile Street, Anna Nagar, Chennai",
        city="Chennai",
        pincode="600040",
        payment_method=Order.PaymentMethod.COD,
        subtotal=Decimal("6497.00"),
        delivery_charge=Decimal("0.00"),
        gst=Decimal("324.85"),
        total=Decimal("6821.85"),
    )
    items = [
        OrderItem.objects.create(order=order, name=name, price=price, quantity=1)
        for name, price in (
            ("Banarasi Moonlight Brocade", Decimal("2499.00")),
            ("Patola Heritage Silk", Decimal("2999.00")),
            ("Cotton Everyday Saree", Decimal("999.00")),
        )
    ]
    return order, items
