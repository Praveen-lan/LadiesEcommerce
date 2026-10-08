from decimal import Decimal

from django.db import transaction
from django.db.models import F

from .models import CartItem, Customer, Saree, ShoppingCart, SiteSettings
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
    """Shopping cart shared across browsers for a signed-in customer.

    Signed-in carts are stored against the customer account. A browser session
    is used only when no valid customer is attached to the request.
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.account_cart = None
        customer_id = self.session.get("customer_id")
        customer = Customer.objects.filter(pk=customer_id).first() if customer_id else None
        if customer is not None:
            with transaction.atomic():
                self.account_cart, created = ShoppingCart.objects.get_or_create(customer=customer)
                if created:
                    self._import_session_cart()
            if "cart" in self.session:
                self.session.pop("cart")
                self.session.modified = True

    def _session_cart(self):
        cart = self.session.get("cart")
        if not isinstance(cart, dict) or not cart:
            cart = {}
            self.session["cart"] = cart
        return cart

    def _save_session_cart(self, cart):
        self.session["cart"] = cart
        self.session.modified = True

    def _import_session_cart(self):
        session_cart = self.session.get("cart")
        if not isinstance(session_cart, dict) or not session_cart:
            return

        quantities = {}
        for key, quantity in session_cart.items():
            try:
                saree_id = int(key)
                quantity = int(quantity)
            except (TypeError, ValueError):
                continue
            if quantity > 0:
                quantities[saree_id] = quantity

        existing_saree_ids = set(
            Saree.objects.filter(pk__in=quantities).values_list("pk", flat=True)
        )
        CartItem.objects.bulk_create(
            [
                CartItem(cart=self.account_cart, saree_id=saree_id, quantity=quantity)
                for saree_id, quantity in quantities.items()
                if saree_id in existing_saree_ids
            ]
        )

    def _account_item(self, saree_id):
        return self.account_cart.items.filter(saree_id=saree_id).first()

    def add(self, saree_id, quantity=1):
        qty = int(quantity)
        if qty <= 0:
            return
        if self.account_cart is not None:
            if not Saree.objects.filter(pk=saree_id).exists():
                return
            item, created = CartItem.objects.get_or_create(
                cart=self.account_cart,
                saree_id=saree_id,
                defaults={"quantity": qty},
            )
            if not created:
                CartItem.objects.filter(pk=item.pk).update(quantity=F("quantity") + qty)
            return
        cart = self._session_cart()
        key = str(saree_id)
        cart[key] = cart.get(key, 0) + qty
        self._save_session_cart(cart)

    def set_quantity(self, saree_id, quantity):
        qty = int(quantity)
        if self.account_cart is not None:
            item = self._account_item(saree_id)
            if item is None:
                return
            if qty <= 0:
                item.delete()
                return
            item.quantity = qty
            item.save(update_fields=("quantity",))
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
        if self.account_cart is not None:
            self.account_cart.items.filter(saree_id=saree_id).delete()
            return
        cart = self._session_cart()
        key = str(saree_id)
        if key in cart:
            del cart[key]
            self._save_session_cart(cart)

    def clear(self):
        if self.account_cart is not None:
            self.account_cart.items.all().delete()
            return
        self._save_session_cart({})

    def count(self):
        if self.account_cart is not None:
            return sum(self.account_cart.items.values_list("quantity", flat=True))
        total = 0
        for qty in self._session_cart().values():
            try:
                total += int(qty)
            except (TypeError, ValueError):
                continue
        return total

    def items(self):
        """Return list of {saree, quantity, line_total} dicts."""
        if self.account_cart is not None:
            return [
                self._item_details(item.saree, item.quantity)
                for item in self.account_cart.items.select_related("saree")
            ]
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
            result.append(self._item_details(saree, qty))
        return result

    @staticmethod
    def _item_details(saree, quantity):
        return {
            "saree": saree,
            "quantity": quantity,
            "final_amount": saree.final_amount,
            "line_total": saree.final_amount * quantity,
            "delivery_charge": saree.delivery_charge * quantity,
            "gst_percent": saree.gst_percent,
            "gst_amount": gst_amount(saree.final_amount * quantity, saree.gst_percent),
        }

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
