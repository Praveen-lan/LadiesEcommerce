from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.conf import settings
from django.db import models
from django.urls import reverse

from .pricing import (
    GST_RATE,
    gst_amount,
    is_valid_discount_percent,
    is_valid_gst_percent,
    price_breakdown,
    to_amount,
)
from .validators import validate_image_extension, validate_payment_image_extension

# Fallbacks for the two saree card details, used when a saree leaves the field
# empty so every saree still shows the full set of details.
DEFAULT_SAREE_LENGTH = "6.3 metres (with blouse piece)"
DEFAULT_DISPATCH_NOTE = "Ready to ship in 24 hrs"


class SiteSettings(models.Model):
    shop_name = models.CharField(max_length=120, default="Swathi Designers")
    tagline = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to="site/", blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    map_embed_url = models.TextField(blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("79.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Delivery charge applied when the order total is below the free delivery limit.",
    )
    free_shipping_above = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("999.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Delivery is free at or above this order total, for example 999 makes delivery free from Rs 999.",
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return self.shop_name


class SEO(models.Model):
    page_name = models.CharField(max_length=120, blank=True)
    site_name = models.CharField(max_length=120, default="Swathi Designers")
    default_title = models.CharField(
        max_length=160,
        default="Swathi Designers | Handloom, Silk and Cotton Sarees",
    )
    default_page_description = models.TextField(
        max_length=300,
        blank=True,
        verbose_name="Default description",
    )
    meta_title = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Meta title",
    )
    default_description = models.TextField(
        max_length=160,
        verbose_name="Meta Description",
        default="Shop beautiful handloom, silk, georgette and cotton sarees online at Swathi Designers. Find timeless weaves for weddings, festivals and everyday celebrations.",
    )
    default_keywords = models.CharField(
        max_length=255,
        verbose_name="Meta keywords",
        default="sarees, online sarees, handloom sarees, silk sarees, cotton sarees, saree online shopping",
    )
    google_site_verification = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Google site Verification",
    )
    robots_extra = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated time")

    class Meta:
        verbose_name = "SEO Settings"
        verbose_name_plural = "SEO Settings"

    def __str__(self):
        return self.page_name or self.site_name

    @classmethod
    def current(cls):
        return cls.objects.order_by("-pk").first()


