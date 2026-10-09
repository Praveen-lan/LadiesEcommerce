import hmac
import json
import logging
import re
import secrets
import smtplib
import uuid
import unicodedata
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.core.validators import EmailValidator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from PIL import Image as PILImage, ImageDraw, ImageFont
from .cart import Cart, shipping_rules
from .forms import (
    AdminRecoveryCodeForm,
    AdminRecoveryCredentialsForm,
    AdminRecoveryEmailForm,
    ContactForm,
    PaymentProofForm,
)
from .maps import extract_map_source
from .models import (
    AboutPage,
    AdminRecoveryCode,
    Banner,
    Category,
    Customer,
    LoginPage,
    Order,
    OrderItem,
    PaymentProof,
    PaymentQR,
    Product,
    ProductType,
    Saree,
    SEO,
    SiteSettings,
    SubCategory,
    TermsPage,
)

logger = logging.getLogger(__name__)

PROFILE_LOGO_SIZE = (300, 300)

PHONE_ERROR = "Please give correct number."

CHECKOUT_PAYMENT_METHODS = ((Order.PaymentMethod.QR, Order.PaymentMethod.QR.label),)

# Used when staff have not uploaded a QR image or set a UPI id in the admin, so
# the payment method section always shows a scannable code out of the box.
DEFAULT_UPI_ID = "swathidesigners@upi"
DEFAULT_PAYEE_NAME = "Swathi Designers"

def _absolute_url(request, value):
    if not value:
        return ""
    url = value.url if hasattr(value, "url") else str(value)
    if url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url) if request else url


def _canonical_url(request, seo):
    if not request:
        return ""
    return request.build_absolute_uri(request.path)


def _seo_context(request, site=None, seo=None, title=None, description=None, keywords=None, image=None, noindex=False, seo_type="website", product=None):
    site = site or SiteSettings()
    seo = seo or SEO()
    title = title or seo.default_title
    description = description or seo.default_description
    keywords = keywords if keywords is not None else seo.default_keywords
    if image is None:
        banner = Banner.objects.filter(is_active=True).first()
        image = banner.image if banner else None
        if not image:
            saree = Saree.objects.filter(Q(image__gt="") | Q(image_url__gt="")).first()
            image = saree.image_source if saree else None

    canonical = _canonical_url(request, seo)
    image_url = _absolute_url(request, image)
    site_name = site.shop_name or seo.site_name
    base_url = request.build_absolute_uri("/") if request else ""

    organization = {
        "@type": "Organization",
        "@id": f"{base_url}#organization",
        "name": site_name,
        "url": base_url,
    }
    if site.logo:
        organization["logo"] = _absolute_url(request, site.logo)
    elif image_url:
        organization["logo"] = image_url
    if site.phone:
        organization["telephone"] = site.phone
    if site.email:
        organization["email"] = site.email
    if site.address:
        organization["address"] = {"@type": "PostalAddress", "streetAddress": site.address}

    schema_graph = [
        organization,
        {
            "@type": "WebSite",
            "@id": f"{base_url}#website",
            "url": base_url,
            "name": site_name,
            "description": seo.default_description,
        },
    ]
    if product:
        product = dict(product)
        product.setdefault("@id", f"{canonical}#product")
        if image_url:
            product.setdefault("image", [image_url])
        schema_graph.append(product)

    return {
        "seo": seo,
        "seo_title": title,
        "seo_description": description,
        "seo_keywords": keywords,
        "seo_canonical": canonical,
        "seo_image_url": image_url,
        "seo_site_name": site_name,
        "seo_google_site_verification": seo.google_site_verification,
        "seo_noindex": noindex,
        "seo_type": seo_type,
        "seo_json_ld": mark_safe(json.dumps({"@context": "https://schema.org", "@graph": schema_graph}, ensure_ascii=False).replace("</", "<\\/")),
    }


def _base_context(request=None):
    site = SiteSettings.objects.first()
    seo = SEO.current() or SEO()
    shipping_fee, free_shipping_above = shipping_rules()
    categories = Category.objects.all()
    cart_count = 0
    customer = None
    if request is not None:
        cart_count = Cart(request).count()
        customer = _customer(request)
    noindex = bool(
        request
        and request.resolver_match
        and request.resolver_match.url_name in {"cart", "checkout", "profile", "order_success"}
    )
    context = {
        "site": site,
        "categories": categories,
        "navigation_categories": categories.prefetch_related(
            Prefetch(
                "subcategories",
                queryset=SubCategory.objects.filter(sarees__isnull=False).distinct(),
            )
        ),
        "navigation_product_types": ProductType.objects.filter(is_active=True).prefetch_related(
            Prefetch("products", queryset=Product.objects.all())
        ),
        "cart_count": cart_count,
        "customer": customer,
        "shipping_fee": shipping_fee,
        "free_shipping_above": free_shipping_above,
        "contact_map_url": _contact_map_url(site),
    }
    context.update(_seo_context(request, site=site, seo=seo, noindex=noindex))
    return context


def _customer(request):
    cid = request.session.get("customer_id")
    if cid:
        return Customer.objects.filter(pk=cid).first()
    return None


def _contact_map_url(site):
    if site and site.map_embed_url:
        source = extract_map_source(site.map_embed_url)
        if source:
            return source
    address = site.address.strip() if site and site.address else "Chennai, Tamil Nadu, India"
    return f"https://www.google.com/maps?q={quote(address)}&output=embed"


