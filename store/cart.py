from decimal import Decimal

from .models import Saree

GST_RATE = Decimal("0.05")
FREE_SHIPPING_ABOVE = Decimal("1499")
SHIPPING_FEE = Decimal("79")
SHIPPING_FEE_ABOVE = Decimal("999")


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
            result.append({"saree": saree, "quantity": qty, "line_total": saree.price * qty})
        return result

    def totals(self):
        items = self.items()
        subtotal = sum((i["line_total"] for i in items), Decimal("0"))
        delivery = Decimal("0")
        if 0 < subtotal < SHIPPING_FEE_ABOVE:
            delivery = SHIPPING_FEE
        gst = (subtotal * GST_RATE).quantize(Decimal("0.01"))
        total = (subtotal + delivery + gst).quantize(Decimal("0.01"))
        return {
            "subtotal": subtotal,
            "delivery": delivery,
            "gst": gst,
            "total": total,
            "free_shipping_message": subtotal > 0 and subtotal < FREE_SHIPPING_ABOVE,
        }