class LoginPage(models.Model):
    heading = models.CharField(max_length=160, default="Welcome to Swathi Designers")
    description = models.TextField(
        max_length=400,
        default="Step into a thoughtfully curated world of handloom stories, festive silks, and timeless drapes.",
    )
    tagline = models.CharField(max_length=160, default="Your saree story begins here")
    background_image = models.ImageField(upload_to="site/", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Login Page Content"
        verbose_name_plural = "Login Page Content"

    def __str__(self):
        return self.heading

    @classmethod
    def current(cls):
        return cls.objects.order_by("-pk").first()


class AboutPage(models.Model):
    title = models.CharField(max_length=150, default="About Our Story")
    subtitle = models.CharField(
        max_length=250,
        default="A thoughtfully curated destination for sarees made to celebrate you.",
    )
    image = models.ImageField(upload_to="site/", blank=True, null=True)
    story = models.TextField(
        default="Swathi Designers is a celebration of timeless Indian craftsmanship and modern style. We bring together handloom textures, graceful silk, comfortable cotton and beautiful prints for every celebration, from everyday gatherings to treasured wedding moments."
    )
    mission = models.TextField(
        default="Our promise is simple: help you find a saree that feels as special as the occasion you are dressing for, with thoughtful service and quality you can trust."
    )
    delivery_commitment = models.CharField(max_length=80, default="Fast Delivery")
    support_commitment = models.CharField(max_length=80, default="24/7 Online Support")
    exchange_commitment = models.CharField(max_length=80, default="Fast Exchange")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "About Page"
        verbose_name_plural = "About Page"

    def __str__(self):
        return self.title

    @classmethod
    def current(cls):
        return cls.objects.order_by("-pk").first()

    def __str__(self):
        return self.title


class TermsPage(models.Model):
    title = models.CharField(max_length=150, default="Terms and Conditions")
    subtitle = models.CharField(
        max_length=250,
        default="Clear guidelines for a smooth and transparent shopping experience.",
    )
    content = models.TextField(
        default="1. About Swathi Designers\nSwathi Designers provides thoughtfully curated sarees and related services through this website.\n\n2. Product information\nProduct images, descriptions, prices and availability may change. Please review the product details before placing an order.\n\n3. Orders and payments\nOrders are confirmed after successful payment or confirmation of cash on delivery. We may contact you to verify order details before dispatch.\n\n4. Delivery\nWe aim to dispatch orders quickly and provide delivery updates through the contact details shared for the order. Delivery timelines may vary by location.\n\n5. Exchanges and returns\nIf you receive a damaged or incorrect item, contact us promptly with your order details. Exchanges or returns are handled according to our quality-check and customer support process.\n\n6. Privacy\nWe use the information you provide to process orders, respond to enquiries and improve your shopping experience. We do not sell your personal information.\n\n7. Contact\nFor questions about an order, product or these terms, please use the Contact Us page to reach our support team."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Terms and Conditions Page"
        verbose_name_plural = "Terms and Conditions Page"

    def __str__(self):
        return self.title


class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.subject}"


class Category(models.Model):
    class Tier(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        BASIC = "basic", "Basic"

    title = models.CharField(max_length=120)
    tier = models.CharField(max_length=20, choices=Tier.choices, db_index=True)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            base = slugify(self.title) or "category"
            slug = base
            counter = 2
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:category_detail", kwargs={"slug": self.slug or self.tier})

    @property
    def banner_image(self):
        if self.image:
            return self.image.url
        saree = self.sarees.filter(models.Q(image__gt="") | models.Q(image_url__gt="")).first()
        return saree.image_source if saree else None


class SubCategory(models.Model):
    """A named style group inside a :class:`Category` collection.

    Collections answer "which price band?", sub categories answer "which weave?"
    — Silk Sarees, Cotton Sarees, Printed & Embroidery and so on. Every category
    gets the same starter set from :data:`DEFAULT_SUBCATEGORIES` so the storefront
    navigation is complete from the first load; staff can rename, reorder or add
    their own from the admin.
    """

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=150, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Sub Category"
        verbose_name_plural = "Sub Categories"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=("category", "slug"), name="unique_subcategory_slug_per_category"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            base = slugify(self.title) or "sub-category"
            slug = base
            counter = 2
            siblings = SubCategory.objects.filter(category_id=self.category_id).exclude(pk=self.pk)
            while siblings.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "store:subcategory_detail",
            kwargs={"category_slug": self.category.slug, "slug": self.slug},
        )

    @property
    def full_title(self):
        return f"{self.category.title} - {self.title}"

    @property
    def banner_image(self):
        if self.image:
            return self.image.url
        saree = self.sarees.filter(models.Q(image__gt="") | models.Q(image_url__gt="")).first()
        return saree.image_source if saree else None


class Saree(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="sarees")
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.SET_NULL,
        related_name="sarees",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=150)
    product_id = models.CharField(
        max_length=220,
        blank=True,
        db_index=True,
        help_text="Between 4 and 220 characters, for example SD-SRK-1001. Required for new products.",
    )
    slug = models.SlugField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    mrp = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="The original amount before any discount. This value is never changed by a discount.",
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        default=None,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text=(
            "Optional. Leave blank to use the price as it is. When set between 0 and 100 the price is "
            "worked out once as: discount = original amount x this percentage / 100, "
            "then final amount = original amount - discount."
        ),
    )
    delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Additional delivery charge per saree, added to the site delivery fee when applicable.",
    )
    gst_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("1.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="GST percentage applied to this saree, from 1 to 100.",
    )
    fabric = models.CharField(max_length=120, blank=True)
    length = models.CharField(
        max_length=120,
        blank=True,
        default=DEFAULT_SAREE_LENGTH,
        help_text="Shown on the saree card, for example 6.3 metres (with blouse piece).",
    )
    in_stock = models.BooleanField(default=True, verbose_name="In stock")
    dispatch_note = models.CharField(
        max_length=120,
        blank=True,
        default=DEFAULT_DISPATCH_NOTE,
        help_text="Dispatch message shown on the saree card, for example Ready to ship in 24 hrs.",
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="sarees/", blank=True)
    image_url = models.URLField(
        blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
    )
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.image and not self.image_url:
            raise ValidationError({"image_url": "Upload an image or enter an image URL."})
        if self.image and self.image_url:
            raise ValidationError({"image_url": "Use either an uploaded image or an image URL, not both."})
        if self.subcategory_id and self.category_id and self.subcategory.category_id != self.category_id:
            raise ValidationError(
                {
                    "subcategory": (
                        f'"{self.subcategory.title}" belongs to "{self.subcategory.category.title}", '
                        f'not to "{self.category.title}". Pick a sub category from the selected category.'
                    )
                }
            )
        if not is_valid_discount_percent(self.discount_percent):
            raise ValidationError({"discount_percent": "Enter a discount between 0 and 100 percent."})
        if not is_valid_gst_percent(self.gst_percent):
            raise ValidationError({"gst_percent": "Enter a GST percentage between 1 and 100."})
        if self.price is not None and Decimal(str(self.price)) < 0:
            raise ValidationError({"price": "Price cannot be negative."})
        if self.mrp is not None and Decimal(str(self.mrp)) < 0:
            raise ValidationError({"mrp": "Original amount cannot be negative."})
        if (
            self.discount_percent is None
            and self.mrp is not None
            and self.price is not None
            and Decimal(str(self.mrp)) < Decimal(str(self.price))
        ):
            raise ValidationError(
                {
                    "mrp": (
                        f"The original amount is lower than the price of {self.price}. "
                        "Correct the original amount, or enter a discount percentage to work the price out."
                    )
                }
            )

    @property
    def image_source(self):
        if self.image:
            return self.image.url
        return self.image_url

    @property
    def product_type_name(self):
        return "Sarees"

    @property
    def is_saree(self):
        return True

    def get_absolute_url(self):
        return reverse("store:saree_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.category_id and self.subcategory_id:
            self.category_id = self.subcategory.category_id
        if not is_valid_discount_percent(self.discount_percent):
            raise ValidationError({"discount_percent": "Enter a discount between 0 and 100 percent."})
        if not is_valid_gst_percent(self.gst_percent):
            raise ValidationError({"gst_percent": "Enter a GST percentage between 1 and 100."})
        if self.discount_percent is not None:
            breakdown = self.calculate_price_breakdown()
            self.mrp = breakdown["original"]
            self.price = breakdown["final"]
        if not self.slug:
            from django.utils.text import slugify

            base = slugify(self.name) or "saree"
            slug = base
            counter = 2
            while Saree.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def calculate_price_breakdown(self):
        """Return the original, percent, discount and final amounts for this saree.

        Every screen that shows money reads from this one breakdown, so the
        product page, cart, checkout, payment and invoice always agree.
        """
        if not is_valid_discount_percent(self.discount_percent):
            raise ValidationError({"discount_percent": "Enter a discount between 0 and 100 percent."})
        return price_breakdown(self.mrp, self.price, self.discount_percent)

    @property
    def price_breakdown(self):
        return self.calculate_price_breakdown()

    @property
    def original_amount(self):
        """The price before any discount. Never modified by a discount."""
        return self.price_breakdown["original"]

    @property
    def final_amount(self):
        """The price the customer pays, after the discount has been applied once."""
        return self.price_breakdown["final"]

    @property
    def discount_amount(self):
        """The money taken off the original amount."""
        return self.price_breakdown["discount"]

    @property
    def effective_discount_percent(self):
        """The discount percentage to display, derived when none was entered."""
        return self.price_breakdown["percent"]

    @property
    def savings(self):
        """Kept for the product page, which shows the money saved."""
        return self.discount_amount

    @property
    def card_length(self):
        return self.length or DEFAULT_SAREE_LENGTH

    @property
    def card_dispatch_note(self):
        return self.dispatch_note or DEFAULT_DISPATCH_NOTE


class ProductType(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.CharField(max_length=250, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "Product Category"
        verbose_name_plural = "Product Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    product_type = models.ForeignKey(ProductType, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    mrp = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        default=None,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    gst_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("1.00")), MaxValueValidator(Decimal("100.00"))],
    )
    image = models.ImageField(upload_to="products/", validators=[validate_image_extension])
    in_stock = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name

    @property
    def image_source(self):
        return self.image.url if self.image else ""

    @property
    def product_type_name(self):
        return self.product_type.name

    @property
    def is_saree(self):
        return False

    def get_absolute_url(self):
        return reverse("store:product_detail", kwargs={"slug": self.slug})

    def clean(self):
        super().clean()
        if not is_valid_discount_percent(self.discount_percent):
            raise ValidationError({"discount_percent": "Enter a discount between 0 and 100 percent."})
        if not is_valid_gst_percent(self.gst_percent):
            raise ValidationError({"gst_percent": "Enter a GST percentage between 1 and 100."})
        if (
            self.discount_percent is None
            and self.mrp is not None
            and self.price is not None
            and Decimal(str(self.mrp)) < Decimal(str(self.price))
        ):
            raise ValidationError({"mrp": "Original amount cannot be lower than the price."})

    def save(self, *args, **kwargs):
        if not is_valid_discount_percent(self.discount_percent):
            raise ValidationError({"discount_percent": "Enter a discount between 0 and 100 percent."})
        if not is_valid_gst_percent(self.gst_percent):
            raise ValidationError({"gst_percent": "Enter a GST percentage between 1 and 100."})
        if self.discount_percent is not None:
            breakdown = self.calculate_price_breakdown()
            self.mrp = breakdown["original"]
            self.price = breakdown["final"]
        super().save(*args, **kwargs)

    def calculate_price_breakdown(self):
        if not is_valid_discount_percent(self.discount_percent):
            raise ValidationError({"discount_percent": "Enter a discount between 0 and 100 percent."})
        return price_breakdown(self.mrp, self.price, self.discount_percent)

    @property
    def original_amount(self):
        return self.calculate_price_breakdown()["original"]

    @property
    def final_amount(self):
        return self.calculate_price_breakdown()["final"]

    @property
    def discount_amount(self):
        return self.calculate_price_breakdown()["discount"]

    @property
    def effective_discount_percent(self):
        return self.calculate_price_breakdown()["percent"]


class Customer(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, unique=True)
    email = models.EmailField(blank=True)
    profile_image = models.ImageField(upload_to="customers/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.phone})"


class ShoppingCart(models.Model):
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="shopping_cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.customer}"


class CartItem(models.Model):
    cart = models.ForeignKey(
        ShoppingCart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    saree = models.ForeignKey(
        Saree,
        on_delete=models.CASCADE,
        related_name="cart_items",
        blank=True,
        null=True,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
        blank=True,
        null=True,
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=("cart", "saree"), name="unique_saree_per_shopping_cart"),
            models.UniqueConstraint(
                fields=("cart", "product"),
                condition=models.Q(product__isnull=False),
                name="unique_product_per_shopping_cart",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(saree__isnull=False, product__isnull=True)
                    | models.Q(saree__isnull=True, product__isnull=False)
                ),
                name="cart_item_has_one_product",
            ),
        ]

    def __str__(self):
        return f"{self.product or self.saree} x {self.quantity}"


class OTPRequest(models.Model):
    phone = models.CharField(max_length=30, db_index=True)
    code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone} - {self.code}"

    @property
    def is_expired(self):
        from django.utils import timezone

        return timezone.now() > self.expires_at

    @property
    def is_locked(self):
        return self.attempts >= 5


class Banner(models.Model):
    title = models.CharField(max_length=150, blank=True)
    subtitle = models.CharField(max_length=250, blank=True)
    image = models.ImageField(upload_to="banners/")
    link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or f"Banner {self.id}"


class Order(models.Model):
    class PaymentMethod(models.TextChoices):
        CARD = "card", "Credit / Debit Card"
        UPI = "upi", "UPI"
        QR = "qr", "QR Code / Scan & Pay"
        NETBANKING = "netbanking", "Net Banking"
        COD = "cod", "Cash on Delivery"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_id} - {self.name}"

    def recalculate_totals(self):
        from .cart import shipping_rules

        subtotal = sum((item.line_total for item in self.items.all()), Decimal("0"))
        fee, limit = shipping_rules()
        items = list(self.items.all())
        base_delivery = fee if 0 < subtotal < limit else Decimal("0.00")
        product_delivery = sum(
            (item.delivery_charge * item.quantity for item in items),
            Decimal("0.00"),
        )
        delivery = base_delivery + product_delivery
        gst = sum((gst_amount(item.line_total, item.gst_percent) for item in items), Decimal("0.00"))
        self.subtotal = subtotal
        self.delivery_charge = delivery
        self.gst = gst
        self.total = (subtotal + delivery + gst).quantize(Decimal("0.01"))
        self.save(update_fields=["subtotal", "delivery_charge", "gst", "total"])
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    saree = models.ForeignKey(Saree, on_delete=models.SET_NULL, null=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    gst_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("1.00")), MaxValueValidator(Decimal("100.00"))],
    )

    @property
    def line_total(self):
        return self.price * self.quantity

    @property
    def gst_amount(self):
        return gst_amount(self.line_total, self.gst_percent)

    def __str__(self):
        return f"{self.quantity} x {self.name}"