def _contact_map_link(site):
    parts = urlsplit(_contact_map_url(site))
    query = parse_qsl(parts.query, keep_blank_values=True)
    if parts.netloc.lower() in {"google.com", "www.google.com", "maps.google.com"}:
        path = parts.path
        if path.rstrip("/") == "/maps/embed":
            path = "/maps"
        query = [(key, value) for key, value in query if not (key == "output" and value == "embed")]
        return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))
    return _contact_map_url(site)


def _payee_name(site):
    """The name a UPI app shows next to the payee once the QR is scanned."""
    name = site.shop_name.strip() if site and site.shop_name else ""
    return name or DEFAULT_PAYEE_NAME


def _upi_id(site):
    """The UPI handle the payment QR collects into."""
    code = PaymentQR.current()
    configured = (code.upi_id if code else "").strip()
    return configured or DEFAULT_UPI_ID


def _upi_uri(site):
    """Build the ``upi://pay`` payload encoded into the payment QR code."""
    return f"upi://pay?pa={quote(_upi_id(site))}&pn={quote(_payee_name(site))}&cu=INR"


def _payment_qr_context(site):
    """Template context for the payment method section.

    Staff can upload their own QR image in the admin; when they have not, we
    fall back to the generated code so the section is never empty.
    """
    code = PaymentQR.current()
    return {
        "payment_qr": code,
        "payment_qr_url": code.image.url if code and code.image else reverse("store:generate_qr"),
        "payment_upi_id": _upi_id(site),
        "payment_payee_name": _payee_name(site),
    }


