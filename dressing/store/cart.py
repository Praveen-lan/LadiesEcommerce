from decimal import Decimal

from .models import Saree

GST_RATE = Decimal("0.05")
FREE_SHIPPING_ABOVE = Decimal("1499")
SHIPPING_FEE = Decimal("79")
SHIPPING_FEE_ABOVE = Decimal("999")


class Cart:
    """Session based shopping cart stored as {saree_id: quantity}."""

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get("cart")
        if not cart:
            cart = self.session["cart"] = {}
        self.cart = cart

    def add(self, saree_id, quantity=1):
        qty = int(quantity)
        if qty <= 0:
            return
        key = str(saree_id)
        self.cart[key] = self.cart.get(key, 0) + qty
        self.session["cart"] = self.cart
        self.session.modified = True

    def set_quantity(self, saree_id, quantity):
        key = str(saree_id)
        if key not in self.cart:
            return
        qty = int(quantity)
        if qty <= 0:
            self.remove(saree_id)
            return
        self.cart[key] = qty
        self.session["cart"] = self.cart
        self.session.modified = True

    def remove(self, saree_id):
        key = str(saree_id)
        if key in self.cart:
            del self.cart[key]
            self.session["cart"] = self.cart
            self.session.modified = True

    def clear(self):
        self.session["cart"] = {}
        self.session.modified = True

    def count(self):
        total = 0
        for qty in self.cart.values():
            total += qty
        return total

    def items(self):
        """Return list of {saree, quantity, line_total} tuples."""
        result = []
        ids = [int(k) for k in self.cart.keys()]
        sarees = Saree.objects.filter(pk__in=ids)
        lookup = {s.pk: s for s in sarees}
        for key, qty in self.cart.items():
            saree = lookup.get(int(key))
            if saree is None:
                continue
            result.append({"saree": saree, "quantity": qty, "line_total": saree.price * qty})
        return result

    def totals(self):
        items = self.items()
        subtotal = sum(i["line_total"] for i in items)
        delivery = Decimal("0")
        if subtotal == 0:
            pass
        elif subtotal < SHIPPING_FEE_ABOVE:
            delivery = SHIPPING_FEE
        else:
            delivery = Decimal("0")
        gst = (subtotal * GST_RATE).quantize(Decimal("0.01"))
        total = (subtotal + delivery + gst).quantize(Decimal("0.01"))
        return {
            "subtotal": subtotal,
            "delivery": delivery,
            "gst": gst,
            "total": total,
            "free_shipping_message": subtotal > 0 and subtotal < FREE_SHIPPING_ABOVE,
        }