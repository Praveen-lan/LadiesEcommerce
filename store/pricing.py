"""Single source of truth for every money and discount calculation.

The product page, saree card, cart, checkout, payment, invoice and order summary
all read their amounts from here, so they can never disagree with each other.

The rules are deliberately narrow:

* the original amount is never modified;
* a discount is applied exactly once, and always to the original amount;
* both the discount and the final amount are rounded to 2 decimal places;
* the discount is clamped to 0-100%, so a final amount can never go negative.

For example a saree with an original amount of 1000 and a 20% discount produces a
discount of 200.00 and a final amount of 800.00, and 1000.00 - 200.00 == 800.00
holds exactly.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TWO_PLACES = Decimal("0.01")
ZERO_AMOUNT = Decimal("0.00")
ZERO_PERCENT = Decimal("0")
MAX_DISCOUNT_PERCENT = Decimal("100")
HUNDRED = Decimal("100")

# Fallback delivery rules, used until Site Settings provides the real ones.
GST_RATE = Decimal("0.05")
SHIPPING_FEE = Decimal("79.00")
SHIPPING_FEE_ABOVE = Decimal("999.00")
FREE_SHIPPING_ABOVE = Decimal("1499.00")


def to_amount(value):
    """Return ``value`` as a non-negative amount rounded to 2 decimal places.

    Blank or unusable input becomes ``0.00`` and a negative amount is clamped to
    zero, so no display or total can ever show a negative price.
    """
    if value is None or value == "":
        return ZERO_AMOUNT
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO_AMOUNT
    if not amount.is_finite():
        return ZERO_AMOUNT
    if amount < ZERO_AMOUNT:
        return ZERO_AMOUNT
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def clamp_discount_percent(value):
    """Return the discount percentage clamped to the 0-100 range.

    ``None`` is returned for blank input, which means "no discount was set" and
    lets the caller fall back to the original and final amounts it already has.
    """
    if value is None or value == "":
        return None
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not percent.is_finite():
        return None
    if percent < ZERO_PERCENT:
        return ZERO_PERCENT
    if percent > MAX_DISCOUNT_PERCENT:
        return MAX_DISCOUNT_PERCENT
    return percent


def is_valid_discount_percent(value):
    """Return ``True`` when ``value`` is a discount percentage inside 0-100."""
    if value is None or value == "":
        return True
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return percent.is_finite() and ZERO_PERCENT <= percent <= MAX_DISCOUNT_PERCENT


def discount_amount(original_amount, discount_percent):
    """Discount Amount = Original Amount x Discount % / 100, to 2 places."""
    original = to_amount(original_amount)
    percent = clamp_discount_percent(discount_percent)
    if percent is None:
        return ZERO_AMOUNT
    amount = (original * percent / HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    # Never discount more than the original, which keeps the final amount whole.
    return min(amount, original)


def final_amount(original_amount, discount_percent):
    """Final Amount = Original Amount - Discount Amount, to 2 places."""
    original = to_amount(original_amount)
    discount = discount_amount(original, discount_percent)
    return (original - discount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def price_breakdown(original_amount, current_amount, discount_percent=None):
    """Return the original, percent, discount and final amounts for one product.

    ``original_amount`` is the price before any discount and is never modified by
    this function. ``current_amount`` is the price the shop has been charging.

    When ``discount_percent`` is given it is applied once to the original amount
    and the result becomes the final amount. When it is blank the stored price is
    already the final amount, so the discount is simply the gap between the two.

    A mistyped original that is lower than the current price is ignored in favour
    of the current price, so a saree can never display a final amount above its
    own original.
    """
    current = to_amount(current_amount)
    original = to_amount(original_amount)
    percent = clamp_discount_percent(discount_percent)
    if original < current:
        original = current

    if percent is None:
        discount = to_amount(original - current)
    else:
        discount = discount_amount(original, percent)

    if original > ZERO_AMOUNT:
        shown_percent = (discount / original * HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    else:
        shown_percent = ZERO_PERCENT

    return {
        "original": original,
        "percent": shown_percent,
        "discount": discount,
        "final": to_amount(original - discount),
    }