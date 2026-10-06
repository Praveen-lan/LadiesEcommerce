from decimal import Decimal

from .models import Saree, SiteSettings
from .pricing import (
    FREE_SHIPPING_ABOVE,
    GST_RATE,
    SHIPPING_FEE,
    SHIPPING_FEE_ABOVE,
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
                }
            )
        return result

    def totals(self):
        items = self.items()
        subtotal = sum((i["line_total"] for i in items), Decimal("0"))
        fee, limit = shipping_rules()
        delivery = Decimal("0")
        if 0 < subtotal < limit:
            delivery = fee
        gst = (subtotal * GST_RATE).quantize(Decimal("0.01"))
        total = (subtotal + delivery + gst).quantize(Decimal("0.01"))
        return {
            "subtotal": subtotal,
            "delivery": delivery,
            "gst": gst,
            "total": total,
            "delivery_fee": fee,
            "free_shipping_above": limit,
            "amount_to_free_shipping": max(limit - subtotal, Decimal("0.00")),
            "free_shipping_message": subtotal > 0 and subtotal < limit,
        }
