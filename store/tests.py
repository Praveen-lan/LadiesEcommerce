from decimal import Decimal
from io import BytesIO
import tempfile

from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .cart import Cart
from .models import (
    AboutPage,
    Category,
    ContactMessage,
    Customer,
    Order,
    OrderItem,
    PaymentProof,
    PaymentQR,
    Saree,
    SEO,
    SiteSettings,
    SubCategory,
    TermsPage,
)


def inline_formset(response, prefix):
    """Return the inline formset with ``prefix``.

    The category admin stacks the sub category inline above the saree one, so
    the saree formset is no longer at a fixed position in the list.
    """
    for inline in response.context["inline_admin_formsets"]:
        if inline.formset.prefix == prefix:
            return inline.formset
    raise AssertionError(f"no inline formset with prefix {prefix!r}")


def inline_management_data(response):
    """Empty management-form data for every inline rendered on ``response``.

    Django validates each inline formset separately, so a save payload has to
    satisfy all of them, not just the one a test cares about.
    """
    data = {}
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        data.update(
            {
                f"{formset.prefix}-TOTAL_FORMS": str(formset.total_form_count()),
                f"{formset.prefix}-INITIAL_FORMS": str(formset.initial_form_count()),
                f"{formset.prefix}-MIN_NUM_FORMS": "0",
                f"{formset.prefix}-MAX_NUM_FORMS": "1000",
            }
        )
    return data


