"""Text and price normalization.

Everything that reads the raw offer data goes through this module, so the
indexed text and the query text are folded the same way and every caller
stores and reads the same keys.
"""

from __future__ import annotations

# Diacritics that get dropped when typing Swedish on a non-Swedish keyboard.
# SQLite's trigram tokenizer does not fold these on its own, so "mjolk" would
# never match "Mjölkchoklad" unless both sides go through fold() first.
_FOLD = str.maketrans(
    {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "é": "e",
        "è": "e",
        "ü": "u",
        "á": "a",
        "à": "a",
        "ø": "o",
        "æ": "ae",
    }
)

# Price fields in the order the source uses them. There is no documented
# precedence, so this order is our own convention and it is applied in one
# place only.
PRICE_PRECEDENCE = ("membershipPrice", "appPrice", "fromPrice", "price")

# The source normalizes unit prices onto one of these three base units.
COMPARABLE_BASE_UNITS = ("kilogram", "liter", "piece")

BASE_UNIT_SYMBOL = {"kilogram": "kg", "liter": "l", "piece": "st"}


def fold(text) -> str:
    """Lowercase and strip diacritics.

    Used for both indexing and querying. Anything that goes into the search
    index must be folded with this function, and so must every user query.
    """
    if text is None:
        return ""
    return str(text).lower().translate(_FOLD)


def _first_present(mapping, keys):
    """Return (key, value) for the first key that is present and not None."""
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return key, value
    return None, None


def _as_float(value):
    """Coerce to float, returning None for junk or non-positive values."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def normalize_offer(raw):
    """Map one raw offer to the canonical shape used everywhere else.

    Accepts either a raw payload straight from a source, or an already cleaned
    product, so the command line path and the web path cannot drift apart.
    Returns None when the record has no usable identifier.
    """
    if not isinstance(raw, dict):
        return None

    public_id = raw.get("publicId") or raw.get("public_id")
    if not public_id:
        return None

    name = raw.get("name") or ""

    # Store name. Raw payloads nest it under "business"; cleaned products carry
    # it as "supermarket".
    store = None
    business = raw.get("business")
    if isinstance(business, dict):
        store = business.get("name")
    if store is None:
        store = raw.get("supermarket")

    # Price. Prefer the raw fields in our documented order, then fall back to
    # the cleaned "price_value".
    price_key, price = _first_present(raw, PRICE_PRECEDENCE)
    if price is None:
        price_key, price = "price_value", raw.get("price_value")
    price = _as_float(price)

    unit_price = _as_float(raw.get("unitPrice", raw.get("unit_price")))
    # The source emits 0 for items it cannot normalize (restaurant meals,
    # combo buckets). Sorting ascending would put all of those first, so 0 is
    # treated as "unknown" rather than "free".
    if unit_price is not None and unit_price <= 0:
        unit_price = None

    base_unit = raw.get("baseUnit", raw.get("base_unit"))
    if base_unit not in COMPARABLE_BASE_UNITS:
        base_unit = None

    return {
        "public_id": str(public_id),
        "name": name,
        "name_folded": fold(name),
        "store": store,
        "price": price,
        "price_type": raw.get("price_type") or price_key,
        "unit_price": unit_price,
        "base_unit": base_unit,
        "unit_symbol": raw.get("unitSymbol", raw.get("unit_symbol")),
        "size_from": _as_float(raw.get("unitSizeFrom", raw.get("size_from"))),
        "size_to": _as_float(raw.get("unitSizeTo", raw.get("size_to"))),
        "currency": raw.get("currencyCode", raw.get("currency")),
        "department": raw.get("departmentSlug", raw.get("department")),
        "valid_from": raw.get("validFrom", raw.get("valid_from")),
        "valid_until": raw.get("validUntil", raw.get("valid_until")),
        "image": raw.get("image"),
    }


def is_rankable(offer) -> bool:
    """Whether an offer may take part in a per-unit price ranking.

    Requires a positive unit price, a known base unit, and SEK. Mixing
    currencies or comparing across base units produces wrong answers, so both
    are excluded here rather than papered over later.
    """
    if not offer:
        return False
    if not offer.get("unit_price") or offer["unit_price"] <= 0:
        return False
    if offer.get("base_unit") not in COMPARABLE_BASE_UNITS:
        return False
    currency = offer.get("currency")
    return currency in (None, "SEK")


def unit_label(offer) -> str:
    """Human readable unit price label, e.g. 'kr/kg'."""
    symbol = BASE_UNIT_SYMBOL.get(offer.get("base_unit"), "?")
    return "kr/%s" % symbol
