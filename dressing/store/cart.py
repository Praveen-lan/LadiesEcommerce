from decimal import Decimal

from .models import CartItem, Saree

GST_RATE = Decimal("0.05")
FREE_SHIPPING_ABOVE = Decimal("1499")
SHIPPING_FEE = Decimal("79")
SHIPPING_FEE_ABOVE = Decimal("999")


class Cart:
    """Shopping cart persisted per customer account.

    A signed-in customer's cart lives in the database (see ``CartItem``), so it
    follows the account across browsers and devices. Anonymous visitors fall
    back to a session cart, which is merged into the account cart at login.
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.customer_id = self.session.get("customer_id")

    @property
    def is_persisted(self):
        return self.customer_id is not None

    def _session_cart(self):
        cart = self.session.get("cart")
        if not cart:
            cart = self.session["cart"] = {}
        return cart

    def _save_session_cart(self, cart):
        self.session["cart"] = cart
        self.session.modified = True

    def add(self, saree_id, quantity=1):
        qty = int(quantity)
        if qty <= 0:
            return
        if self.is_persisted:
            item = CartItem.objects.filter(customer_id=self.customer_id, saree_id=saree_id).first()
            if item is None:
                CartItem.objects.create(customer_id=self.customer_id, saree_id=saree_id, quantity=qty)
            else:
                item.quantity += qty
                item.save(update_fields=["quantity", "updated_at"])
            return
        cart = self._session_cart()
        key = str(saree_id)
        cart[key] = cart.get(key, 0) + qty
        self._save_session_cart(cart)

    def set_quantity(self, saree_id, quantity):
        qty = int(quantity)
        if self.is_persisted:
            if qty <= 0:
                self.remove(saree_id)
                return
            CartItem.objects.filter(customer_id=self.customer_id, saree_id=saree_id).update(quantity=qty)
            return
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
        if self.is_persisted:
            CartItem.objects.filter(customer_id=self.customer_id, saree_id=saree_id).delete()
            return
        cart = self._session_cart()
        key = str(saree_id)
        if key in cart:
            del cart[key]
            self._save_session_cart(cart)

    def clear(self):
        if self.is_persisted:
            CartItem.objects.filter(customer_id=self.customer_id).delete()
        self._save_session_cart({})

    def merge_guest_cart(self):
        """Fold a guest session cart into the signed-in customer's saved cart.

        Must be called with ``customer_id`` already present in the session.
        """
        guest = self.session.get("cart") or {}
        if guest:
            for key, qty in guest.items():
                try:
                    saree_id = int(key)
                    qty = int(qty)
                except (TypeError, ValueError):
                    continue
                if qty <= 0 or not Saree.objects.filter(pk=saree_id).exists():
                    continue
                item = CartItem.objects.filter(customer_id=self.customer_id, saree_id=saree_id).first()
                if item is None:
                    CartItem.objects.create(customer_id=self.customer_id, saree_id=saree_id, quantity=qty)
                else:
                    item.quantity += qty
                    item.save(update_fields=["quantity", "updated_at"])
        self._save_session_cart({})

    def count(self):
        if self.is_persisted:
            return sum(CartItem.objects.filter(customer_id=self.customer_id).values_list("quantity", flat=True))
        total = 0
        for qty in self._session_cart().values():
            try:
                total += int(qty)
            except (TypeError, ValueError):
                continue
        return total

    def items(self):
        """Return list of {saree, quantity, line_total} dicts."""
        if self.is_persisted:
            rows = (
                CartItem.objects.filter(customer_id=self.customer_id)
                .select_related("saree")
                .order_by("updated_at", "id")
            )
            return [
                {
                    "saree": row.saree,
                    "quantity": row.quantity,
                    "line_total": row.saree.price * row.quantity,
                }
                for row in rows
            ]

        cart = self._session_cart()
        try:
            ids = [int(k) for k in cart.keys()]
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
