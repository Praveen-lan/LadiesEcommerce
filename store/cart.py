from decimal import Decimal

from .models import Saree, SiteSettings
from .pricing import (
    FREE_SHIPPING_ABOVE,
    GST_RATE,
    SHIPPING_FEE,
    SHIPPING_FEE_ABOVE,
    gst_amount,
    to_amount,
)

__all__ = [
    "Cart",
    "GST_RATE",
    "FREE_SHIPPING_ABOVE",
    "SHIPPING_FEE",
    "SHIPPING_FEE_ABOVE",
    "shipping_rules",
]


def shipping_rules():
    """Return the (delivery fee, free delivery limit) pair to charge with.

    The values come from Site Settings so they can be changed from the admin,
    and fall back to the built-in defaults when no settings row exists yet.
    """
    settings = SiteSettings.objects.first()
    if settings is None:
        return SHIPPING_FEE, SHIPPING_FEE_ABOVE
    return to_amount(settings.shipping_fee), to_amount(settings.free_shipping_above)


class Cart:
    """Shopping cart scoped to a single browser session.

    The cart lives in ``request.session`` only. Nothing about the cart is keyed
    on the customer account, so signing in on one browser never reveals or
    reuses cart contents from another browser or device.
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session

    def _session_cart(self):
        cart = self.session.get("cart")
        if not isinstance(cart, dict) or not cart:
            cart = {}
            self.session["cart"] = cart
        return cart

    def _save_session_cart(self, cart):
        self.session["cart"] = cart
        self.session.modified = True

    def add(self, saree_id, quantity=1):
        qty = int(quantity)
        if qty <= 0:
            return
        cart = self._session_cart()
        key = str(saree_id)
        cart[key] = cart.get(key, 0) + qty
        self._save_session_cart(cart)

    def set_quantity(self, saree_id, quantity):
        qty = int(quantity)
        cart = self._session_cart()
        key = str(saree_id)
        if key not in cart:
            return
        if qty <= 0:
            self.remove(saree_id)
            return
        cart[key] = qty
        self._save_session_cart(cart)

    def remove(self, saree_id):
        cart = self._session_cart()
        key = str(saree_id)
        if key in cart:
            del cart[key]
            self._save_session_cart(cart)

    def clear(self):
        self._save_session_cart({})

    def count(self):
        total = 0
        for qty in self._session_cart().values():
            try:
                total += int(qty)
            except (TypeError, ValueError):
                continue
        return total

    def items(self):
        """Return list of {saree, quantity, line_total} dicts."""
        cart = self._session_cart()
        try:
            ids = [int(key) for key in cart.keys()]
        except (TypeError, ValueError):
            ids = []
        lookup = {s.pk: s for s in Saree.objects.filter(pk__in=ids)}
        result = []
        for key, qty in cart.items():
            try:
                saree = lookup.get(int(key))
                qty = int(qty)
            except (TypeError, ValueError):
                continue
            if saree is None or qty <= 0:
                continue
            result.append(
                {
                    "saree": saree,
                    "quantity": qty,
                    "final_amount": saree.final_amount,
                    "line_total": saree.final_amount * qty,
                    "delivery_charge": saree.delivery_charge * qty,
                    "gst_percent": saree.gst_percent,
                    "gst_amount": gst_amount(saree.final_amount * qty, saree.gst_percent),
                }
            )
        return result

    def totals(self):
        items = self.items()
        subtotal = sum((i["line_total"] for i in items), Decimal("0"))
        fee, limit = shipping_rules()
        base_delivery = fee if 0 < subtotal < limit else Decimal("0.00")
        product_delivery = sum((item["delivery_charge"] for item in items), Decimal("0.00"))
        delivery = base_delivery + product_delivery
        gst = sum((item["gst_amount"] for item in items), Decimal("0.00"))
        gst_by_percent = {}
        for item in items:
            percent = item["gst_percent"]
            gst_by_percent[percent] = gst_by_percent.get(percent, Decimal("0.00")) + item["gst_amount"]
        total = (subtotal + delivery + gst).quantize(Decimal("0.01"))
        return {
            "subtotal": subtotal,
            "delivery": delivery,
            "gst": gst,
            "gst_breakdown": [
                {"percent": percent, "amount": amount}
                for percent, amount in sorted(gst_by_percent.items())
            ],
            "total": total,
            "delivery_fee": fee,
            "base_delivery": base_delivery,
            "product_delivery": product_delivery,
            "free_shipping_above": limit,
            "amount_to_free_shipping": max(limit - subtotal, Decimal("0.00")),
            "free_shipping_message": subtotal > 0 and subtotal < limit,
        }
