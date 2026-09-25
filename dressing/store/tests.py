from django.test import TestCase
from django.urls import reverse

from .models import Category, ContactMessage, Saree, SEO, SiteSettings


class StorePageTests(TestCase):
    def setUp(self):
        SiteSettings.objects.create(
            shop_name="Saree Elegance",
            address="18, Heritage Textile Street, Anna Nagar, Chennai",
            phone="+91 98765 43210",
            email="hello@sareeelegance.in",
        )

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
        seo.default_title = "Saree Elegance SEO Test"
        seo.default_description = "Search-optimized saree shopping description."
        seo.default_keywords = "test sarees, online sarees"
        seo.canonical_base_url = "https://sareeelegance.example"
        seo.save()

        response = self.client.get(reverse("store:home"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>Saree Elegance SEO Test</title>", content)
        self.assertIn('name="description" content="Search-optimized saree shopping description."', content)
        self.assertIn('name="keywords" content="test sarees, online sarees"', content)
        self.assertIn('rel="canonical" href="https://sareeelegance.example/home/"', content)
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
        positions = [content.index(label) for label in ("Home</a>", "All Catalog</a>", "Collections", "About Us</a>", "Contact Us</a>")]
        self.assertEqual(positions, sorted(positions))