def robots_txt(request):
    seo = SEO.current() or SEO()
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /cart/",
        "Disallow: /checkout/",
        "Disallow: /profile/",
    ]
    if seo.robots_extra.strip():
        lines.append(seo.robots_extra.strip())
    lines.append(f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}")
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def resize_profile_logo(upload, size=PROFILE_LOGO_SIZE):
    img = PILImage.open(upload)
    img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
    img = img.resize(size, PILImage.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return ContentFile(buf.getvalue(), name=f"profile_{uuid.uuid4().hex[:8]}.png")


def _customer_name_matches(customer, submitted_name):
    return " ".join(customer.name.split()).casefold() == " ".join(submitted_name.split()).casefold()


def login_view(request):
    site = SiteSettings.objects.first()
    seo = SEO.current() or SEO()
    site_name = site.shop_name if site else seo.site_name
    seo_context = _seo_context(
        request,
        site=site,
        seo=seo,
        title=f"Login | {site_name}",
        description="Sign in to Swathi Designers to access your account and continue shopping for beautiful sarees.",
        noindex=True,
    )
    login_images = Saree.objects.filter(Q(image__gt="") | Q(image_url__gt=""))[:3]
    login_content = LoginPage.current() or LoginPage()
    error = ""
    login_errors = {}

    if request.method == "POST":
        name = " ".join(request.POST.get("name", "").split())
        phone = request.POST.get("phone", "").strip()
        digits = re.sub(r"\D", "", phone)
        customer = Customer.objects.filter(phone=digits).first() if digits else None

        if not name:
            login_errors["name"] = "Please enter name."
        elif not _is_valid_login_name(name):
            login_errors["name"] = "Please enter username"
        if not phone:
            login_errors["phone"] = "Please enter mobile number."
        elif not _is_valid_mobile(digits):
            login_errors["phone"] = PHONE_ERROR

        if not login_errors and customer and not _customer_name_matches(customer, name):
            error = "Please enter username"
            login_errors["name"] = error
        elif not login_errors and customer is None:
            customer = Customer.objects.create(phone=digits, name=name)

        if not error and not login_errors:
            _login_customer(request, customer)
            return redirect("store:home")

    return render(
        request,
        "store/login.html",
        {
            "site": site,
            "login_images": login_images,
            "login_content": login_content,
            "login_error": error,
            "login_errors": login_errors,
            **seo_context,
        },
    )


def _login_customer(request, customer):
    """Bind this browser session to ``customer``.

    The session key is rotated first so a pre-login session id can never be
    replayed. The customer's cart is stored separately against the account so
    it remains available in the customer's other signed-in browsers.
    """
    request.session.cycle_key()
    request.session["customer_id"] = customer.pk
    return customer


ADMIN_RECOVERY_CODE_LIFETIME = timedelta(minutes=10)
ADMIN_RECOVERY_CODE_COOLDOWN = timedelta(minutes=1)
ADMIN_RECOVERY_MAX_ATTEMPTS = 5
ADMIN_RECOVERY_SESSION_CODE = "admin_recovery_code_id"
ADMIN_RECOVERY_SESSION_USER = "admin_recovery_user_id"


def _admin_recovery_code_digest(user_id, code):
    return salted_hmac(
        "store.admin_recovery_code",
        f"{user_id}:{code}",
        algorithm="sha256",
    ).hexdigest()


def admin_password_reset_request(request):
    if request.method == "POST":
        form = AdminRecoveryEmailForm(request.POST)
        if form.is_valid():
            now = timezone.now()
            user_model = get_user_model()
            users = list(
                user_model._default_manager.filter(
                    email__iexact=form.cleaned_data["email"],
                    is_active=True,
                    is_staff=True,
                )[:2]
            )
            request.session.pop(ADMIN_RECOVERY_SESSION_CODE, None)
            if len(users) == 1:
                user = users[0]
                active_code = (
                    AdminRecoveryCode.objects.filter(
                        user=user,
                        used_at__isnull=True,
                        expires_at__gt=now,
                    )
                    .order_by("-created_at")
                    .first()
                )
                recent_code = (
                    AdminRecoveryCode.objects.filter(
                        user=user,
                        created_at__gte=now - ADMIN_RECOVERY_CODE_COOLDOWN,
                    )
                    .order_by("-created_at")
                    .first()
                )
                if recent_code and active_code:
                    request.session[ADMIN_RECOVERY_SESSION_CODE] = active_code.pk
                else:
                    code = f"{secrets.randbelow(1_000_000):06d}"
                    try:
                        sent = send_mail(
                            "Django admin account recovery code",
                            (
                                f"Your admin account recovery code is {code}.\n\n"
                                "Enter this code on the admin recovery page to reset your "
                                "username and password. It expires in 10 minutes. If you "
                                "did not request this, ignore this email."
                            ),
                            settings.DEFAULT_FROM_EMAIL,
                            [user.email],
                            fail_silently=False,
                        )
                    except (OSError, smtplib.SMTPException):
                        logger.exception("Admin recovery email could not be delivered.")
                        form.add_error(
                            None,
                            "We could not send a recovery code. Please try again later or contact the system owner.",
                        )
                    else:
                        if sent != 1:
                            logger.error("Admin recovery email backend sent no message.")
                            form.add_error(
                                None,
                                "We could not send a recovery code. Please try again later or contact the system owner.",
                            )
                        else:
                            sent_at = timezone.now()
                            recovery = AdminRecoveryCode.objects.create(
                                user=user,
                                code_digest=_admin_recovery_code_digest(user.pk, code),
                                expires_at=sent_at + ADMIN_RECOVERY_CODE_LIFETIME,
                            )
                            AdminRecoveryCode.objects.filter(
                                user=user,
                                used_at__isnull=True,
                            ).exclude(pk=recovery.pk).update(used_at=sent_at)
                            request.session[ADMIN_RECOVERY_SESSION_CODE] = recovery.pk
                            return redirect("admin_password_reset_verify")
            if not form.errors:
                return redirect("admin_password_reset_verify")
    else:
        form = AdminRecoveryEmailForm()

    return render(
        request,
        "admin/store/admin_recovery_request.html",
        {"form": form, "title": "Recover admin account"},
    )


def admin_password_reset_verify(request):
    recovery_id = request.session.get(ADMIN_RECOVERY_SESSION_CODE)
    recovery = None
    if recovery_id:
        recovery = (
            AdminRecoveryCode.objects.select_related("user")
            .filter(
                pk=recovery_id,
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
                attempts__lt=ADMIN_RECOVERY_MAX_ATTEMPTS,
                user__is_active=True,
                user__is_staff=True,
            )
            .first()
        )

    if request.method == "POST":
        form = AdminRecoveryCodeForm(request.POST)
        if form.is_valid() and recovery:
            now = timezone.now()
            with transaction.atomic():
                recovery = AdminRecoveryCode.objects.select_for_update().get(pk=recovery.pk)
                if (
                    recovery.used_at is None
                    and recovery.expires_at > now
                    and recovery.attempts < ADMIN_RECOVERY_MAX_ATTEMPTS
                ):
                    valid_code = hmac.compare_digest(
                        recovery.code_digest,
                        _admin_recovery_code_digest(recovery.user_id, form.cleaned_data["code"]),
                    )
                    recovery.attempts += 1
                    if valid_code:
                        recovery.used_at = now
                    elif recovery.attempts >= ADMIN_RECOVERY_MAX_ATTEMPTS:
                        recovery.used_at = now
                    recovery.save(update_fields=("attempts", "used_at"))
                else:
                    valid_code = False

            if valid_code:
                request.session.cycle_key()
                request.session[ADMIN_RECOVERY_SESSION_CODE] = recovery.pk
                request.session[ADMIN_RECOVERY_SESSION_USER] = recovery.user_id
                request.session.set_expiry(ADMIN_RECOVERY_CODE_LIFETIME.total_seconds())
                return redirect("admin_password_reset_change")
            form.add_error("code", "The code is invalid or expired. Request a new code.")
        elif form.is_valid():
            form.add_error("code", "The code is invalid or expired. Request a new code.")
    else:
        form = AdminRecoveryCodeForm()

    return render(
        request,
        "admin/store/admin_recovery_verify.html",
        {"form": form, "title": "Verify recovery code", "code_sent": recovery is not None},
    )


def _verified_admin_recovery(request):
    recovery_id = request.session.get(ADMIN_RECOVERY_SESSION_CODE)
    user_id = request.session.get(ADMIN_RECOVERY_SESSION_USER)
    if not recovery_id or not user_id:
        return None, None
    recovery = (
        AdminRecoveryCode.objects.select_related("user")
        .filter(
            pk=recovery_id,
            user_id=user_id,
            used_at__isnull=False,
            expires_at__gt=timezone.now(),
            user__is_active=True,
            user__is_staff=True,
        )
        .first()
    )
    return (recovery, recovery.user) if recovery else (None, None)


def admin_password_reset_change(request):
    recovery, user = _verified_admin_recovery(request)
    if not recovery:
        request.session.pop(ADMIN_RECOVERY_SESSION_CODE, None)
        request.session.pop(ADMIN_RECOVERY_SESSION_USER, None)
        return redirect("admin_password_reset")

    form = AdminRecoveryCredentialsForm(
        request.POST if request.method == "POST" else None,
        user=user,
    )
    if request.method == "POST" and form.is_valid():
        username_field = user.USERNAME_FIELD
        try:
            with transaction.atomic():
                recovery = AdminRecoveryCode.objects.select_for_update().filter(
                    pk=recovery.pk,
                    user_id=user.pk,
                    used_at__isnull=False,
                    expires_at__gt=timezone.now(),
                ).first()
                if not recovery:
                    request.session.pop(ADMIN_RECOVERY_SESSION_CODE, None)
                    request.session.pop(ADMIN_RECOVERY_SESSION_USER, None)
                    return redirect("admin_password_reset")

                user = get_user_model()._default_manager.select_for_update().get(pk=user.pk)
                form = AdminRecoveryCredentialsForm(request.POST, user=user)
                if form.is_valid():
                    setattr(user, username_field, form.cleaned_data["username"])
                    user.set_password(form.cleaned_data["password1"])
                    user.save(update_fields=(username_field, "password"))
                    request.session.flush()
                    return redirect("password_reset_complete")
        except IntegrityError:
            form.add_error("username", "That username is already in use.")

    return render(
        request,
        "admin/store/admin_recovery_change.html",
        {"form": form, "title": "Set new admin credentials"},
    )


def admin_password_reset_complete(request):
    return render(
        request,
        "admin/store/admin_recovery_complete.html",
        {"title": "Admin credentials updated"},
    )


def logout_view(request):
    request.session.flush()
    return redirect("store:login")

def profile(request):
    customer = _customer(request)
    if not customer:
        return redirect("store:login")

    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        digits = re.sub(r"\D", "", request.POST.get("phone", "").strip())

        if len(name) < 2:
            error = "Please enter your name."
        elif not _is_valid_mobile(digits):
            error = PHONE_ERROR
        else:
            taken = Customer.objects.filter(phone=digits).exclude(pk=customer.pk).exists()
            if taken:
                error = "This phone number is already linked to another account."
            else:
                customer.name = name
                customer.phone = digits
                if request.FILES.get("profile_image"):
                    logo = resize_profile_logo(request.FILES["profile_image"])
                    if customer.profile_image:
                        customer.profile_image.delete(save=False)
                    customer.profile_image.save(logo.name, logo, save=False)
                customer.save()
                return redirect("store:home")

    context = _base_context(request)
    context["profile_error"] = error
    return render(request, "store/profile.html", context)


def home(request):
    context = _base_context(request)
    banners = Banner.objects.filter(is_active=True)
    context["banners"] = banners

    layers = []
    for cat in Category.objects.all().order_by("order"):
        sarees = list(cat.sarees.filter(is_featured=True)[:10])
        if sarees:
            layers.append({"category": cat, "sarees": sarees})
    context["layers"] = layers
    return render(request, "store/home.html", context)


def about(request):
    context = _base_context(request)
    defaults = AboutPage()
    page = AboutPage.current() or defaults
    about_saree = Saree.objects.filter(Q(image__gt="") | Q(image_url__gt="")).first()
    image = page.image.url if page.image else (about_saree.image_source if about_saree else None)
    context.update(
        {
            "about_page": page,
            "about_image": image,
            "about_image_alt": page.title if page == defaults else (about_saree.name if about_saree else "Saree collection"),
            "about_title": page.title or defaults.title,
            "about_subtitle": page.subtitle or defaults.subtitle,
            "about_story": page.story or defaults.story,
            "about_mission": page.mission or defaults.mission,
            "delivery_commitment": page.delivery_commitment or defaults.delivery_commitment,
            "support_commitment": page.support_commitment or defaults.support_commitment,
            "exchange_commitment": page.exchange_commitment or defaults.exchange_commitment,
        }
    )
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"About Us | {site_name}",
            description=context["about_subtitle"],
            image=image,
        )
    )
    return render(request, "store/about.html", context)