class PaymentQR(models.Model):
    """The payment QR code shown to customers in the payment method section."""

    label = models.CharField(max_length=120, blank=True)
    image = models.ImageField(upload_to="payment-qr/")
    upi_id = models.CharField(
        max_length=120,
        blank=True,
        help_text="UPI ID used for the automatically generated QR when no image is uploaded.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only the newest active code is shown to customers.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payment QR Code"
        verbose_name_plural = "Payment QR Codes"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.label or f"Payment QR {self.pk}"

    @classmethod
    def current(cls):
        """Return the QR to show customers, or ``None`` when none is active."""
        return cls.objects.filter(is_active=True).order_by("-created_at", "-id").first()


class PaymentProof(models.Model):
    """A payment screenshot uploaded by a customer for staff to verify."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Payment done"
        REJECTED = "rejected", "Rejected"

    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_proofs",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_proofs",
    )
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="The amount the customer was asked to pay.",
    )
    payment_method = models.CharField(
        max_length=20,
        choices=Order.PaymentMethod.choices,
        default=Order.PaymentMethod.QR,
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="UPI reference or UTR number, when the customer has one.",
    )
    screenshot = models.ImageField(
        upload_to="payment-proofs/",
        validators=[validate_payment_image_extension],
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated time")
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_payment_proofs",
    )

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "Payment Verification"
        verbose_name_plural = "Payment Verifications"

    def __str__(self):
        return f"{self.customer_name} - {self.amount}"

    def save(self, *args, **kwargs):
        if self.order_id:
            if not self.customer_name:
                self.customer_name = self.order.name
            if not self.phone:
                self.phone = self.order.phone
            if not self.amount:
                self.amount = self.order.total
            if self.order.payment_status == Order.Status.PENDING:
                self.order.payment_status = Order.Status.PAID
                self.order.save(update_fields=["payment_status"])
        super().save(*args, **kwargs)

    @property
    def order_reference(self):
        """The order ID, or a clear placeholder when no order is linked."""
        return self.order.order_id if self.order_id else "Not linked"

    @property
    def order_details(self):
        """The sarees and quantities on the linked order, for the admin list."""
        if not self.order_id:
            return "No order linked"
        items = [f"{item.quantity} x {item.name}" for item in self.order.items.all()]
        return ", ".join(items) if items else "No items on this order"


class AdminRecoveryCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Admin recovery code for {self.user}"


# The starter sub categories every collection is seeded with, in menu order.
# Each entry carries the words that identify it so existing sarees can be filed
# automatically: the fabric field is checked first, then the name and description.
DEFAULT_SUBCATEGORIES = (
    (
        "Silk Sarees",
        "Pure mulberry, Kanjivaram, Banarasi and soft silk weaves with a luminous drape.",
        ("silk", "kanjivaram", "kanchi", "banarasi", "patola", "mysore", "tussar", "dupatta", "mulberry"),
    ),
    (
        "Cotton Sarees",
        "Lightweight, breathable cottons and handspun khadi for everyday grace.",
        ("cotton", "chanderi", "linen", "khadi", "tussar silk", "poplin", "canvas"),
    ),
    (
        "Modern & Synthetic Fabric Sarees",
        "Georgette, chiffon and crepe drapes with an easy, modern fall.",
        ("georgette", "chiffon", "crepe", "satin", "organza", "polyester", "synthetic", "nylon", "rayon", "jacquard"),
    ),
    (
        "Printed & Embroidery Sarees",
        "Block prints, zari work and hand embroidery in rich, festive detail.",
        ("print", "printed", "block", "embroid", "zari", "zardozi", "aari", "chikankari", "appliqu", "patchwork"),
    ),
    (
        "Modern Fusion Sarees",
        "Indo-western drapes that blend traditional motifs with a contemporary cut.",
        ("fusion", "indo-western", "indo western", "contemporary", "modern", "ready-to-wear", "drape"),
    ),
)


def guess_subcategory(saree, subcategories):
    """Return the sub category that best fits ``saree``, or ``None``.

    The fabric field is the strongest signal, so it is matched on its own before
    the name and description are considered. The first matching sub category in
    menu order wins, which keeps the guess stable when a saree mentions more than
    one fabric (a "silk cotton" saree files under Silk Sarees).
    """
    fabric = (saree.fabric or "").lower()
    haystack = " ".join(filter(None, (saree.name, saree.description))).lower()
    if not fabric and not haystack:
        return None
    for subcategory in subcategories:
        for keyword in subcategory["keywords"]:
            if keyword in fabric:
                return subcategory
    for subcategory in subcategories:
        for keyword in subcategory["keywords"]:
            if keyword in haystack:
                return subcategory
    return None
