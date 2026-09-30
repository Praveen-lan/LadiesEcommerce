from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.core.validators import URLValidator


class SiteSettings(models.Model):
    shop_name = models.CharField(max_length=120, default="Saree Elegance")
    tagline = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to="site/", blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    map_embed_url = models.URLField(blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    youtube = models.URLField(blank=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return self.shop_name


class SEO(models.Model):
    site_name = models.CharField(max_length=120, default="Saree Elegance")
    default_title = models.CharField(
        max_length=160,
        default="Saree Elegance | Handloom, Silk and Cotton Sarees",
    )
    default_description = models.TextField(
        max_length=160,
        default="Shop beautiful handloom, silk, georgette and cotton sarees online at Saree Elegance. Find timeless weaves for weddings, festivals and everyday celebrations.",
    )
    default_keywords = models.CharField(
        max_length=255,
        default="sarees, online sarees, handloom sarees, silk sarees, cotton sarees, saree online shopping",
    )
    og_image = models.ImageField(upload_to="seo/", blank=True, null=True)
    twitter_handle = models.CharField(max_length=100, blank=True)
    canonical_base_url = models.URLField(blank=True)
    google_site_verification = models.CharField(max_length=100, blank=True)
    robots_extra = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SEO Settings"
        verbose_name_plural = "SEO Settings"

    def __str__(self):
        return self.site_name


class AboutPage(models.Model):
    title = models.CharField(max_length=150, default="About Our Story")
    subtitle = models.CharField(
        max_length=250,
        default="A thoughtfully curated destination for sarees made to celebrate you.",
    )
    image = models.ImageField(upload_to="site/", blank=True, null=True)
    story = models.TextField(
        default="Saree Elegance is a celebration of timeless Indian craftsmanship and modern style. We bring together handloom textures, graceful silk, comfortable cotton and beautiful prints for every celebration, from everyday gatherings to treasured wedding moments."
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


class TermsPage(models.Model):
    title = models.CharField(max_length=150, default="Terms and Conditions")
    subtitle = models.CharField(
        max_length=250,
        default="Clear guidelines for a smooth and transparent shopping experience.",
    )
    content = models.TextField(
        default="1. About Saree Elegance\nSaree Elegance provides thoughtfully curated sarees and related services through this website.\n\n2. Product information\nProduct images, descriptions, prices and availability may change. Please review the product details before placing an order.\n\n3. Orders and payments\nOrders are confirmed after successful payment or confirmation of cash on delivery. We may contact you to verify order details before dispatch.\n\n4. Delivery\nWe aim to dispatch orders quickly and provide delivery updates through the contact details shared for the order. Delivery timelines may vary by location.\n\n5. Exchanges and returns\nIf you receive a damaged or incorrect item, contact us promptly with your order details. Exchanges or returns are handled according to our quality-check and customer support process.\n\n6. Privacy\nWe use the information you provide to process orders, respond to enquiries and improve your shopping experience. We do not sell your personal information.\n\n7. Contact\nFor questions about an order, product or these terms, please use the Contact Us page to reach our support team."
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


class Saree(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="sarees")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    mrp = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fabric = models.CharField(max_length=120, blank=True)
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

    @property
    def image_source(self):
        if self.image:
            return self.image.url
        return self.image_url

    def get_absolute_url(self):
        return reverse("store:saree_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name)
            slug = base
            counter = 2
            while Saree.objects.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def discount_percent(self):
        if self.mrp and self.mrp > self.price:
            return round((self.mrp - self.price) / self.mrp * 100)
        return 0

    @property
    def savings(self):
        if self.mrp and self.mrp > self.price:
            return self.mrp - self.price
        return 0


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


class CartItem(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="cart_items")
    saree = models.ForeignKey(Saree, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["updated_at", "id"]
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        constraints = [
            models.UniqueConstraint(fields=["customer", "saree"], name="unique_customer_saree_cart_item"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.saree.name} ({self.customer.phone})"


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
        from .cart import GST_RATE, SHIPPING_FEE, SHIPPING_FEE_ABOVE

        subtotal = sum((item.line_total for item in self.items.all()), Decimal("0"))
        delivery = SHIPPING_FEE if 0 < subtotal < SHIPPING_FEE_ABOVE else Decimal("0")
        gst = (subtotal * GST_RATE).quantize(Decimal("0.01"))
        self.subtotal = subtotal
        self.delivery_charge = delivery
        self.gst = gst
        self.total = (subtotal + delivery + gst).quantize(Decimal("0.01"))
        self.save(update_fields=["subtotal", "delivery_charge", "gst", "total"])
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    saree = models.ForeignKey(Saree, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.name}"