def contact(request):
    context = _base_context(request)
    form = ContactForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thank you. Your enquiry has been received.")
        return redirect("store:contact")
    context.update(
        {
            "contact_form": form,
            "contact_map_url": _contact_map_url(context["site"]),
            "contact_map_link_url": _contact_map_link(context["site"]),
        }
    )
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"Contact Us | {site_name}",
            description="Contact Swathi Designers for help with saree orders, product questions, delivery updates and exchanges.",
            keywords="contact swathi designers, saree order support, saree delivery, saree exchange",
        )
    )
    return render(request, "store/contact.html", context)


def terms(request):
    context = _base_context(request)
    defaults = TermsPage()
    page = TermsPage.objects.first() or defaults
    context.update(
        {
            "terms_page": page,
            "terms_title": page.title or defaults.title,
            "terms_subtitle": page.subtitle or defaults.subtitle,
            "terms_content": page.content or defaults.content,
        }
    )
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"Terms and Conditions | {site_name}",
            description=context["terms_subtitle"],
            keywords="terms and conditions, saree shopping terms, returns policy, delivery policy",
        )
    )
    return render(request, "store/terms.html", context)


def catalog(request):
    context = _base_context(request)
    active = request.GET.get("tier", "")
    query = request.GET.get("q", "").strip()

    cats = list(Category.objects.all())
    if active:
        cats = [c for c in cats if c.tier == active]

    layers = []
    for cat in cats:
        qs = cat.sarees.all()
        if query:
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(fabric__icontains=query)
                | Q(description__icontains=query)
            )
        sarees = list(qs)
        if sarees:
            layers.append({"category": cat, "sarees": sarees})
    catalog_banner = Banner.objects.filter(is_active=True).first()
    catalog_saree = Saree.objects.filter(Q(image__gt="") | Q(image_url__gt="")).first()
    catalog_banner_image = (
        catalog_banner.image.url
        if catalog_banner and catalog_banner.image
        else (catalog_saree.image_source if catalog_saree else None)
    )
    context["catalog_banner_image"] = catalog_banner_image
    context["layers"] = layers
    context["active_tier"] = active
    context["query"] = query
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    active_category = next((cat for cat in cats if cat.tier == active), None)
    if query:
        seo_title = f"Search Results for {query} | {site_name}"
        seo_description = f"Browse sarees matching {query} and find your next favourite weave at Swathi Designers."
        seo_keywords = f"{query}, saree search, online sarees, Swathi Designers"
    elif active_category:
        seo_title = f"{active_category.title} | {site_name}"
        seo_description = active_category.subtitle or f"Explore the {active_category.title} saree collection from Swathi Designers."
        seo_keywords = f"{active_category.title}, {active_category.title.lower()} sarees, online sarees"
    else:
        seo_title = f"All Sarees | {site_name}"
        seo_description = "Explore handloom, silk, georgette and cotton sarees for weddings, festivals and everyday celebrations."
        seo_keywords = "all sarees, online sarees, handloom sarees, silk sarees, cotton sarees"
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=seo_title,
            description=seo_description,
            keywords=seo_keywords,
            image=catalog_banner_image,
            noindex=bool(query),
        )
    )
    return render(request, "store/catalog.html", context)