class StorePageTests(TestCase):
    def setUp(self):
        SiteSettings.objects.create(
            shop_name="Swathi Designers",
            address="18, Heritage Textile Street, Anna Nagar, Chennai",
            phone="+91 98765 43210",
            email="hello@sareeelegance.in",
        )
        customer = Customer.objects.create(name="Test Shopper", phone="9876543210")
        session = self.client.session
        session["customer_id"] = customer.pk
        session.save()

    def test_about_page_uses_shared_navigation_and_commits(self):
        response = self.client.get(reverse("store:about"))
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("About Us", content)
        self.assertIn("Fast Delivery", content)
        self.assertIn("24/7 Online Support", content)
        self.assertIn("Fast Exchange", content)
        self.assertIn("About Our Story", content)

    def test_catalog_page_renders_collection_banners(self):
        categories = [
            Category.objects.create(title="High Collection", tier=Category.Tier.HIGH, order=1),
            Category.objects.create(title="Medium Collection", tier=Category.Tier.MEDIUM, order=2),
            Category.objects.create(title="Basic Collection", tier=Category.Tier.BASIC, order=3),
        ]
        Saree.objects.create(
            category=categories[0],
            name="Banner Saree",
            price="1499",
            image="sarees/banner-saree.jpg",
        )

        response = self.client.get(reverse("store:catalog"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("catalog-page-banner", content)
        self.assertIn("Explore timeless weaves, graceful silk and everyday comfort", content)
        self.assertIn("category-banner-card", content)
        self.assertEqual(content.count("category-banner-card"), 3)
        self.assertIn("background-image:url('/media/sarees/banner-saree.jpg')", content)

    def test_about_page_uses_image_banner(self):
        Saree.objects.create(
            category=Category.objects.create(title="Collection", tier=Category.Tier.HIGH),
            name="About Banner Saree",
            price="1499",
            image="sarees/about-banner.jpg",
        )

        response = self.client.get(reverse("store:about"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("about-page-banner", content)
        self.assertIn("background-image:url('/media/sarees/about-banner.jpg')", content)

    def test_contact_page_saves_enquiry(self):
        response = self.client.post(
            reverse("store:contact"),
            {
                "name": "Test Customer",
                "email": "customer@example.com",
                "phone": "9876543210",
                "subject": "Product question",
                "message": "Please share more details.",
            },
        )
        self.assertRedirects(response, reverse("store:contact"))
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(ContactMessage.objects.first().subject, "Product question")

    def test_contact_page_rejects_a_phone_that_is_not_a_mobile_number(self):
        for phone in ("12345", "1234567890", "5876543210", "98765@3210"):
            with self.subTest(phone=phone):
                response = self.client.post(
                    reverse("store:contact"),
                    {
                        "name": "Test Customer",
                        "email": "customer@example.com",
                        "phone": phone,
                        "subject": "Product question",
                        "message": "Please share more details.",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Please give correct number.")
                self.assertEqual(ContactMessage.objects.count(), 0)

    def test_contact_page_phone_is_optional(self):
        response = self.client.post(
            reverse("store:contact"),
            {
                "name": "Test Customer",
                "email": "customer@example.com",
                "phone": "",
                "subject": "Product question",
                "message": "Please share more details.",
            },
        )

        self.assertRedirects(response, reverse("store:contact"))
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_terms_page_uses_shared_navigation(self):
        response = self.client.get(reverse("store:terms"))
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Terms and Conditions", content)
        self.assertIn("Product information", content)

    def test_footer_quick_links_exclude_catalog_and_collections(self):
        Category.objects.create(title="Luxury Pure Silk", tier=Category.Tier.HIGH)
        Category.objects.create(title="Premium Collection", tier=Category.Tier.MEDIUM)
        Category.objects.create(title="Everyday Comfort", tier=Category.Tier.BASIC)

        response = self.client.get(reverse("store:home"))
        content = response.content.decode()
        footer = content.split('id="contact-section"', 1)[1].split("</footer>", 1)[0]

        self.assertNotIn(">All Catalog</a>", footer)
        self.assertNotIn(">Luxury Pure Silk</a>", footer)
        self.assertNotIn(">Premium Collection</a>", footer)
        self.assertNotIn(">Everyday Comfort</a>", footer)
        self.assertIn("About Us", footer)

    def test_seo_metadata_and_structured_data(self):
        seo, _ = SEO.objects.get_or_create()
        seo.default_title = "Swathi Designers SEO Test"
        seo.default_description = "Search-optimized saree shopping description."
        seo.default_keywords = "test sarees, online sarees"
        seo.save()

        response = self.client.get(reverse("store:home"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>Swathi Designers SEO Test</title>", content)
        self.assertIn('name="description" content="Search-optimized saree shopping description."', content)
        self.assertIn('name="keywords" content="test sarees, online sarees"', content)
        self.assertIn('rel="canonical" href="http://testserver/home/"', content)
        self.assertIn('property="og:title"', content)
        self.assertIn('"@type": "WebSite"', content)

    def test_product_page_includes_product_schema(self):
        category = Category.objects.create(title="Silk Collection", tier=Category.Tier.HIGH)
        saree = Saree.objects.create(
            category=category,
            name="SEO Silk Saree",
            price="2499",
            image="sarees/seo-silk.jpg",
            description="A premium silk saree for weddings and celebrations.",
        )

        response = self.client.get(reverse("store:saree_detail", kwargs={"slug": saree.slug}))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('property="og:type" content="product"', content)
        self.assertIn('"@type": "Product"', content)
        self.assertIn("SEO Silk Saree", content)

    def test_seo_sitemap_and_robots(self):
        sitemap_response = self.client.get("/sitemap.xml")
        robots_response = self.client.get("/robots.txt")

        self.assertEqual(sitemap_response.status_code, 200)
        self.assertIn("/home/", sitemap_response.content.decode())
        self.assertIn("/catalog/", sitemap_response.content.decode())
        self.assertEqual(robots_response.status_code, 200)
        self.assertIn("Sitemap:", robots_response.content.decode())

    def test_navigation_order(self):
        response = self.client.get(reverse("store:home"))
        content = response.content.decode()
        positions = [
            content.index(label)
            for label in ("Home</a>", "About Us</a>", "Collection&amp;Services", "Contact Us</a>")
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn(">All Catalog</a>", content)


class CheckoutNameValidationTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.objects.create(shop_name="Swathi Designers")
        customer = Customer.objects.create(name="Checkout Customer", phone="9876543210")
        self.category = Category.objects.create(title="Checkout Collection", tier=Category.Tier.HIGH)
        self.saree = Saree.objects.create(
            category=self.category,
            name="Checkout Saree",
            price="1499.00",
            image_url="https://images.example/checkout-saree.jpg",
        )
        session = self.client.session
        session["customer_id"] = customer.pk
        session["cart"] = {str(self.saree.pk): 1}
        session.save()
        self.checkout_url = reverse("store:checkout")

    def _post(self, name, phone="9876543210", city="Chennai", state="Tamil Nadu"):
        return self.client.post(
            self.checkout_url,
            {
                "name": name,
                "phone": phone,
                "email": "",
                "address": "18 Heritage Street",
                "city": city,
                "state": state,
                "pincode": "600040",
                "payment_method": "qr",
            },
        )

    def test_numeric_or_symbol_only_names_are_rejected_without_creating_orders(self):
        for name in ("123445567890", "@#$%^//"):
            with self.subTest(name=name):
                response = self._post(name)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Please enter a valid name.")
                self.assertContains(response, f'value="{name}"')
                self.assertEqual(Order.objects.count(), 0)
                self.assertEqual(self.client.session["cart"], {str(self.saree.pk): 1})

    def test_name_with_letters_and_allowed_punctuation_can_create_order(self):
        response = self._post("Anne-Marie O'Neil")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get().name, "Anne-Marie O'Neil")

    def test_invalid_phone_values_are_rejected_without_creating_orders(self):
        for phone in (
            "qwerty",
            "98765@3210",
            "123456789",
            "12345678901",
            "+919876543210",
            "1234567890",
            "5234567890",
            "5876543210",
            "0123456789",
        ):
            with self.subTest(phone=phone):
                response = self._post("Valid Customer", phone=phone)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Please give correct number.")
                self.assertContains(response, f'value="{phone}"')
                self.assertEqual(Order.objects.count(), 0)
                self.assertEqual(self.client.session["cart"], {str(self.saree.pk): 1})

    def test_every_valid_mobile_start_creates_an_order(self):
        for name, phone in (
            ("Six Start", "6123456789"),
            ("Seven Start", "7123456789"),
            ("Eight Start", "8123456789"),
            ("Nine Start", "9876543210"),
        ):
            with self.subTest(phone=phone):
                Order.objects.all().delete()
                session = self.client.session
                session["cart"] = {str(self.saree.pk): 1}
                session.save()
                response = self._post(name, phone=phone)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(Order.objects.get().phone, phone)

    def test_exactly_ten_digit_phone_can_create_order(self):
        response = self._post("Valid Customer", phone="9876543210")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get().phone, "9876543210")

    def test_city_and_state_reject_special_character_only_values(self):
        for field in ("city", "state"):
            with self.subTest(field=field):
                location_fields = {field: "#"}
                response = self._post("Valid Customer", **location_fields)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f"Please enter a valid {field} name.")
                self.assertContains(response, 'value="#"')
                self.assertEqual(Order.objects.count(), 0)
                self.assertEqual(self.client.session["cart"], {str(self.saree.pk): 1})

    def test_blank_optional_state_is_allowed(self):
        response = self._post("Valid Customer", state="")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get().state, "")


class CustomerLoginIdentityTests(TestCase):
    def setUp(self):
        SiteSettings.objects.create(shop_name="Swathi Designers")
        self.customer = Customer.objects.create(name="User A", phone="9876543210")

    def test_mismatched_name_is_rejected_and_leaves_the_account_untouched(self):
        response = self.client.post(
            reverse("store:login"),
            {"name": "User B", "phone": self.customer.phone},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered under a different name")
        self.assertNotIn("customer_id", self.client.session)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "User A")

    def test_matching_name_logs_into_existing_customer_without_renaming(self):
        response = self.client.post(
            reverse("store:login"),
            {"name": "  user   a ", "phone": self.customer.phone},
        )

        self.assertRedirects(response, reverse("store:home"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "User A")
        self.assertEqual(self.client.session["customer_id"], self.customer.pk)

    def test_new_phone_number_registers_a_customer_in_one_step(self):
        response = self.client.post(
            reverse("store:login"),
            {"name": "New Shopper", "phone": "91234 56789"},
        )

        self.assertRedirects(response, reverse("store:home"))
        created = Customer.objects.get(phone="9123456789")
        self.assertEqual(created.name, "New Shopper")
        self.assertEqual(self.client.session["customer_id"], created.pk)

    def test_login_page_has_no_otp_step(self):
        response = self.client.get(reverse("store:login"))
        content = response.content.decode()

        self.assertContains(response, "Welcome to Swathi Designers")
        self.assertNotIn("otp", content.lower())

    def test_invalid_phone_is_rejected_without_signing_in(self):
        for phone in ("12345", "1234567890", "5876543210", "abcdefghij"):
            with self.subTest(phone=phone):
                self.client.session.flush()
                response = self.client.post(
                    reverse("store:login"),
                    {"name": "User A", "phone": phone},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Please give correct number.")
                self.assertNotIn("customer_id", self.client.session)


class AdminPasswordResetTests(TestCase):
    def test_admin_login_displays_a_working_password_reset_link(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Forgotten your login credentials?")
        self.assertContains(response, reverse("admin_password_reset"))
        self.assertEqual(self.client.get(reverse("admin_password_reset")).status_code, 200)


class SiteSettingsAdminValidationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("staff", "staff@example.com", "pw12345!")
        self.client.force_login(self.admin)
        self.settings_obj = SiteSettings.objects.create(shop_name="Swathi Designers")
        self.url = reverse("admin:store_sitesettings_change", args=[self.settings_obj.pk])

    def _post(self, **overrides):
        payload = {
            "shop_name": "Swathi Designers",
            "tagline": "Handwoven silk",
            "phone": "9876543210",
            "email": "hello@sareeelegance.in",
            "address": "18, Heritage Textile Street, Anna Nagar, Chennai",
            "map_embed_url": "https://www.google.com/maps/embed?pb=abc",
            "whatsapp": "919876543210",
            "shipping_fee": "79.00",
            "free_shipping_above": "999.00",
        }
        payload.update(overrides)
        return self.client.post(self.url, payload)

    def test_blank_mandatory_fields_are_rejected(self):
        response = self._post(phone="", email="", address="", map_embed_url="", whatsapp="")

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        for field in ("phone", "email", "address", "map_embed_url", "whatsapp"):
            with self.subTest(field=field):
                self.assertIn(field, form.errors)
                self.assertEqual(form.errors[field], ["This field is required."])

    def test_whitespace_only_values_are_treated_as_blank(self):
        response = self._post(phone="   ", email="   ", address="   ", map_embed_url="  ", whatsapp="  ")

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        for field in ("phone", "email", "address", "map_embed_url", "whatsapp"):
            with self.subTest(field=field):
                self.assertIn(field, form.errors)

    def test_invalid_phone_and_whatsapp_are_rejected(self):
        response = self._post(phone="9100048@", whatsapp="abc")

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertEqual(form.errors["phone"], ["Enter a valid phone number with exactly 10 digits."])
        self.assertEqual(
            form.errors["whatsapp"],
            ["Enter a valid WhatsApp number: 10-15 digits including country code, no spaces."],
        )

    def test_phone_rejects_values_with_fewer_or_more_than_ten_digits(self):
        for phone in ("123456789", "12345678901", "+919876543210", " 9876543210 "):
            with self.subTest(phone=phone):
                response = self._post(phone=phone)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["adminform"].form.errors["phone"],
                    ["Enter a valid phone number with exactly 10 digits."],
                )

    def test_non_http_map_embed_url_is_rejected(self):
        response = self._post(map_embed_url="javascript:alert(1)")

        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertEqual(
            form.errors["map_embed_url"],
            ["Enter a valid map embed URL starting with http:// or https://."],
        )

    def test_valid_values_are_saved_and_optional_fields_stay_optional(self):
        response = self._post()

        self.assertEqual(response.status_code, 302)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.phone, "9876543210")
        self.assertEqual(self.settings_obj.email, "hello@sareeelegance.in")
        self.assertEqual(self.settings_obj.whatsapp, "919876543210")
        self.assertEqual(self.settings_obj.address, "18, Heritage Textile Street, Anna Nagar, Chennai")
        self.assertEqual(self.settings_obj.map_embed_url, "https://www.google.com/maps/embed?pb=abc")
        self.assertEqual(self.settings_obj.facebook, "")
        self.assertEqual(self.settings_obj.free_shipping_above, Decimal("999.00"))
        self.assertEqual(self.settings_obj.shipping_fee, Decimal("79.00"))

    def test_whatsapp_is_normalised_to_digits(self):
        self._post(whatsapp="+91 98765-43210")

        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.whatsapp, "919876543210")


class OrderItemRemovalTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("staff", "staff@example.com", "pw12345!")
        self.client.force_login(self.admin)
        self.order = Order.objects.create(
            order_id="SE202609282202599",
            name="Naveen",
            phone="9876543210",
            address="18, Heritage Textile Street, Anna Nagar, Chennai",
            city="Chennai",
            pincode="600040",
            payment_method=Order.PaymentMethod.COD,
            subtotal=Decimal("5498.00"),
            delivery_charge=Decimal("0.00"),
            gst=Decimal("274.90"),
            total=Decimal("5772.90"),
        )
        self.banarasi = OrderItem.objects.create(
            order=self.order, name="Banarasi Moonlight Brocade", price=Decimal("2499.00"), quantity=1
        )
        self.patola = OrderItem.objects.create(
            order=self.order, name="Patola Heritage Silk", price=Decimal("2999.00"), quantity=1
        )
        self.change_url = reverse("admin:store_order_change", args=[self.order.pk])

    def _remove_url(self, item):
        return reverse("admin:store_order_remove_item", args=[self.order.pk, item.pk])

    def test_order_page_offers_per_item_removal_instead_of_delete_checkbox(self):
        response = self.client.get(self.change_url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(">Delete?</th>", content)
        self.assertIn("store/admin/selected-inline-delete.js", content)
        self.assertIn("Remove item", content)
        self.assertIn(self._remove_url(self.banarasi), content)
        self.assertIn(self._remove_url(self.patola), content)

    def test_removing_one_item_keeps_the_order_and_other_items(self):
        response = self.client.post(self._remove_url(self.banarasi))

        self.assertRedirects(response, self.change_url)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.order.refresh_from_db()
        self.assertEqual([item.name for item in self.order.items.all()], ["Patola Heritage Silk"])

    def test_removing_an_item_recalculates_order_totals(self):
        self.client.post(self._remove_url(self.banarasi))

        self.order.refresh_from_db()
        self.assertEqual(self.order.subtotal, Decimal("2999.00"))
        self.assertEqual(self.order.gst, Decimal("149.95"))
        self.assertEqual(self.order.total, Decimal("3148.95"))
        self.assertEqual(self.order.delivery_charge, Decimal("0.00"))

    def test_removing_an_item_recalculates_delivery_charge(self):
        self.client.post(self._remove_url(self.banarasi))

        self.order.refresh_from_db()
        self.assertEqual(self.order.subtotal, Decimal("2999.00"))
        self.assertEqual(self.order.delivery_charge, Decimal("0.00"))
        self.assertEqual(self.order.gst, Decimal("149.95"))
        self.assertEqual(self.order.total, Decimal("3148.95"))

    def test_removing_an_item_can_reintroduce_shipping_charge(self):
        cheap = OrderItem.objects.create(
            order=self.order, name="Cotton Everyday Saree", price=Decimal("500.00"), quantity=1
        )

        self.client.post(self._remove_url(self.banarasi))
        self.client.post(self._remove_url(self.patola))
        self.order.refresh_from_db()

        self.assertEqual([item.name for item in self.order.items.all()], ["Cotton Everyday Saree"])
        self.assertEqual(self.order.subtotal, Decimal("500.00"))
        self.assertEqual(self.order.delivery_charge, Decimal("79.00"))
        self.assertEqual(self.order.gst, Decimal("25.00"))
        self.assertEqual(self.order.total, Decimal("604.00"))
        self.assertTrue(cheap.pk)

    def test_remove_item_confirmation_page_is_scoped_to_single_item(self):
        response = self.client.get(self._remove_url(self.banarasi))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Banarasi Moonlight Brocade", content)
        self.assertIn("removes only the selected line item", content)

    def test_cannot_remove_the_last_remaining_item(self):
        self.client.post(self._remove_url(self.banarasi))
        remaining = self.order.items.get()

        response = self.client.post(self._remove_url(remaining), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order.items.count(), 1)
        self.assertContains(response, "must keep at least one item")

    def test_order_delete_requires_typing_the_order_id(self):
        delete_url = reverse("admin:store_order_delete", args=[self.order.pk])

        response = self.client.post(delete_url, {"post": "yes", "confirm_order_id": ""})

        self.assertRedirects(response, delete_url)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_order_delete_succeeds_with_matching_order_id(self):
        delete_url = reverse("admin:store_order_delete", args=[self.order.pk])

        response = self.client.post(delete_url, {"post": "yes", "confirm_order_id": self.order.order_id})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(pk=self.order.pk).exists())
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_order_delete_confirmation_warns_it_removes_every_item(self):
        response = self.client.get(reverse("admin:store_order_delete", args=[self.order.pk]))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("deletes the ENTIRE order", content)
        self.assertIn('name="confirm_order_id"', content)

    def test_order_delete_with_inline_selection_confirms_and_removes_only_selected_items(self):
        delete_url = reverse("admin:store_order_delete", args=[self.order.pk])
        selected_url = f"{delete_url}?selected_items={self.banarasi.pk}"

        response = self.client.get(selected_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Banarasi Moonlight Brocade")
        self.assertNotContains(response, "Patola Heritage Silk")
        self.assertContains(response, "order and all unselected items will be kept")

        response = self.client.post(
            selected_url,
            {"delete_selected_items": "yes", "selected_items": str(self.banarasi.pk)},
        )

        self.assertRedirects(response, self.change_url)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertFalse(OrderItem.objects.filter(pk=self.banarasi.pk).exists())
        self.assertTrue(OrderItem.objects.filter(pk=self.patola.pk).exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.subtotal, Decimal("2999.00"))
        self.assertEqual(self.order.gst, Decimal("149.95"))
        self.assertEqual(self.order.total, Decimal("3148.95"))

    def test_order_selected_delete_cannot_remove_every_item(self):
        delete_url = reverse("admin:store_order_delete", args=[self.order.pk])
        selected_url = f"{delete_url}?selected_items={self.banarasi.pk}&selected_items={self.patola.pk}"

        response = self.client.get(selected_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An order must keep at least one item")
        self.assertNotContains(response, "Yes, remove selected items")


class CategorySareeRemovalTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("staff", "staff@example.com", "pw12345!")
        self.client.force_login(self.admin)
        self.category = Category.objects.create(title="Silk Collection", tier=Category.Tier.HIGH)
        self.other_category = Category.objects.create(title="Cotton Collection", tier=Category.Tier.BASIC)
        self.first_saree = Saree.objects.create(
            category=self.category,
            name="Banarasi Silk",
            price="2499",
            image_url="https://images.example/banarasi.jpg",
        )
        self.second_saree = Saree.objects.create(
            category=self.category,
            name="Kanjivaram Silk",
            price="2999",
            image_url="https://images.example/kanjivaram.jpg",
        )
        self.foreign_saree = Saree.objects.create(
            category=self.other_category,
            name="Cotton Floral",
            price="999",
            image_url="https://images.example/cotton.jpg",
        )
        self.change_url = reverse("admin:store_category_change", args=[self.category.pk])
        self.delete_url = reverse("admin:store_category_delete", args=[self.category.pk])

    def _remove_url(self, saree, category=None):
        return reverse(
            "admin:store_category_remove_saree",
            args=[(category or self.category).pk, saree.pk],
        )

    def test_category_inline_offers_per_saree_removal(self):
        response = self.client.get(self.change_url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(self._remove_url(self.first_saree), content)
        self.assertIn(self._remove_url(self.second_saree), content)
        self.assertIn(">Delete?</th>", content)
        self.assertIn("store/admin/selected-inline-delete.js", content)

    def test_inline_delete_removes_only_selected_saree_and_keeps_category(self):
        response = self.client.get(self.change_url)
        formset = inline_formset(response, "sarees")
        prefix = formset.prefix
        data = {
            "title": self.category.title,
            "tier": self.category.tier,
            "slug": self.category.slug,
            "subtitle": self.category.subtitle,
            "image": "",
            "order": str(self.category.order),
            "_save": "Save",
            **inline_management_data(response),
            f"{prefix}-0-id": str(self.first_saree.pk),
            f"{prefix}-0-DELETE": "on",
            f"{prefix}-1-id": str(self.second_saree.pk),
        }

        response = self.client.post(self.change_url, data)

        self.assertRedirects(response, reverse("admin:store_category_changelist"))
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        self.assertFalse(Saree.objects.filter(pk=self.first_saree.pk).exists())
        self.assertTrue(Saree.objects.filter(pk=self.second_saree.pk).exists())

    def test_category_delete_with_inline_selection_confirms_only_selected_sarees(self):
        selected_url = f"{self.delete_url}?selected_sarees={self.first_saree.pk}"

        response = self.client.get(selected_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Banarasi Silk")
        self.assertNotContains(response, "Kanjivaram Silk")
        self.assertContains(response, "category and all unselected sarees will be kept")

        response = self.client.post(
            selected_url,
            {"delete_selected_sarees": "yes", "selected_sarees": str(self.first_saree.pk)},
        )

        self.assertRedirects(response, self.change_url)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        self.assertFalse(Saree.objects.filter(pk=self.first_saree.pk).exists())
        self.assertTrue(Saree.objects.filter(pk=self.second_saree.pk).exists())

    def test_saree_removal_confirmation_is_scoped_to_one_saree(self):
        response = self.client.get(self._remove_url(self.first_saree))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Banarasi Silk", content)
        self.assertIn("all of its other sarees are kept", content)

    def test_removing_one_saree_keeps_category_and_other_sarees(self):
        response = self.client.post(self._remove_url(self.first_saree))

        self.assertRedirects(response, self.change_url)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        self.assertFalse(Saree.objects.filter(pk=self.first_saree.pk).exists())
        self.assertTrue(Saree.objects.filter(pk=self.second_saree.pk).exists())

    def test_saree_from_another_category_cannot_be_removed(self):
        response = self.client.post(self._remove_url(self.foreign_saree), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That saree is no longer in this category.")
        self.assertTrue(Saree.objects.filter(pk=self.foreign_saree.pk).exists())

    def test_category_delete_confirmation_requires_exact_title(self):
        response = self.client.get(self.delete_url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("deletes the ENTIRE category", content)
        self.assertIn('name="confirm_category_title"', content)
        self.assertIn("Banarasi Silk", content)

        response = self.client.post(
            self.delete_url,
            {"post": "yes", "confirm_category_title": "silk collection"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        self.assertEqual(self.category.sarees.count(), 2)

    def test_category_delete_with_exact_title_removes_category_and_sarees(self):
        response = self.client.post(
            self.delete_url,
            {"post": "yes", "confirm_category_title": self.category.title},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())
        self.assertFalse(Saree.objects.filter(category_id=self.category.pk).exists())


class FeaturedSareeAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("staff", "staff@example.com", "pw12345!")
        self.client.force_login(self.admin)
        SiteSettings.objects.create(shop_name="Swathi Designers")
        self.category = Category.objects.create(title="Featured Collection", tier=Category.Tier.HIGH)
        self.unfeatured = Saree.objects.create(
            category=self.category,
            name="Unfeatured Saree",
            price="1499",
            image_url="https://images.example/unfeatured.jpg",
            is_featured=True,
        )
        self.featured = Saree.objects.create(
            category=self.category,
            name="Featured Saree",
            price="1999",
            image_url="https://images.example/featured.jpg",
            is_featured=True,
        )

    def test_unchecking_inline_featured_removes_saree_from_homepage(self):
        change_url = reverse("admin:store_category_change", args=[self.category.pk])
        response = self.client.get(change_url)
        formset = inline_formset(response, "sarees")
        prefix = formset.prefix

        self.assertFalse(formset.forms[0].fields["is_featured"].disabled)
        payload = {
            "title": self.category.title,
            "tier": self.category.tier,
            "slug": self.category.slug,
            "subtitle": self.category.subtitle,
            "image": "",
            "order": str(self.category.order),
            "_save": "Save",
            **inline_management_data(response),
            f"{prefix}-0-id": str(self.unfeatured.pk),
            f"{prefix}-1-id": str(self.featured.pk),
            f"{prefix}-1-is_featured": "on",
        }

        response = self.client.post(change_url, payload)

        self.assertRedirects(response, reverse("admin:store_category_changelist"))
        self.unfeatured.refresh_from_db()
        self.featured.refresh_from_db()
        self.assertFalse(self.unfeatured.is_featured)
        self.assertTrue(self.featured.is_featured)

        homepage = self.client.get(reverse("store:home"))
        self.assertNotContains(homepage, "Unfeatured Saree")
        self.assertContains(homepage, "Featured Saree")


class CategoryCreationAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("staff", "staff@example.com", "pw12345!")
        self.client.force_login(self.admin)
        SiteSettings.objects.create(shop_name="Swathi Designers")
        customer = Customer.objects.create(name="Admin Shopper", phone="9876543210")
        session = self.client.session
        session["customer_id"] = customer.pk
        session.save()
        self.add_url = reverse("admin:store_category_add")
        self.media_dir = tempfile.TemporaryDirectory()
        self.settings_override = self.settings(MEDIA_ROOT=self.media_dir.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)

    def _post_category(self, title, tier, saree=None, slug=""):
        add_page = self.client.get(self.add_url)
        formset = inline_formset(add_page, "sarees")
        prefix = formset.prefix
        total_forms = 1 if saree else 0
        data = {
            "title": title,
            "tier": tier,
            "slug": slug,
            "subtitle": "",
            "image": "",
            "order": "0",
            "_save": "Save",
            **inline_management_data(add_page),
        }
        data[f"{prefix}-TOTAL_FORMS"] = str(total_forms)
        if saree:
            data.update(
                {
                    f"{prefix}-0-name": saree["name"],
                    f"{prefix}-0-product_id": saree.get("product_id", "NC-1001"),
                    f"{prefix}-0-price": saree["price"],
                    f"{prefix}-0-mrp": "",
                    f"{prefix}-0-fabric": "Silk",
                    f"{prefix}-0-description": "A new collection saree.",
                    f"{prefix}-0-is_featured": "",
                }
            )
            data[f"{prefix}-0-image"] = saree["image"]
        return self.client.post(self.add_url, data)

    def test_category_can_reuse_an_existing_tier(self):
        Category.objects.create(title="First High Collection", tier=Category.Tier.HIGH)

        response = self._post_category("Second High Collection", Category.Tier.HIGH)

        self.assertRedirects(response, reverse("admin:store_category_changelist"))
        self.assertEqual(Category.objects.filter(tier=Category.Tier.HIGH).count(), 2)

    def test_category_with_duplicate_prepopulated_slug_gets_unique_slug(self):
        Category.objects.create(title="Kalankari", tier=Category.Tier.BASIC)

        response = self._post_category("Kalankari", Category.Tier.BASIC, slug="kalankari")

        self.assertRedirects(response, reverse("admin:store_category_changelist"))
        category = Category.objects.get(title="Kalankari", slug="kalankari-2")
        self.assertEqual(category.tier, Category.Tier.BASIC)

    def test_new_category_inline_creates_saree_with_image_for_storefront(self):
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="red").save(image_buffer, format="PNG")
        image = SimpleUploadedFile("new-collection.png", image_buffer.getvalue(), content_type="image/png")

        response = self._post_category(
            "New Silk Collection",
            Category.Tier.HIGH,
            {"name": "New Collection Saree", "product_id": "NC-1001", "price": "1499.00", "image": image},
        )

        self.assertRedirects(response, reverse("admin:store_category_changelist"))
        category = Category.objects.get(title="New Silk Collection")
        saree = category.sarees.get()
        self.assertEqual(saree.name, "New Collection Saree")
        self.assertEqual(saree.price, Decimal("1499.00"))
        self.assertEqual(saree.image.name, "sarees/new-collection.png")

        storefront = self.client.get(reverse("store:category_detail", kwargs={"slug": category.slug}))
        self.assertEqual(storefront.status_code, 200)
        self.assertContains(storefront, "New Collection Saree")
        self.assertContains(storefront, "/media/sarees/new-collection.png")

    def test_existing_category_has_editable_fields_for_new_inline_saree(self):
        category = Category.objects.create(title="Existing Collection", tier=Category.Tier.HIGH)
        Saree.objects.create(
            category=category,
            name="Existing Saree",
            price="999",
            image="sarees/existing-saree.jpg",
        )

        response = self.client.get(reverse("admin:store_category_change", args=[category.pk]))
        formset = inline_formset(response, "sarees")
        empty_form = formset.empty_form
        existing_form = formset.forms[0]

        self.assertEqual(response.status_code, 200)
        for field_name in ("name", "product_id", "price", "mrp", "fabric", "description", "image", "image_url", "is_featured"):
            with self.subTest(field=field_name):
                self.assertFalse(empty_form.fields[field_name].disabled)
                self.assertEqual(existing_form.fields[field_name].disabled, field_name != "is_featured")

    def test_existing_category_can_add_saree_with_image_url(self):
        category = Category.objects.create(title="URL Image Collection", tier=Category.Tier.MEDIUM)
        change_url = reverse("admin:store_category_change", args=[category.pk])
        response = self.client.get(change_url)
        prefix = inline_formset(response, "sarees").prefix
        data = {
            "title": category.title,
            "tier": category.tier,
            "slug": category.slug,
            "subtitle": "",
            "image": "",
            "order": "0",
            "_save": "Save",
            **inline_management_data(response),
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-0-name": "URL Image Saree",
            f"{prefix}-0-product_id": "URL-1001",
            f"{prefix}-0-price": "1799.00",
            f"{prefix}-0-mrp": "1999.00",
            f"{prefix}-0-fabric": "Silk",
            f"{prefix}-0-description": "A saree with a remote image.",
            f"{prefix}-0-image_url": "https://images.example/saree.jpg",
            f"{prefix}-0-is_featured": "",
        }

        response = self.client.post(change_url, data)

        self.assertRedirects(response, reverse("admin:store_category_changelist"))
        saree = category.sarees.get()
        self.assertEqual(saree.image_source, "https://images.example/saree.jpg")
        storefront = self.client.get(reverse("store:category_detail", kwargs={"slug": category.slug}))
        self.assertEqual(storefront.status_code, 200)
        self.assertContains(storefront, "URL Image Saree")
        self.assertContains(storefront, "https://images.example/saree.jpg")


class SEOAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("seoadmin", "seo@example.com", "admin123")
        self.client.force_login(self.admin_user)

    def test_seo_form_shows_every_seo_box_in_order(self):
        seo = SEO.objects.create(site_name="Swathi Designers")

        response = self.client.get(reverse("admin:store_seo_change", args=[seo.pk]))
        form = response.context["adminform"].form

        self.assertEqual(
            list(form.fields),
            [
                "page_name",
                "site_name",
                "default_title",
                "default_page_description",
                "meta_title",
                "default_description",
                "default_keywords",
                "google_site_verification",
            ],
        )
        self.assertNotIn("robots_extra", form.fields)
        self.assertEqual(list(response.context["adminform"].readonly_fields), ["updated_at"])

    def test_seo_form_shows_the_requested_labels(self):
        seo = SEO.objects.create(site_name="Swathi Designers")

        content = self.client.get(reverse("admin:store_seo_change", args=[seo.pk])).content.decode()

        for label in (
            "Page name",
            "Site name",
            "Default title",
            "Default description",
            "Meta title",
            "Meta Description",
            "Meta keywords",
            "Google site Verification",
            "Updated time",
        ):
            with self.subTest(label=label):
                self.assertIn(label, content)
        self.assertNotIn("Robots extra", content)

    def test_updated_time_is_filled_in_automatically_on_save(self):
        seo = SEO.objects.create(site_name="Swathi Designers")
        self.assertIsNotNone(seo.updated_at)

        self.client.post(
            reverse("admin:store_seo_change", args=[seo.pk]),
            {
                "page_name": "",
                "site_name": "Swathi Designers",
                "default_title": "Kanjivaram Silk Sarees",
                "default_page_description": "",
                "meta_title": "",
                "default_description": "Handloom silk sarees.",
                "default_keywords": "kanjivaram",
                "google_site_verification": "",
            },
        )

        seo.refresh_from_db()
        self.assertGreater(seo.updated_at, self.admin_user.date_joined)

    def test_add_button_is_always_available(self):
        SEO.objects.create(site_name="Swathi Designers")

        response = self.client.get(reverse("admin:store_seo_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:store_seo_add"))

    def test_add_form_opens_completely_blank(self):
        SEO.objects.create(
            page_name="Home Page",
            site_name="Swathi Designers",
            default_title="Saved Title",
            default_page_description="Saved description.",
            meta_title="Saved meta title",
            default_description="Saved meta description.",
            default_keywords="saved, keywords",
            google_site_verification="savedcode",
        )

        content = self.client.get(reverse("admin:store_seo_add")).content.decode()

        for saved in (
            "Home Page",
            "Swathi Designers",
            "Saved Title",
            "Saved description.",
            "Saved meta title",
            "Saved meta description.",
            "saved, keywords",
            "savedcode",
        ):
            with self.subTest(value=saved):
                self.assertNotIn(f'value="{saved}"', content)

    def test_add_form_has_no_model_defaults_prefilled(self):
        SEO.objects.all().delete()

        response = self.client.get(reverse("admin:store_seo_add"))

        for name, field in response.context["adminform"].form.fields.items():
            with self.subTest(field=name):
                self.assertEqual(field.initial, "")

    def test_saving_seo_stores_every_box(self):
        seo = SEO.objects.create(site_name="Swathi Designers")

        response = self.client.post(
            reverse("admin:store_seo_change", args=[seo.pk]),
            {
                "page_name": "Storefront Home",
                "site_name": "Swathi Designers",
                "default_title": "Kanjivaram Silk Sarees",
                "default_page_description": "A short shop summary.",
                "meta_title": "Silk Sarees | Swathi Designers",
                "default_description": "Handloom silk sarees for weddings.",
                "default_keywords": "kanjivaram, silk sarees, wedding saree",
                "google_site_verification": "google123abc",
            },
        )

        self.assertEqual(response.status_code, 302)
        seo.refresh_from_db()
        self.assertEqual(seo.page_name, "Storefront Home")
        self.assertEqual(seo.default_title, "Kanjivaram Silk Sarees")
        self.assertEqual(seo.default_page_description, "A short shop summary.")
        self.assertEqual(seo.meta_title, "Silk Sarees | Swathi Designers")
        self.assertEqual(seo.default_description, "Handloom silk sarees for weddings.")
        self.assertEqual(seo.default_keywords, "kanjivaram, silk sarees, wedding saree")
        self.assertEqual(seo.google_site_verification, "google123abc")
        self.assertEqual(str(seo), "Storefront Home")

    def test_the_newest_added_row_is_the_one_the_site_uses(self):
        SEO.objects.create(default_title="Older Row Title", default_description="Older row description.")
        newest = SEO.objects.create(
            page_name="Newest Page",
            default_title="Newest Row Title",
            default_description="Newest row description.",
        )

        self.assertEqual(SEO.current(), newest)

        content = self.client.get(reverse("store:home")).content.decode()

        self.assertIn("Newest Row Title", content)
        self.assertIn("Newest row description.", content)
        self.assertNotIn("Older Row Title", content)


class SareeProductIdTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("pidadmin", "pid@example.com", "admin123")
        self.client.force_login(self.admin_user)
        self.category = Category.objects.create(title="Silk Sarees", tier=Category.Tier.HIGH)

    def test_add_saree_form_offers_a_product_id_box(self):
        response = self.client.get(reverse("admin:store_saree_add"))
        form = response.context["adminform"].form

        self.assertIn("product_id", form.fields)
        self.assertContains(response, "Product id")

    def test_product_id_is_saved_with_the_saree(self):
        response = self.client.post(
            reverse("admin:store_saree_add"),
            {
                "category": self.category.pk,
                "subcategory": "",
                "name": "Kanjivaram Gold Silk",
                "product_id": "SD-SRK-1001",
                "price": "8999.00",
                "mrp": "",
                "fabric": "Silk",
                "description": "A wedding saree.",
                "image_url": "https://images.example/saree.jpg",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Saree.objects.get().product_id, "SD-SRK-1001")

    def test_product_id_is_required(self):
        response = self.client.post(
            reverse("admin:store_saree_add"),
            {
                "category": self.category.pk,
                "subcategory": "",
                "name": "Cotton Everyday Saree",
                "product_id": "",
                "price": "1499.00",
                "mrp": "",
                "fabric": "Cotton",
                "description": "A daily wear saree.",
                "image_url": "https://images.example/cotton.jpg",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Saree.objects.count(), 0)
        self.assertContains(response, "Enter a product ID of 4 to 220 characters.")

    def test_product_id_needs_at_least_four_characters(self):
        response = self.client.post(
            reverse("admin:store_saree_add"),
            {
                "category": self.category.pk,
                "subcategory": "",
                "name": "Cotton Everyday Saree",
                "product_id": "SD1",
                "price": "1499.00",
                "mrp": "",
                "fabric": "Cotton",
                "description": "A daily wear saree.",
                "image_url": "https://images.example/cotton.jpg",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Saree.objects.count(), 0)
        self.assertContains(response, "Ensure this value has at least 4 characters")

    def test_product_id_accepts_four_characters_and_up_to_220(self):
        base = {
            "category": self.category.pk,
            "subcategory": "",
            "name": "Cotton Everyday Saree",
            "price": "1499.00",
            "mrp": "",
            "fabric": "Cotton",
            "description": "A daily wear saree.",
            "image_url": "https://images.example/cotton.jpg",
        }

        self.client.post(reverse("admin:store_saree_add"), {**base, "product_id": "SD01"})
        self.client.post(reverse("admin:store_saree_add"), {**base, "product_id": "X" * 220})
        self.client.post(reverse("admin:store_saree_add"), {**base, "product_id": "X" * 221})

        self.assertEqual(Saree.objects.count(), 2)
        self.assertEqual(Saree.objects.get(pk=1).product_id, "SD01")
        self.assertEqual(len(Saree.objects.get(pk=2).product_id), 220)

    def test_an_existing_product_without_a_product_id_can_still_be_saved(self):
        legacy = Saree.objects.create(
            category=self.category,
            name="Legacy Saree",
            price=Decimal("999.00"),
            image_url="https://images.example/legacy.jpg",
        )
        self.assertEqual(legacy.product_id, "")

        response = self.client.post(
            reverse("admin:store_saree_change", args=[legacy.pk]),
            {
                "category": self.category.pk,
                "subcategory": "",
                "name": "Legacy Saree",
                "product_id": "",
                "price": "1099.00",
                "mrp": "",
                "fabric": "Cotton",
                "description": "",
                "image_url": "https://images.example/legacy.jpg",
                "_save": "Save",
            },
        )

        legacy.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(legacy.price, Decimal("1099.00"))

    def test_a_product_id_of_one_character_cannot_be_added_to_an_existing_product(self):
        legacy = Saree.objects.create(
            category=self.category,
            name="Legacy Saree",
            price=Decimal("999.00"),
            image_url="https://images.example/legacy.jpg",
        )

        response = self.client.post(
            reverse("admin:store_saree_change", args=[legacy.pk]),
            {
                "category": self.category.pk,
                "subcategory": "",
                "name": "Legacy Saree",
                "product_id": "AB",
                "price": "1099.00",
                "mrp": "",
                "fabric": "Cotton",
                "description": "",
                "image_url": "https://images.example/legacy.jpg",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value has at least 4 characters")

    def test_category_saree_inline_offers_a_product_id_box(self):
        response = self.client.get(reverse("admin:store_category_change", args=[self.category.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("product_id", inline_formset(response, "sarees").empty_form.fields)


class BlankAddFormTests(TestCase):
    """Every "+ Add" page opens with empty text boxes across the admin."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser("blankadmin", "blank@example.com", "admin123")
        self.client.force_login(self.admin_user)

    def _add_pages(self):
        for model_admin in admin.site._registry.values():
            model = model_admin.model
            if model._meta.app_label != "store":
                continue
            url = reverse(f"admin:store_{model._meta.model_name}_add")
            response = self.client.get(url)
            if response.status_code == 200:
                yield model.__name__, response

    def test_every_add_page_has_blank_text_boxes(self):
        checked = 0
        for name, response in self._add_pages():
            form = response.context["adminform"].form
            for field_name, field in form.fields.items():
                model_field = form._meta.model._meta.get_field(field_name)
                if not isinstance(model_field, (models.CharField, models.TextField)):
                    continue
                if isinstance(field.widget, (forms.CheckboxInput, forms.Select, forms.RadioSelect)):
                    continue
                checked += 1
                with self.subTest(model=name, field=field_name):
                    self.assertEqual(field.initial, "")
        self.assertGreater(checked, 20)

    def test_required_controls_keep_their_defaults(self):
        category = Category.objects.create(title="Defaults Collection", tier=Category.Tier.HIGH)
        expected = {
            "store_category": {"order": 0},
            "store_banner": {"order": 0, "is_active": True},
            "store_orderitem": {"quantity": 1},
            "store_saree": {"is_featured": False},
        }
        for model_name, fields in expected.items():
            with self.subTest(model=model_name):
                form = self.client.get(reverse(f"admin:{model_name}_add")).context["adminform"].form
                for field_name, value in fields.items():
                    self.assertEqual(form.fields[field_name].initial, value)
        self.assertTrue(category.pk)

    def test_the_boilerplate_pages_open_empty(self):
        AboutPage.objects.create()
        TermsPage.objects.create()

        for url, saved_text in (
            (reverse("admin:store_aboutpage_add"), AboutPage._meta.get_field("story").default),
            (reverse("admin:store_termspage_add"), "For questions about an order"),
        ):
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                self.assertNotIn(saved_text[:60], content)

    def test_inline_empty_rows_open_blank(self):
        category = Category.objects.create(title="Inline Collection", tier=Category.Tier.HIGH)

        response = self.client.get(reverse("admin:store_category_change", args=[category.pk]))
        sarees = inline_formset(response, "sarees").empty_form

        for field_name in ("name", "product_id", "fabric", "description", "image_url"):
            with self.subTest(field=field_name):
                self.assertIn(sarees.fields[field_name].initial, ("", None))
        self.assertIs(sarees.fields["is_featured"].initial, False)

    def test_existing_rows_still_show_their_saved_values(self):
        seo = SEO.objects.create(page_name="Saved Page", site_name="Saved Site")

        form = self.client.get(reverse("admin:store_seo_change", args=[seo.pk])).context["adminform"].form

        self.assertEqual(form.initial["page_name"], "Saved Page")
        self.assertEqual(form.initial["site_name"], "Saved Site")


class SubCategoryInlineSareeTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("inlineadmin", "inline@example.com", "admin123")
        self.client.force_login(self.admin_user)
        self.category = Category.objects.create(title="Silk Sarees", tier=Category.Tier.HIGH)
        self.subcategory = SubCategory.objects.create(category=self.category, title="Kanjivaram")

    def test_saree_created_from_a_subcategory_inherits_the_collection(self):
        saree = Saree.objects.create(name="Kanjivaram Silk", subcategory=self.subcategory, price="2000")

        self.assertEqual(saree.category_id, self.category.pk)

    def test_adding_a_saree_on_the_subcategory_change_page_saves(self):
        response = self.client.post(
            reverse("admin:store_subcategory_change", args=[self.subcategory.pk]),
            {
                "category": self.category.pk,
                "title": self.subcategory.title,
                "slug": self.subcategory.slug,
                "subtitle": self.subcategory.subtitle,
                "image": "",
                "order": "0",
                "sarees-TOTAL_FORMS": "1",
                "sarees-INITIAL_FORMS": "0",
                "sarees-MIN_NUM_FORMS": "0",
                "sarees-MAX_NUM_FORMS": "1000",
                "sarees-0-subcategory": self.subcategory.pk,
                "sarees-0-name": "Banarasi Kumkum Silk",
                "sarees-0-product_id": "SL-1001",
                "sarees-0-price": "2177",
                "sarees-0-mrp": "2999",
                "sarees-0-fabric": "silk",
                "sarees-0-image": "",
                "sarees-0-image_url": "https://example.com/b.jpg",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Saree.objects.get(name="Banarasi Kumkum Silk")
        self.assertEqual(created.category_id, self.category.pk)
        self.assertEqual(created.subcategory_id, self.subcategory.pk)

class DiscountCalculationTests(TestCase):
    """The discount is worked out once, from the original amount, in one place."""

    def setUp(self):
        self.category = Category.objects.create(title="Discounts", tier=Category.Tier.HIGH)

    def _saree(self, **overrides):
        values = {
            "name": "Test Saree",
            "category": self.category,
            "price": Decimal("1000.00"),
            "mrp": Decimal("1000.00"),
            "image_url": "https://example.com/a.jpg",
        }
        values.update(overrides)
        saree = Saree(**values)
        saree.save()
        return saree

    def test_a_twenty_percent_discount_on_one_thousand(self):
        saree = self._saree(discount_percent=Decimal("20"))

        self.assertEqual(saree.mrp, Decimal("1000.00"))
        self.assertEqual(saree.price, Decimal("800.00"))
        self.assertEqual(saree.discount_amount, Decimal("200.00"))
        self.assertEqual(saree.final_amount, Decimal("800.00"))
        self.assertEqual(saree.original_amount - saree.discount_amount, saree.final_amount)

    def test_the_discount_is_applied_to_the_original_not_to_the_discounted_price(self):
        saree = self._saree(discount_percent=Decimal("20"))
        saree.save()

        self.assertEqual(saree.price, Decimal("800.00"))
        self.assertEqual(saree.discount_amount, Decimal("200.00"))

    def test_the_discount_is_never_applied_twice(self):
        saree = self._saree(discount_percent=Decimal("50"))
        for _ in range(3):
            saree.save()
            saree.refresh_from_db()

        self.assertEqual(saree.price, Decimal("500.00"))
        self.assertEqual(saree.discount_amount, Decimal("500.00"))

    def test_a_hundred_percent_discount_reaches_zero_but_never_below(self):
        self.assertEqual(self._saree(discount_percent=Decimal("100")).price, Decimal("0.00"))
        for percent in (Decimal("150"), Decimal("-25")):
            with self.subTest(percent=percent), self.assertRaises(ValidationError):
                self._saree(discount_percent=percent)

    def test_discount_without_mrp_preserves_the_original_and_is_applied_once(self):
        saree = self._saree(mrp=None, price=Decimal("2000.00"), discount_percent=Decimal("20"))

        self.assertEqual(saree.mrp, Decimal("2000.00"))
        self.assertEqual(saree.price, Decimal("1600.00"))
        self.assertEqual(saree.final_amount, Decimal("1600.00"))
        self.assertEqual(saree.discount_amount, Decimal("400.00"))

    def test_amounts_are_rounded_to_two_decimal_places(self):
        saree = self._saree(mrp=Decimal("999.00"), price=Decimal("799.00"))

        self.assertEqual(saree.discount_amount, Decimal("200.00"))
        self.assertEqual(saree.original_amount - saree.discount_amount, saree.final_amount)

    def test_an_original_below_the_price_never_produces_a_negative_final_amount(self):
        saree = self._saree(mrp=Decimal("1.05"), price=Decimal("1500.00"))

        self.assertEqual(saree.final_amount, Decimal("1500.00"))
        self.assertEqual(saree.discount_amount, Decimal("0.00"))
        self.assertGreaterEqual(saree.final_amount, Decimal("0.00"))

    def test_a_blank_discount_keeps_the_price_as_entered(self):
        saree = self._saree(mrp=Decimal("2999.00"), price=Decimal("2184.00"), discount_percent=None)

        self.assertEqual(saree.price, Decimal("2184.00"))
        self.assertEqual(saree.final_amount, Decimal("2184.00"))
        self.assertEqual(saree.original_amount, Decimal("2999.00"))
        self.assertEqual(saree.discount_amount, Decimal("815.00"))

    def test_a_discount_outside_zero_to_one_hundred_is_rejected(self):
        for percent in (Decimal("101"), Decimal("-1"), Decimal("250")):
            with self.subTest(percent=percent):
                saree = Saree(
                    name="Invalid Discount Saree",
                    category=self.category,
                    price=Decimal("1000.00"),
                    mrp=Decimal("1000.00"),
                    discount_percent=percent,
                    image_url="https://example.com/a.jpg",
                )
                with self.assertRaises(ValidationError) as caught:
                    saree.full_clean()
                self.assertIn("discount_percent", caught.exception.error_dict)
                with self.assertRaises(ValidationError):
                    saree.save()


class SareeCardDetailsTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(title="Card Details", tier=Category.Tier.HIGH)
        customer = Customer.objects.create(name="Card Shopper", phone="9876543210")
        session = self.client.session
        session["customer_id"] = customer.pk
        session.save()
        self.saree = Saree.objects.create(
            name="Card Saree",
            category=self.category,
            price=Decimal("1000.00"),
            mrp=Decimal("1250.00"),
            fabric="Silk",
            description="A soft mulberry silk saree with a luminous drape.",
            image_url="https://example.com/a.jpg",
        )

    def test_the_card_shows_only_the_name_and_price(self):
        content = self.client.get(reverse("store:category_detail", args=[self.category.slug])).content.decode()
        card = content.split("saree-card", 1)[1].split("</form>", 1)[0]

        self.assertIn("Card Saree", card)
        self.assertIn("1000.00", card)

    def test_the_card_hides_the_details_that_belong_on_the_product_page(self):
        content = self.client.get(reverse("store:category_detail", args=[self.category.slug])).content.decode()
        card = content.split("saree-card", 1)[1].split("</form>", 1)[0]

        self.assertNotIn("A soft mulberry silk saree", card)
        self.assertNotIn("6.3 metres", card)
        self.assertNotIn("Ready to ship in 24 hrs", card)
        self.assertNotIn("Free above", card)
        self.assertNotIn("saree-details", card)

    def test_opening_a_saree_shows_fabric_length_stock_dispatch_and_delivery(self):
        content = self.client.get(reverse("store:saree_detail", args=[self.saree.slug])).content.decode()

        self.assertIn("Silk", content)
        self.assertIn("6.3 metres (with blouse piece)", content)
        self.assertIn("In Stock", content)
        self.assertIn("Ready to ship in 24 hrs", content)
        self.assertIn("Free above", content)

    def test_the_delivery_limit_is_read_from_site_settings(self):
        site = SiteSettings.objects.first() or SiteSettings.objects.create(shop_name="Swathi Designers")
        site.free_shipping_above = Decimal("1500.00")
        site.save()

        content = self.client.get(reverse("store:saree_detail", args=[self.saree.slug])).content.decode()

        self.assertIn("1500.00", content)
        self.assertNotIn("999.00", content)

    def test_the_cart_prompt_uses_the_configured_remaining_amount(self):
        site = SiteSettings.objects.create(
            shop_name="Swathi Designers",
            free_shipping_above=Decimal("1500.00"),
        )
        session = self.client.session
        session["cart"] = {str(self.saree.pk): 1}
        session.save()

        response = self.client.get(reverse("store:cart"))

        self.assertContains(response, "Add &#8377; 500.00 more for free shipping")
        self.assertEqual(site.free_shipping_above, Decimal("1500.00"))

    def test_length_and_dispatch_fall_back_when_left_blank(self):
        self.saree.length = ""
        self.saree.dispatch_note = ""

        self.assertEqual(self.saree.card_length, "6.3 metres (with blouse piece)")
        self.assertEqual(self.saree.card_dispatch_note, "Ready to ship in 24 hrs")

    def test_an_out_of_stock_saree_says_so_on_the_product_page(self):
        self.saree.in_stock = False
        self.saree.save()

        content = self.client.get(reverse("store:saree_detail", args=[self.saree.slug])).content.decode()

        self.assertIn("Out of Stock", content)

    def test_an_out_of_stock_saree_cannot_be_added_to_the_cart(self):
        self.saree.in_stock = False
        self.saree.save()

        response = self.client.post(
            reverse("store:add_to_cart"),
            {"saree_id": self.saree.pk, "quantity": 1},
            follow=True,
        )

        self.assertEqual(Cart(self.client).count(), 0)
        self.assertContains(response, "out of stock")


class CartUsesTheDiscountedAmountTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(title="Cart Discounts", tier=Category.Tier.HIGH)
        self.saree = Saree.objects.create(
            name="Cart Saree",
            category=self.category,
            price=Decimal("800.00"),
            mrp=Decimal("1000.00"),
            discount_percent=Decimal("20"),
            image_url="https://example.com/a.jpg",
        )

    def test_the_cart_charges_the_final_amount_not_the_original(self):
        cart = Cart(self.client)
        cart.add(self.saree.pk, 2)

        item = cart.items()[0]

        self.assertEqual(item["final_amount"], Decimal("800.00"))
        self.assertEqual(item["line_total"], Decimal("1600.00"))
        self.assertEqual(cart.totals()["subtotal"], Decimal("1600.00"))

    def test_checkout_and_order_confirmation_use_the_discounted_snapshot(self):
        customer = Customer.objects.create(name="Discount Shopper", phone="9876543210")
        session = self.client.session
        session["customer_id"] = customer.pk
        session["cart"] = {str(self.saree.pk): 1}
        session.save()

        response = self.client.post(
            reverse("store:checkout"),
            {
                "name": customer.name,
                "phone": customer.phone,
                "email": "",
                "address": "18 Heritage Street",
                "city": "Chennai",
                "state": "Tamil Nadu",
                "pincode": "600040",
                "payment_method": "qr",
            },
        )

        self.assertEqual(response.status_code, 302)
        order_item = Order.objects.get().items.get()
        self.assertEqual(order_item.price, Decimal("800.00"))
        self.assertEqual(order_item.line_total, Decimal("800.00"))
        self.assertContains(self.client.get(response.url), "&#8377; 800")


class FloatingWhatsAppButtonTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(title="Chat", tier=Category.Tier.HIGH)

    def test_the_footer_social_row_no_longer_carries_whatsapp(self):
        SiteSettings.objects.create(shop_name="Swathi Designers", whatsapp="919876543210")

        content = self.client.get(reverse("store:home")).content.decode()
        social_row = content.split("social-links", 1)[1].split("</div>", 1)[0]

        self.assertNotIn("wa.me", social_row)

    def test_whatsapp_is_available_as_a_fixed_floating_link(self):
        SiteSettings.objects.create(shop_name="Swathi Designers", whatsapp="919876543210")

        content = self.client.get(reverse("store:home")).content.decode()

        self.assertIn("whatsapp-float", content)
        self.assertIn("https://wa.me/919876543210", content)

    def test_the_floating_button_is_absent_without_a_whatsapp_number(self):
        content = self.client.get(reverse("store:home")).content.decode()

        self.assertNotIn("whatsapp-float", content)


class PaymentQRAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("qrboss", "qr@example.com", "pw12345!")
        self.client.force_login(self.admin)
        self.media_dir = tempfile.TemporaryDirectory()
        self.settings_override = self.settings(MEDIA_ROOT=self.media_dir.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)
        self.customer = Customer.objects.create(name="Scan Shopper", phone="9876543210")
        self.category = Category.objects.create(title="Pay Tests", tier=Category.Tier.HIGH)
        self.saree = Saree.objects.create(
            name="Pay Saree",
            category=self.category,
            price=Decimal("1000.00"),
            mrp=Decimal("1000.00"),
            image_url="https://example.com/pay.jpg",
        )

    def _image(self, name="qr.png", colour="white", size=(60, 60)):
        buffer = BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def _login_customer(self):
        session = self.client.session
        session["customer_id"] = self.customer.pk
        session["cart"] = {str(self.saree.pk): 1}
        session.save()

    def test_the_checkout_shows_the_uploaded_qr_code(self):
        PaymentQR.objects.create(label="Main UPI", image=self._image(), upi_id="shop@upi")

        self._login_customer()
        content = self.client.get(reverse("store:checkout")).content.decode()

        self.assertIn("payment-qr/", content)
        self.assertIn("Payment Verification", content)

    def test_the_checkout_falls_back_to_the_generated_qr_when_none_is_uploaded(self):
        self._login_customer()
        response = self.client.get(reverse("store:checkout"))

        self.assertEqual(response.context["payment_qr"], None)
        self.assertContains(response, reverse("store:generate_qr"))

    def test_only_one_qr_can_be_added_so_the_payment_screen_stays_unambiguous(self):
        self.client.get(reverse("admin:store_paymentqr_add"))
        PaymentQR.objects.create(label="Main UPI", image=self._image())

        response = self.client.get(reverse("admin:store_paymentqr_add"))

        self.assertEqual(response.status_code, 403)

    def test_the_newest_active_qr_is_the_one_used(self):
        PaymentQR.objects.create(label="Old", image=self._image(colour="red"), created_at="2026-01-01T10:00:00Z")
        newest = PaymentQR.objects.create(label="New", image=self._image(colour="blue"))

        self.assertEqual(PaymentQR.current(), newest)

    def test_an_inactive_qr_is_never_shown(self):
        PaymentQR.objects.create(label="Off", image=self._image(), is_active=False)

        self.assertEqual(PaymentQR.current(), None)


class PaymentVerificationUploadTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("proofboss", "proof@example.com", "pw12345!")
        self.customer = Customer.objects.create(name="Scan Shopper", phone="9876543210")
        self.category = Category.objects.create(title="Pay Tests", tier=Category.Tier.HIGH)
        self.saree = Saree.objects.create(
            name="Pay Saree",
            category=self.category,
            price=Decimal("1000.00"),
            mrp=Decimal("1000.00"),
            image_url="https://example.com/pay.jpg",
        )
        self.media_dir = tempfile.TemporaryDirectory()
        self.settings_override = self.settings(MEDIA_ROOT=self.media_dir.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)
        session = self.client.session
        session["customer_id"] = self.customer.pk
        session["cart"] = {str(self.saree.pk): 1}
        session.save()

    def _image(self, name="proof.png"):
        buffer = BytesIO()
        Image.new("RGB", (60, 60), "green").save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def _checkout_payload(self, **overrides):
        payload = {
            "name": "Scan Shopper",
            "phone": "9876543210",
            "email": "scan@example.com",
            "address": "18, Heritage Textile Street",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600040",
            "payment": "qr",
            "payment_reference": "425781230001",
            "payment_screenshot": self._image(),
        }
        payload.update(overrides)
        return payload

    def test_a_screenshot_uploaded_at_checkout_is_stored_against_the_order(self):
        response = self.client.post(reverse("store:checkout"), self._checkout_payload())

        order = Order.objects.get()
        proof = PaymentProof.objects.get()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(proof.order, order)
        self.assertEqual(proof.customer_name, "Scan Shopper")
        self.assertEqual(proof.phone, "9876543210")
        self.assertEqual(proof.amount, order.total)
        self.assertEqual(proof.reference, "425781230001")
        self.assertEqual(proof.status, PaymentProof.Status.PENDING)
        self.assertTrue(proof.screenshot.name.startswith("payment-proofs/"))
        self.assertIsNotNone(proof.submitted_at)

    def test_checkout_still_succeeds_when_no_screenshot_is_uploaded(self):
        response = self.client.post(reverse("store:checkout"), self._checkout_payload(payment_screenshot=""))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(PaymentProof.objects.count(), 0)

    def test_a_screenshot_can_be_uploaded_after_the_order_is_placed(self):
        order = Order.objects.create(
            order_id="202601010001",
            name="Scan Shopper",
            phone="9876543210",
            address="18, Heritage Textile Street",
            city="Chennai",
            pincode="600040",
            payment_method="qr",
            payment_status=Order.Status.PENDING,
            subtotal=Decimal("1000.00"),
            total=Decimal("1050.00"),
        )

        response = self.client.post(
            reverse("store:payment_verification_order", args=[order.order_id]),
            {"order_id": order.order_id, "reference": "UTR99", "screenshot": self._image()},
            follow=True,
        )

        proof = PaymentProof.objects.get()
        order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(proof.order, order)
        self.assertEqual(proof.customer_name, "Scan Shopper")
        self.assertEqual(proof.amount, Decimal("1050.00"))
        self.assertEqual(order.payment_status, Order.Status.PAID)
        self.assertContains(response, "Payment done")
        self.assertNotContains(response, ">Pending<")

    def test_a_missing_screenshot_is_rejected_with_a_clear_message(self):
        response = self.client.post(
            reverse("store:payment_verification"),
            {"order_id": "", "reference": "", "screenshot": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaymentProof.objects.count(), 0)
        self.assertContains(response, "Upload the payment screenshot.")

    def test_another_customers_order_cannot_be_used_to_attach_a_screenshot(self):
        someone_else = Order.objects.create(
            order_id="202601010009",
            name="Someone Else",
            phone="9000000000",
            address="1, Elsewhere Road",
            city="Chennai",
            pincode="600040",
            payment_method="qr",
            subtotal=Decimal("1000.00"),
            total=Decimal("1050.00"),
        )

        response = self.client.post(
            reverse("store:payment_verification"),
            {"order_id": someone_else.order_id, "reference": "", "screenshot": self._image()},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(PaymentProof.objects.count(), 0)

    def test_the_standalone_page_is_reachable_without_an_order_id(self):
        response = self.client.get(reverse("store:payment_verification"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment Verification")

    def test_the_admin_list_shows_who_paid_what_and_when(self):
        order = Order.objects.create(
            order_id="202601010002",
            name="Scan Shopper",
            phone="9876543210",
            address="18, Heritage Textile Street",
            city="Chennai",
            pincode="600040",
            payment_method="qr",
            subtotal=Decimal("1000.00"),
            total=Decimal("1050.00"),
        )
        OrderItem.objects.create(order=order, saree=self.saree, name=self.saree.name, price=Decimal("1000.00"), quantity=2)
        proof = PaymentProof(
            order=order,
            customer=self.customer,
            customer_name="Scan Shopper",
            phone="9876543210",
            amount=order.total,
            screenshot=self._image(),
        )
        proof.save()

        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:store_paymentproof_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scan Shopper")
        self.assertContains(response, "1050.00")
        self.assertContains(response, "202601010002")
        self.assertContains(response, "2 x Pay Saree")
        self.assertContains(response, proof.screenshot.url)

    def test_staff_can_mark_a_screenshot_verified(self):
        proof = PaymentProof(
            customer=self.customer,
            customer_name="Scan Shopper",
            amount=Decimal("1050.00"),
            screenshot=self._image(),
        )
        proof.save()

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:store_paymentproof_changelist"),
            {
                "action": "mark_verified",
                "_selected_action": [str(proof.pk)],
            },
            follow=True,
        )

        proof.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(proof.status, PaymentProof.Status.VERIFIED)
        self.assertEqual(proof.reviewed_by, self.admin)
        self.assertIsNotNone(proof.reviewed_at)

    def test_a_paid_order_is_listed_as_payment_done(self):
        order = Order.objects.create(
            order_id="202601010003",
            name="Scan Shopper",
            phone="9876543210",
            address="18, Heritage Textile Street",
            city="Chennai",
            pincode="600040",
            payment_method="qr",
            payment_status=Order.Status.PAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1050.00"),
        )
        proof = PaymentProof(
            order=order,
            customer=self.customer,
            customer_name="Scan Shopper",
            phone="9876543210",
            amount=order.total,
            screenshot=self._image(),
        )
        proof.save()

        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:store_paymentproof_changelist"))

        self.assertContains(response, "Payment done")
        self.assertNotContains(response, "Pending verification")

    def test_an_unpaid_order_falls_back_to_the_proof_status(self):
        order = Order.objects.create(
            order_id="202601010004",
            name="Scan Shopper",
            phone="9876543210",
            address="18, Heritage Textile Street",
            city="Chennai",
            pincode="600040",
            payment_method="qr",
            payment_status=Order.Status.CANCELLED,
            subtotal=Decimal("1000.00"),
            total=Decimal("1050.00"),
        )
        proof = PaymentProof(
            order=order,
            customer=self.customer,
            customer_name="Scan Shopper",
            phone="9876543210",
            amount=order.total,
            screenshot=self._image(),
        )
        proof.save()

        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:store_paymentproof_changelist"))

        proof_admin = admin.site._registry[PaymentProof]

        self.assertEqual(proof_admin.payment_state(proof), "Pending")
        self.assertNotContains(response, "Pending verification")


class SareeCardDiscountVisibilityTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(title="Card Offers", tier=Category.Tier.HIGH)
        self.saree = Saree.objects.create(
            name="Offer Saree",
            category=self.category,
            price=Decimal("800.00"),
            mrp=Decimal("1000.00"),
            discount_percent=Decimal("20"),
            image_url="https://example.com/offer.jpg",
        )
        session = self.client.session
        session["customer_id"] = Customer.objects.create(name="Card Shopper", phone="9876543210").pk
        session.save()

    def test_the_cards_show_the_final_price_with_the_actual_amount_struck_through(self):
        content = self.client.get(reverse("store:catalog")).content.decode()

        self.assertIn("&#8377; 800.00", content)
        self.assertIn("<del>&#8377; 1000.00</del>", content)
        self.assertNotIn("% off", content)

    def test_the_discount_is_shown_on_the_product_page(self):
        content = self.client.get(
            reverse("store:saree_detail", args=[self.saree.slug])
        ).content.decode()

        self.assertIn("20.00% off", content)
        self.assertIn("you save &#8377; 200.00", content)
        self.assertIn("&#8377; 1000.00", content)


class SareeAdminListColumnTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("listboss", "list@example.com", "pw12345!")
        self.client.force_login(self.admin)
        category = Category.objects.create(title="Price Lists", tier=Category.Tier.HIGH)
        Saree.objects.create(
            name="Listed Saree",
            category=category,
            price=Decimal("900.00"),
            mrp=Decimal("1200.00"),
            discount_percent=Decimal("25"),
            image_url="https://example.com/listed.jpg",
        )

    def test_the_product_list_shows_actual_and_final_price_without_a_discount_column(self):
        model_admin = admin.site._registry[Saree]

        self.assertIn("category", model_admin.list_display)
        self.assertIn("name", model_admin.list_display)
        self.assertIn("original_amount", model_admin.list_display)
        self.assertIn("final_amount", model_admin.list_display)
        self.assertNotIn("discount_percent", model_admin.list_display)

    def test_the_product_list_page_renders_both_prices(self):
        response = self.client.get(reverse("admin:store_saree_changelist"))

        self.assertContains(response, "Original amount")
        self.assertContains(response, "Final amount")
        self.assertContains(response, "Rs 1200.00")
        self.assertContains(response, "Rs 900.00")