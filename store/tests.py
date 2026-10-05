from decimal import Decimal
from io import BytesIO
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Category, ContactMessage, Customer, Order, OrderItem, Saree, SEO, SiteSettings, SubCategory


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
        positions = [content.index(label) for label in ("Home</a>", "About Us</a>", "Collections", "Contact Us</a>")]
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
        for phone in ("qwerty", "98765@3210", "123456789", "12345678901", "+919876543210"):
            with self.subTest(phone=phone):
                response = self._post("Valid Customer", phone=phone)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Please enter a valid 10-digit phone number.")
                self.assertContains(response, f'value="{phone}"')
                self.assertEqual(Order.objects.count(), 0)
                self.assertEqual(self.client.session["cart"], {str(self.saree.pk): 1})

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
        response = self.client.post(
            reverse("store:login"),
            {"name": "User A", "phone": "12345"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a valid phone number.")
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
            {"name": "New Collection Saree", "price": "1499.00", "image": image},
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
        for field_name in ("name", "price", "mrp", "fabric", "description", "image", "image_url", "is_featured"):
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