def all_products(request):
    context = _base_context(request)
    query = request.GET.get("q", "").strip()
    selected = request.GET.get("category", "")
    product_types = ProductType.objects.filter(is_active=True)
    collections = Category.objects.all()
    product_queryset = Product.objects.filter(product_type__is_active=True).select_related("product_type")
    saree_queryset = Saree.objects.select_related("category")

    filter_options = [
        {"value": f"product:{product_type.slug}", "label": product_type.name}
        for product_type in product_types
    ]
    filter_options.extend(
        {"value": f"saree:{category.slug}", "label": f"Sarees - {category.title}"}
        for category in collections
    )

    if selected.startswith("product:"):
        product_queryset = product_queryset.filter(product_type__slug=selected.removeprefix("product:"))
        saree_queryset = Saree.objects.none()
    elif selected.startswith("saree:"):
        saree_queryset = saree_queryset.filter(category__slug=selected.removeprefix("saree:"))
        product_queryset = Product.objects.none()

    if query:
        product_queryset = product_queryset.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(product_type__name__icontains=query)
        )
        saree_queryset = saree_queryset.filter(
            Q(name__icontains=query)
            | Q(fabric__icontains=query)
            | Q(description__icontains=query)
            | Q(category__title__icontains=query)
        )

    items = sorted(
        [*product_queryset, *saree_queryset],
        key=lambda item: item.created_at,
        reverse=True,
    )
    banner = Banner.objects.filter(is_active=True).first()
    banner_item = Product.objects.filter(product_type__is_active=True).first()
    banner_saree = Saree.objects.filter(Q(image__gt="") | Q(image_url__gt="")).first()
    banner_image = (
        banner.image.url
        if banner and banner.image
        else banner_item.image_source
        if banner_item
        else banner_saree.image_source
        if banner_saree
        else None
    )
    context.update(
        {
            "all_items": items,
            "product_filters": filter_options,
            "selected_product_filter": selected,
            "query": query,
            "catalog_banner_image": banner_image,
        }
    )
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"All Products | {site_name}",
            description="Browse sarees, jewellery, handbags and every product category at Swathi Designers.",
            keywords="all products, sarees, jewellery, handbags, online shopping",
            image=banner_image,
        )
    )
    return render(request, "store/all_products.html", context)


def category_detail(request, slug):
    category = Category.objects.filter(slug=slug).first()
    if category is None:
        legacy = list(Category.objects.filter(tier=slug)[:2])
        if len(legacy) == 1:
            return redirect(legacy[0].get_absolute_url(), permanent=True)
        raise Http404(f"No category matches the given query: {slug}")
    context = _base_context(request)
    context["category"] = category
    context["sarees"] = category.sarees.all()
    context["subcategories"] = category.subcategories.filter(sarees__isnull=False).distinct()
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"{category.title} | {site_name}",
            description=category.subtitle or f"Shop the {category.title} saree collection from Swathi Designers.",
            keywords=f"{category.title}, {category.title.lower()} sarees, saree collection",
            image=category.banner_image,
        )
    )
    return render(request, "store/category_detail.html", context)


def subcategory_detail(request, category_slug, slug):
    subcategory = get_object_or_404(
        SubCategory.objects.select_related("category"),
        category__slug=category_slug,
        slug=slug,
    )
    context = _base_context(request)
    context["subcategory"] = subcategory
    context["category"] = subcategory.category
    context["sarees"] = subcategory.sarees.all()
    context["subcategories"] = subcategory.category.subcategories.filter(
        sarees__isnull=False
    ).distinct()
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"{subcategory.title} | {site_name}",
            description=subcategory.subtitle
            or f"Shop {subcategory.title} in the {subcategory.category.title} collection from Saree Elegance.",
            keywords=(
                f"{subcategory.title.lower()}, {subcategory.title.lower()} online, "
                f"{subcategory.category.title.lower()} sarees, online sarees"
            ),
            image=subcategory.banner_image,
        )
    )
    return render(request, "store/subcategory_detail.html", context)


