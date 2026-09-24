import random
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from PIL import Image as PILImage
from .cart import Cart, FREE_SHIPPING_ABOVE
from .models import (
    Banner,
    Category,
    Customer,
    Order,
    OrderItem,
    OTPRequest,
    Saree,
    SiteSettings,
)

PROFILE_LOGO_SIZE = (300, 300)


def _base_context(request=None):
    settings = SiteSettings.objects.first()
    cart_count = 0
    customer = None
    if request is not None:
        cart_count = Cart(request).count()
        customer = _customer(request)
    return {
        "site": settings,
        "categories": Category.objects.all(),
        "cart_count": cart_count,
        "customer": customer,
    }


def _customer(request):
    cid = request.session.get("customer_id")
    if cid:
        return Customer.objects.filter(pk=cid).first()
    return None


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


def login_view(request):
    site = SiteSettings.objects.first()
    login_images = Saree.objects.exclude(image="")[:3]
    error = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        digits = re.sub(r"\D", "", phone)

        if len(name) < 2:
            error = "Please enter your name."
        elif not re.fullmatch(r"[0-9+()\-\s]{10,20}", phone) or len(digits) < 10:
            error = "Please enter a valid phone number."
        else:
            otp = new_otp(digits)
            request.session["visitor_name"] = name
            request.session["visitor_phone"] = digits
            request.session["otp_pending"] = True
            request.session["dev_otp"] = otp
            return redirect("store:login")

    show_otp = bool(request.session.get("otp_pending"))
    return render(
        request,
        "store/login.html",
        {
            "site": site,
            "login_images": login_images,
            "login_error": error,
            "show_otp": show_otp,
            "dev_otp": request.session.get("dev_otp", ""),
            "step_phone": request.session.get("visitor_phone", ""),
            "step_name": request.session.get("visitor_name", ""),
        },
    )


def new_otp(phone):
    code = f"{random.randint(0, 999999):06d}"
    OTPRequest.objects.create(
        phone=phone,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return code


def verify_otp(request):
    site = SiteSettings.objects.first()
    login_images = Saree.objects.exclude(image="")[:3]

    if request.method != "POST":
        return redirect("store:login")

    phone = request.session.get("visitor_phone", "")
    name = request.session.get("visitor_name", "")
    code = request.POST.get("otp", "").strip()
    error = ""

    if not phone:
        return redirect("store:login")

    otp = OTPRequest.objects.filter(phone=phone, is_verified=False).first()

    if otp is not None and not otp.is_expired and not otp.is_locked and code.isdigit() and otp.code == code:
        otp.is_verified = True
        otp.save(update_fields=["is_verified"])
        customer, _ = Customer.objects.get_or_create(phone=phone, defaults={"name": name})
        if name:
            customer.name = name
        customer.save()
        request.session["customer_id"] = customer.pk
        request.session.pop("otp_pending", None)
        request.session.pop("dev_otp", None)
        return redirect("store:home")

    fresh = new_otp(phone)
    request.session["dev_otp"] = fresh
    error = "Your OTP was incorrect or expired. A new random OTP has been generated."

    return render(
        request,
        "store/login.html",
        {
            "site": site,
            "login_images": login_images,
            "login_error": error,
            "show_otp": True,
            "dev_otp": request.session.get("dev_otp", ""),
            "step_phone": phone,
            "step_name": name,
        },
    )


def logout_view(request):
    for key in ("customer_id", "visitor_name", "visitor_phone", "otp_pending", "dev_otp"):
        request.session.pop(key, None)
    request.session.modified = True
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
        sarees = list(cat.sarees.all()[:10])
        if sarees:
            layers.append({"category": cat, "sarees": sarees})
    context["layers"] = layers
    return render(request, "store/home.html", context)


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
    context["layers"] = layers
    context["active_tier"] = active
    context["query"] = query
    return render(request, "store/catalog.html", context)


def category_detail(request, tier):
    category = get_object_or_404(Category, tier=tier)
    context = _base_context(request)
    context["category"] = category
    context["sarees"] = category.sarees.all()
    return render(request, "store/category_detail.html", context)


def saree_detail(request, slug):
    saree = get_object_or_404(Saree, slug=slug)
    related = saree.category.sarees.exclude(pk=saree.pk)[:4]
    context = _base_context(request)
    context["saree"] = saree
    context["related"] = related
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
        payment = request.POST.get("payment_method", "cod")

        if not items:
            messages.error(request, "Your cart is empty.")
            return redirect("store:catalog")

        valid_payment = [c[0] for c in Order.PaymentMethod.choices]
        if payment not in valid_payment:
            payment = "cod"

        totals = cart.totals()
        order = Order(
            order_id=random_id(),
            name=name or "Guest",
            phone=phone,
            email=email,
            address=address,
            city=city,
            state=state,
            pincode=pincode,
            payment_method=payment,
            payment_status=Order.Status.PAID if payment != "cod" else Order.Status.PENDING,
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
    context["payment_methods"] = Order.PaymentMethod.choices
    return render(request, "store/checkout.html", context)


def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    context = _base_context(request)
    context["order"] = order
    return render(request, "store/order_success.html", context)


def generate_qr(request):
    mail = request.GET.get("upi", "sareeelegance@upi")
    try:
        import segno

        qr = segno.make_qr(f"upi://pay?pa={mail}&pn=Saree%20Elegance")
        from django.http import HttpResponse

        response = HttpResponse(content_type="image/png")
        qr.save(response, kind="png", scale=8, border=2)
        return response
    except Exception:
        from django.http import HttpResponseNotFound

        return HttpResponseNotFound("QR unavailable")


def random_id():
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    return f"SE{stamp}{random.randint(100, 999)}"