import json
import logging
import random
import re
import uuid
import unicodedata
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.safestring import mark_safe
from PIL import Image as PILImage
from .cart import Cart, FREE_SHIPPING_ABOVE
from .forms import ContactForm, PasswordResetForm
from .models import (
    AboutPage,
    Banner,
    Category,
    Customer,
    Order,
    OrderItem,
    Saree,
    SEO,
    SiteSettings,
    SubCategory,
    TermsPage,
)

logger = logging.getLogger(__name__)

PROFILE_LOGO_SIZE = (300, 300)

CHECKOUT_PAYMENT_METHODS = ((Order.PaymentMethod.QR, Order.PaymentMethod.QR.label),)


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
        "categories": Category.objects.prefetch_related("subcategories"),
        "cart_count": cart_count,
        "customer": customer,
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
        return site.map_embed_url
    address = site.address.strip() if site and site.address else "Chennai, Tamil Nadu, India"
    return f"https://www.google.com/maps?q={quote(address)}&output=embed"


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
    error = ""

    if request.method == "POST":
        name = " ".join(request.POST.get("name", "").split())
        phone = request.POST.get("phone", "").strip()
        digits = re.sub(r"\D", "", phone)
        customer = Customer.objects.filter(phone=digits).first() if digits else None

        if len(name) < 2:
            error = "Please enter your name."
        elif not re.fullmatch(r"[0-9+()\-\s]{10,20}", phone) or len(digits) < 10:
            error = "Please enter a valid phone number."
        elif customer and not _customer_name_matches(customer, name):
            error = "This mobile number is already registered under a different name."
        elif customer is None:
            customer = Customer.objects.create(phone=digits, name=name)

        if not error:
            _login_customer(request, customer)
            return redirect("store:home")

    return render(
        request,
        "store/login.html",
        {
            "site": site,
            "login_images": login_images,
            "login_error": error,
            **seo_context,
        },
    )


def _login_customer(request, customer):
    """Bind this browser session to ``customer``.

    The session key is rotated first so a pre-login session id can never be
    replayed, and no leftover sign-in state is carried across the handover. All
    per-visitor state (including the cart) stays inside this session, so it is
    never visible to another browser.
    """
    request.session.cycle_key()
    request.session["customer_id"] = customer.pk
    return customer


class StorePasswordContextMixin:
    """Render the storefront chrome (nav, footer, SEO) on auth templates."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_base_context(self.request))
        context["seo_noindex"] = True
        return context


class StorePasswordResetView(StorePasswordContextMixin, auth_views.PasswordResetView):
    template_name = "store/password_reset_form.html"
    form_class = PasswordResetForm
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except Exception:
            logger.exception("Password reset email could not be delivered.")
            form.add_error(
                None,
                "We could not send the reset email just now. Please try again in a few minutes.",
            )
            return self.form_invalid(form)


class StorePasswordResetDoneView(StorePasswordContextMixin, auth_views.PasswordResetDoneView):
    template_name = "store/password_reset_done.html"


class StorePasswordResetConfirmView(StorePasswordContextMixin, auth_views.PasswordResetConfirmView):
    template_name = "store/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")


class StorePasswordResetCompleteView(StorePasswordContextMixin, auth_views.PasswordResetCompleteView):
    template_name = "store/password_reset_complete.html"


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
        elif len(digits) < 10:
            error = "Please enter a valid phone number."
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
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thank you. Your enquiry has been received.")
        return redirect("store:contact")
    context.update({"contact_form": form, "contact_map_url": _contact_map_url(context["site"])})
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
    context["subcategories"] = category.subcategories.all()
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
    context["subcategories"] = subcategory.category.subcategories.all()
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
            "price": str(saree.price),
            "availability": "https://schema.org/InStock",
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


def add_to_cart(request):
    if request.method == "POST":
        saree_id = request.POST.get("saree_id")
        quantity = request.POST.get("quantity", 1)
        saree = get_object_or_404(Saree, pk=saree_id)
        cart = Cart(request)
        cart.add(saree.id, quantity)
        messages.success(request, f'"{saree.name}" added to your cart.')
        redirect_back = request.POST.get("redirect") or "store:catalog"
        if redirect_back == "store:cart":
            return redirect("store:cart")
        return redirect(redirect_back)
    return redirect("store:catalog")


def cart_view(request):
    cart = Cart(request)
    context = _base_context(request)
    context["cart_items"] = cart.items()
    context["totals"] = cart.totals()
    context["cart_counts"] = cart.count()
    context["free_ship_above"] = FREE_SHIPPING_ABOVE
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


def checkout(request):
    cart = Cart(request)
    items = cart.items()
    customer = _customer(request)
    if request.method == "POST":
        name = request.POST.get("name", "").strip() or (customer.name if customer else "")
        phone = request.POST.get("phone", "").strip() or (customer.phone if customer else "")
        email = request.POST.get("email", "").strip()
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        pincode = request.POST.get("pincode", "").strip()
        payment = Order.PaymentMethod.QR

        if not items:
            messages.error(request, "Your cart is empty.")
            return redirect("store:catalog")

        checkout_error = None
        checkout_error_field = None
        if not _is_valid_checkout_name(name):
            checkout_error = "Please enter a valid name."
            checkout_error_field = "name"
        elif not _is_valid_checkout_phone(phone):
            checkout_error = "Please enter a valid 10-digit phone number."
            checkout_error_field = "phone"
        elif not _is_valid_checkout_place(city):
            checkout_error = "Please enter a valid city name."
            checkout_error_field = "city"
        elif state and not _is_valid_checkout_place(state):
            checkout_error = "Please enter a valid state name."
            checkout_error_field = "state"

        if checkout_error:
            context = _base_context(request)
            context.update(
                {
                    "cart_items": items,
                    "totals": cart.totals(),
                    "payment_methods": CHECKOUT_PAYMENT_METHODS,
                    "checkout_error": checkout_error,
                    "checkout_error_field": checkout_error_field,
                    "checkout_values": {
                        "name": request.POST.get("name", ""),
                        "phone": request.POST.get("phone", ""),
                        "email": email,
                        "address": address,
                        "city": city,
                        "state": state,
                        "pincode": pincode,
                    },
                }
            )
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
            OrderItem.objects.create(
                order=order,
                saree=item["saree"],
                name=item["saree"].name,
                price=item["saree"].price,
                quantity=item["quantity"],
            )
        cart.clear()
        return redirect("store:order_success", order_id=order.order_id)
    totals = cart.totals()
    context = _base_context(request)
    context["cart_items"] = items
    context["totals"] = totals
    context["payment_methods"] = CHECKOUT_PAYMENT_METHODS
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


def _is_valid_checkout_phone(phone):
    return re.fullmatch(r"[0-9]{10}", phone) is not None


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
    return render(request, "store/order_success.html", context)


def generate_qr(request):
    mail = request.GET.get("upi", "sareeelegance@upi")
    try:
        import segno

        qr = segno.make_qr(f"upi://pay?pa={mail}&pn=Swathi%20Designers")

        response = HttpResponse(content_type="image/png")
        qr.save(response, kind="png", scale=8, border=2)
        return response
    except Exception:
        from django.http import HttpResponseNotFound

        return HttpResponseNotFound("QR unavailable")


def new_order_id():
    date_id = timezone.localdate().strftime("%Y%m%d")
    if not Order.objects.filter(order_id=date_id).exists():
        return date_id
    for suffix in range(2, 100):
        candidate = f"{date_id}-{suffix}"
        if not Order.objects.filter(order_id=candidate).exists():
            return candidate
    return f"{date_id}-{uuid.uuid4().hex[:4]}"