def saree_detail(request, slug):
    saree = get_object_or_404(Saree, slug=slug)
    related = saree.category.sarees.exclude(pk=saree.pk)[:4]
    context = _base_context(request)
    context["saree"] = saree
    context["related"] = related
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    product_description = saree.description or f"Shop the {saree.name} from the {saree.category.title} collection at Swathi Designers."
    canonical_url = _canonical_url(request, context["seo"])
    product = {
        "@type": "Product",
        "name": saree.name,
        "description": product_description,
        "brand": {"@type": "Brand", "name": site_name},
        "offers": {
            "@type": "Offer",
            "priceCurrency": "INR",
            "price": str(saree.final_amount),
            "availability": (
                "https://schema.org/InStock" if saree.in_stock else "https://schema.org/OutOfStock"
            ),
            "url": canonical_url,
        },
    }
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"{saree.name} | {site_name}",
            description=product_description,
            keywords=f"{saree.name}, {saree.fabric}, saree online, {saree.category.title}",
            image=saree.image_source,
            seo_type="product",
            product=product,
        )
    )
    return render(request, "store/saree_detail.html", context)


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.select_related("product_type"), slug=slug)
    related = Product.objects.filter(product_type=product.product_type).exclude(pk=product.pk)[:4]
    context = _base_context(request)
    context.update({"product": product, "related": related})
    site_name = context["site"].shop_name if context["site"] else context["seo"].site_name
    description = product.description or f"Shop {product.name} from {product.product_type.name} at {site_name}."
    product_schema = {
        "@type": "Product",
        "name": product.name,
        "description": description,
        "brand": {"@type": "Brand", "name": site_name},
        "offers": {
            "@type": "Offer",
            "priceCurrency": "INR",
            "price": str(product.final_amount),
            "availability": (
                "https://schema.org/InStock" if product.in_stock else "https://schema.org/OutOfStock"
            ),
            "url": _canonical_url(request, context["seo"]),
        },
    }
    context.update(
        _seo_context(
            request,
            site=context["site"],
            seo=context["seo"],
            title=f"{product.name} | {site_name}",
            description=description,
            keywords=f"{product.name}, {product.product_type.name}, online shopping",
            image=product.image_source,
            seo_type="product",
            product=product_schema,
        )
    )
    return render(request, "store/product_detail.html", context)


def add_to_cart(request):
    if request.method == "POST":
        item_type = request.POST.get("item_type", "saree")
        item_id = request.POST.get("item_id") or request.POST.get("saree_id")
        quantity = request.POST.get("quantity", 1)
        if item_type == "product":
            item = get_object_or_404(Product, pk=item_id, product_type__is_active=True)
        elif item_type == "saree":
            item = get_object_or_404(Saree, pk=item_id)
        else:
            raise Http404("Unknown product type.")
        cart = Cart(request)
        if not item.in_stock:
            message = f'"{item.name}" is out of stock and cannot be added to your cart.'
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse(
                    {"success": False, "message": message, "cart_count": cart.count()},
                    status=400,
                )
            messages.error(request, message)
        else:
            cart.add_item(item_type, item.pk, quantity)
            message = f'"{item.name}" added to your cart.'
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": message, "cart_count": cart.count()})
            messages.success(request, message)
        redirect_back = request.POST.get("redirect", "")
        if redirect_back.startswith("/") and url_has_allowed_host_and_scheme(
            redirect_back,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(redirect_back)
        return redirect("store:catalog")
    return redirect("store:catalog")


def cart_view(request):
    cart = Cart(request)
    context = _base_context(request)
    context["cart_items"] = cart.items()
    context["totals"] = cart.totals()
    context["cart_counts"] = cart.count()
    return render(request, "store/cart.html", context)


def update_cart(request, saree_id):
    if request.method == "POST":
        cart = Cart(request)
        cart.set_quantity(saree_id, request.POST.get("quantity", 1))
        messages.info(request, "Cart updated.")
    return redirect("store:cart")


def remove_from_cart(request, saree_id):
    cart = Cart(request)
    cart.remove(saree_id)
    messages.info(request, "Item removed from cart.")
    return redirect("store:cart")


def update_cart_item(request, item_type, item_id):
    if item_type not in {"saree", "product"}:
        raise Http404("Unknown product type.")
    if request.method == "POST":
        Cart(request).set_item_quantity(item_type, item_id, request.POST.get("quantity", 1))
        messages.info(request, "Cart updated.")
    return redirect("store:cart")


def remove_cart_item(request, item_type, item_id):
    if item_type not in {"saree", "product"}:
        raise Http404("Unknown product type.")
    Cart(request).remove_item(item_type, item_id)
    messages.info(request, "Item removed from cart.")
    return redirect("store:cart")


def checkout(request):
    cart = Cart(request)
    items = cart.items()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        pincode = request.POST.get("pincode", "").strip()
        payment = Order.PaymentMethod.QR

        if not items:
            messages.error(request, "Your cart is empty.")
            return redirect("store:catalog")

        checkout_errors = {}
        if not _is_valid_checkout_name(name) or len(name) > 150:
            checkout_errors["name"] = "Please enter a valid name."
        if not _is_valid_checkout_phone(phone):
            checkout_errors["phone"] = PHONE_ERROR
        if not email:
            checkout_errors["email"] = "Please enter email."
        elif len(email) > 254 or not _valid_email(email):
            checkout_errors["email"] = "Please enter a valid email address."
        if not address:
            checkout_errors["address"] = "Please enter address."
        elif len(address) > 300:
            checkout_errors["address"] = "Please enter a delivery address of 300 characters or fewer."
        if not city:
            checkout_errors["city"] = "Please enter city."
        elif not _is_valid_checkout_place(city) or len(city) > 100:
            checkout_errors["city"] = "Please enter a valid city name."
        if not state:
            checkout_errors["state"] = "Please enter state."
        elif not _is_valid_checkout_place(state) or len(state) > 100:
            checkout_errors["state"] = "Please enter a valid state name."
        if not pincode:
            checkout_errors["pincode"] = "Please enter pincode."
        elif not re.fullmatch(r"[0-9]{6}", pincode):
            checkout_errors["pincode"] = "Please enter a valid 6-digit PIN code."
        proof_files = request.FILES.copy()
        if request.FILES.get("payment_screenshot"):
            proof_files["screenshot"] = request.FILES["payment_screenshot"]
        proof_form = PaymentProofForm(request.POST, proof_files)
        if not proof_form.is_valid():
            checkout_errors["payment_screenshot"] = (
                "Please upload payment screenshot."
                if not request.FILES.get("payment_screenshot")
                else "Please upload valid payment receipt."
            )

        if checkout_errors:
            checkout_error = next(iter(checkout_errors.values()))
            context = _base_context(request)
            context.update(
                {
                    "cart_items": items,
                    "totals": cart.totals(),
                    "payment_methods": CHECKOUT_PAYMENT_METHODS,
                    "checkout_error": checkout_error,
                    "checkout_errors": checkout_errors,
                    "proof_form": proof_form,
                    "checkout_values": {
                        "name": request.POST.get("name", ""),
                        "phone": request.POST.get("phone", ""),
                        "email": email,
                        "address": address,
                        "city": city,
                        "state": state,
                        "pincode": pincode,
                        "payment_reference": request.POST.get("payment_reference", ""),
                    },
                }
            )
            context.update(_payment_qr_context(context["site"]))
            return render(request, "store/checkout.html", context)

        valid_payment = [c[0] for c in CHECKOUT_PAYMENT_METHODS]
        if payment not in valid_payment:
            payment = Order.PaymentMethod.QR

        totals = cart.totals()
        order = Order(
            order_id=new_order_id(),
            name=name or "Guest",
            phone=phone,
            email=email,
            address=address,
            city=city,
            state=state,
            pincode=pincode,
            payment_method=payment,
            payment_status=Order.Status.PAID,
            subtotal=totals["subtotal"],
            delivery_charge=totals["delivery"],
            gst=totals["gst"],
            total=totals["total"],
        )
        order.save()
        for item in items:
            product = item["product"] if item["kind"] == "product" else None
            saree = item["saree"]
            order_item = item["product"]
            OrderItem.objects.create(
                order=order,
                saree=saree,
                product=product,
                name=order_item.name,
                price=order_item.final_amount,
                quantity=item["quantity"],
                delivery_charge=order_item.delivery_charge,
                gst_percent=order_item.gst_percent,
            )
        PaymentProof(
            order=order,
            customer=_customer(request),
            customer_name=order.name,
            phone=order.phone,
            amount=order.total,
            payment_method=order.payment_method,
            reference=(request.POST.get("payment_reference") or "").strip(),
            screenshot=proof_form.cleaned_data["screenshot"],
        ).save()
        cart.clear()
        request.session["last_order_id"] = order.order_id
        return redirect("store:order_success", order_id=order.order_id)
    totals = cart.totals()
    context = _base_context(request)
    context["cart_items"] = items
    context["totals"] = totals
    context["payment_methods"] = CHECKOUT_PAYMENT_METHODS
    context.update(_payment_qr_context(context["site"]))
    return render(request, "store/checkout.html", context)


def _is_valid_checkout_name(name):
    has_letter = False
    for character in name:
        category = unicodedata.category(character)
        if category.startswith("L"):
            has_letter = True
        elif category.startswith("M") or character in " .'-":
            continue
        else:
            return False
    return has_letter


def _is_valid_login_name(name):
    if len(name) > 150:
        return False
    has_letter = False
    for character in name:
        category = unicodedata.category(character)
        if category.startswith("L"):
            has_letter = True
        elif category.startswith("M") or character == " ":
            continue
        else:
            return False
    return has_letter


def _is_valid_checkout_phone(phone):
    return _is_valid_mobile(phone or "")


def _valid_email(value):
    try:
        EmailValidator()(value)
    except ValidationError:
        return False
    return True


def _is_valid_mobile(digits):
    """True only for an Indian mobile number: 10 digits starting 6-9."""
    return re.fullmatch(r"[6-9][0-9]{9}", digits or "") is not None


def _is_valid_checkout_place(value):
    has_letter = False
    for character in value:
        category = unicodedata.category(character)
        if category.startswith("L"):
            has_letter = True
        elif category.startswith("M") or character in " .-":
            continue
        else:
            return False
    return has_letter


def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    context = _base_context(request)
    context["order"] = order
    context.update(_payment_qr_context(context["site"]))
    proof_form = PaymentProofForm(initial={"order_id": order.order_id})
    context["proof_form"] = proof_form
    context["proofs"] = order.payment_proofs.all()
    return render(request, "store/order_success.html", context)


def _customer_owns_order(request, customer, order):
    """Only the shopper who placed an order may attach a payment screenshot.

    A phone number typed at checkout may differ from the profile number, so the
    order placed in this session counts as theirs too.
    """
    if order is None:
        return True
    if request.session.get("last_order_id") == order.order_id:
        return True
    phone = getattr(customer, "phone", "")
    return bool(phone) and order.phone == phone


def payment_verification(request, order_id=None):
    """Let a customer upload the payment screenshot for staff to verify.

    The screenshot is stored against the order so the admin list always shows
    who paid, which order it covers, the amount and when it arrived.
    """
    customer = _customer(request)
    order = None
    requested_order_id = order_id or request.POST.get("order_id") or ""
    if requested_order_id:
        order = get_object_or_404(Order, order_id=requested_order_id)
        if not _customer_owns_order(request, customer, order):
            raise Http404("No order matches this account.")

    initial = {"order_id": order.order_id if order else ""}
    if request.method == "POST":
        form = PaymentProofForm(request.POST, request.FILES)
        if form.is_valid():
            if order is None:
                # Fall back to the shopper's most recent order so the upload is
                # never lost, even if the order ID field was left blank.
                order = (
                    Order.objects.filter(phone=getattr(customer, "phone", "")).order_by("-created_at").first()
                )
            proof = PaymentProof(
                order=order,
                customer=customer,
                customer_name=(getattr(customer, "name", "") or (order.name if order else "") or "Guest"),
                phone=(order.phone if order else getattr(customer, "phone", "")),
                amount=order.total if order else Decimal("0.00"),
                payment_method=order.payment_method if order else Order.PaymentMethod.QR,
                reference=form.cleaned_data.get("reference", ""),
                notes=form.cleaned_data.get("notes", ""),
                screenshot=form.cleaned_data["screenshot"],
            )
            proof.save()
            messages.success(request, "Payment screenshot received. We will verify it shortly.")
            if order is not None:
                return redirect("store:order_success", order_id=order.order_id)
            return redirect("store:home")
    else:
        form = PaymentProofForm(initial=initial)

    context = _base_context(request)
    context.update({"form": form, "order": order})
    context.update(_payment_qr_context(context["site"]))
    return render(request, "store/payment_verification.html", context)


def _qr_monogram_font(size):
    for path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_qr_monogram(image, payee_name):
    """Stamp the shop's initials into the middle, the way real UPI QRs carry a logo."""
    draw = ImageDraw.Draw(image)
    side = max(30, int(image.width * 0.16))
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    inset = max(3, side // 14)
    draw.rounded_rectangle(
        (left, top, left + side, top + side),
        radius=side // 5,
        fill="white",
        outline=(214, 209, 194),
        width=max(2, side // 24),
    )
    initials = "".join(word[0] for word in payee_name.split()[:2]).upper() or "UP"
    font = _qr_monogram_font(int(side * 0.42))
    box = draw.textbbox((0, 0), initials, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(
        ((image.width - width) / 2 - box[0], (image.height - height) / 2 - box[1]),
        initials,
        font=font,
        fill=(17, 24, 22),
    )
    # Keeps the badge sitting on white so the surrounding modules stay scannable.
    draw.rounded_rectangle(
        (left - inset, top - inset, left + side + inset, top + side + inset),
        radius=side // 5,
        outline="white",
        width=inset,
    )


def _render_payment_qr(payload, payee_name):
    """Draw a crisp, shop branded UPI style QR instead of a plain black square."""
    import segno

    matrix = list(segno.make_qr(payload, error="h").matrix_iter(border=4))
    scale = 12
    image = PILImage.new("RGB", (len(matrix[0]) * scale, len(matrix) * scale), "white")
    draw = ImageDraw.Draw(image)
    ink = (16, 22, 20)
    radius = max(2, scale // 3)
    for y, row in enumerate(matrix):
        for x, bit in enumerate(row):
            if not bit:
                continue
            left = x * scale
            top = y * scale
            # Modules touch edge to edge so scanners read the code as one piece.
            draw.rounded_rectangle(
                (left, top, left + scale - 1, top + scale - 1),
                radius=radius,
                fill=ink,
            )
    _draw_qr_monogram(image, payee_name)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def generate_qr(request):
    site = SiteSettings.objects.first()
    payload = _upi_uri(site)
    try:
        png = _render_payment_qr(payload, _payee_name(site))
    except Exception:
        logger.exception("Could not build the payment QR for %s", payload)
        return HttpResponseNotFound("QR unavailable")

    response = HttpResponse(png, content_type="image/png")
    # The payload only changes when staff edit the UPI id or shop name, so the
    # browser can keep serving the same image between the two edits.
    response["Cache-Control"] = "private, max-age=3600"
    return response


def new_order_id():
    """Build today's order ID as ``YYYYMMDD`` + a zero padded 4 digit sequence.

    The first order placed on a day gets ``0001``, the next ``0002`` and so on,
    so every ID is 12 characters long and sorts chronologically as text.
    """
    prefix = timezone.localdate().strftime("%Y%m%d")
    taken = set(
        Order.objects.filter(order_id__startswith=prefix).values_list("order_id", flat=True)
    )
    for sequence in range(1, 10000):
        candidate = f"{prefix}{sequence:04d}"
        if candidate not in taken:
            return candidate
    return f"{prefix}{uuid.uuid4().hex[:4]}"
