"""FR-2 — normalize a raw record into the canonical shape.

The bug these tests exist to prevent: the web path and the CLI path once read
different key names, so one of them silently stored price=0 and store=NULL for
every row. normalize_offer() is the single mapping both paths go through, so
the mapping itself is what gets tested.
"""

from __future__ import annotations

import pytest

import store
from normalize import (
    COMPARABLE_BASE_UNITS,
    PRICE_PRECEDENCE,
    fold,
    is_rankable,
    normalize_offer,
    unit_label,
)


# --- FR-2: reject records with no usable identifier -------------------------

@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"name": "Mjölk"},
        {"publicId": None, "name": "Mjölk"},
        {"publicId": "", "name": "Mjölk"},
        None,
        "not a dict",
        [],
        42,
    ],
)
def test_record_without_identifier_is_rejected(raw):
    assert normalize_offer(raw) is None


def test_identifier_is_coerced_to_string():
    assert normalize_offer({"publicId": 123})["public_id"] == "123"


def test_snake_case_identifier_is_accepted():
    """Cleaned products use public_id; raw payloads use publicId."""
    assert normalize_offer({"public_id": "abc"})["public_id"] == "abc"


# --- FR-2: both shapes map to the same keys --------------------------------

def test_raw_and_cleaned_shapes_agree_on_every_shared_field():
    raw = {
        "publicId": "x1",
        "name": "Färsk kycklingfilé 450 g",
        "business": {"name": "Willys"},
        "price": 39.9,
        "unitPrice": 88.67,
        "baseUnit": "kilogram",
        "unitSymbol": "kg",
        "unitSizeFrom": 450,
        "unitSizeTo": 450,
        "currencyCode": "SEK",
        "departmentSlug": "kott-fagel",
        "validFrom": "2026-10-01T00:00:00+0000",
        "validUntil": "2026-10-11T23:59:59+0000",
    }
    # The same offer after the web cleaning step: different key names, same data.
    cleaned = {
        "publicId": "x1",
        "name": "Färsk kycklingfilé 450 g",
        "supermarket": "Willys",
        "price_value": 39.9,
        "unitPrice": 88.67,
        "baseUnit": "kilogram",
        "unitSymbol": "kg",
        "unitSizeFrom": 450,
        "unitSizeTo": 450,
        "currencyCode": "SEK",
        "departmentSlug": "kott-fagel",
        "validFrom": "2026-10-01T00:00:00+0000",
        "validUntil": "2026-10-11T23:59:59+0000",
    }

    raw_offer = normalize_offer(raw)
    cleaned_offer = normalize_offer(cleaned)

    # Same keys, same values, apart from price_type (see the test below).
    assert {k: v for k, v in raw_offer.items() if k != "price_type"} == {
        k: v for k, v in cleaned_offer.items() if k != "price_type"
    }
    assert raw_offer["price_type"] == "price"
    assert cleaned_offer["price_type"] == "price_value"


def test_raw_and_cleaned_shapes_persist_identical_values():
    """FR-2's actual criterion: no two paths may store different values.

    `price_type` records which source field the price came from, and the
    cleaning step collapses the four price fields into one, so that label is
    allowed to differ — it is not a stored column.
    """
    raw = {"publicId": "x1", "name": "Ost", "price": 39.9, "business": {"name": "Willys"}}
    cleaned = {"publicId": "x1", "name": "Ost", "price_value": 39.9, "supermarket": "Willys"}

    raw_offer = normalize_offer(raw)
    cleaned_offer = normalize_offer(cleaned)

    assert set(raw_offer) == set(cleaned_offer)
    assert {k: raw_offer.get(k) for k in store.OFFER_COLUMNS} == {
        k: cleaned_offer.get(k) for k in store.OFFER_COLUMNS
    }


def test_canonical_shape_has_the_documented_keys():
    offer = normalize_offer({"publicId": "x1", "name": "Mjölk"})
    assert set(offer) >= {
        "public_id", "name", "name_folded", "store", "price", "price_type",
        "unit_price", "base_unit", "unit_symbol", "size_from", "size_to",
        "currency", "department", "valid_from", "valid_until", "image",
    }
    # name_folded is derived here so that no caller has to remember to fold.
    assert offer["name_folded"] == fold("Mjölk") == "mjolk"


# --- FR-2: price precedence ------------------------------------------------

def test_price_precedence_follows_the_documented_order():
    assert PRICE_PRECEDENCE == ("membershipPrice", "appPrice", "fromPrice", "price")

    raw = {
        "publicId": "x1",
        "membershipPrice": 10.0,
        "appPrice": 20.0,
        "fromPrice": 30.0,
        "price": 40.0,
    }
    offer = normalize_offer(raw)
    assert offer["price"] == 10.0
    assert offer["price_type"] == "membershipPrice"


@pytest.mark.parametrize(
    "present,expected_key,expected_value",
    [
        ({"appPrice": 20.0, "fromPrice": 30.0, "price": 40.0}, "appPrice", 20.0),
        ({"fromPrice": 30.0, "price": 40.0}, "fromPrice", 30.0),
        ({"price": 40.0}, "price", 40.0),
    ],
)
def test_price_falls_through_the_precedence(present, expected_key, expected_value):
    offer = normalize_offer({"publicId": "x1", **present})
    assert (offer["price"], offer["price_type"]) == (expected_value, expected_key)


def test_cleaned_price_value_is_used_when_no_raw_field_exists():
    offer = normalize_offer({"publicId": "x1", "price_value": 15.5})
    assert offer["price"] == 15.5


def test_unparseable_price_becomes_none_not_zero():
    """NFR-3: a value we cannot derive is NULL, never a fabricated number."""
    offer = normalize_offer({"publicId": "x1", "price": "inte ett tal"})
    assert offer["price"] is None


# --- FR-2: store name resolved defensively ---------------------------------

def test_store_comes_from_the_nested_business_object():
    offer = normalize_offer({"publicId": "x1", "business": {"name": "ICA Maxi"}})
    assert offer["store"] == "ICA Maxi"


def test_store_falls_back_to_the_cleaned_supermarket_key():
    offer = normalize_offer({"publicId": "x1", "supermarket": "Coop"})
    assert offer["store"] == "Coop"


def test_missing_store_is_none_not_a_placeholder():
    """The web path used to invent "未知超市"; the canonical shape must not."""
    assert normalize_offer({"publicId": "x1"})["store"] is None
    assert normalize_offer({"publicId": "x1", "business": None})["store"] is None


# --- NFR-3: zero unit price means unknown ----------------------------------

@pytest.mark.parametrize("value", [0, 0.0, -1, -3.5])
def test_non_positive_unit_price_is_treated_as_unknown(value):
    offer = normalize_offer({"publicId": "x1", "unitPrice": value})
    assert offer["unit_price"] is None


def test_unknown_base_unit_is_nulled_out():
    offer = normalize_offer({"publicId": "x1", "baseUnit": "furlong"})
    assert offer["base_unit"] is None


@pytest.mark.parametrize("unit", COMPARABLE_BASE_UNITS)
def test_known_base_units_survive(unit):
    assert normalize_offer({"publicId": "x1", "baseUnit": unit})["base_unit"] == unit


# --- is_rankable -----------------------------------------------------------

def test_rankable_requires_positive_price_unit_and_sek():
    good = normalize_offer(
        {"publicId": "x1", "unitPrice": 12.0, "baseUnit": "liter", "currencyCode": "SEK"}
    )
    assert is_rankable(good)

    no_unit = normalize_offer({"publicId": "x1", "baseUnit": "liter"})
    assert not is_rankable(no_unit)

    zero_unit = normalize_offer({"publicId": "x1", "unitPrice": 0, "baseUnit": "liter"})
    assert not is_rankable(zero_unit)


@pytest.mark.parametrize("currency", ["EUR", "USD", "DKK"])
def test_rankable_excludes_foreign_currency(currency):
    offer = normalize_offer(
        {"publicId": "x1", "unitPrice": 12.0, "baseUnit": "liter", "currencyCode": currency}
    )
    assert not is_rankable(offer)


def test_rankable_accepts_missing_currency():
    """Some records carry no currency; assume SEK rather than drop the offer."""
    offer = normalize_offer({"publicId": "x1", "unitPrice": 12.0, "baseUnit": "liter"})
    assert is_rankable(offer)


def test_rankable_rejects_none():
    assert not is_rankable(None)


# --- unit_label ------------------------------------------------------------

@pytest.mark.parametrize(
    "unit,expected",
    [("kilogram", "kr/kg"), ("liter", "kr/l"), ("piece", "kr/st")],
)
def test_unit_label(unit, expected):
    assert unit_label({"base_unit": unit}) == expected


def test_unit_label_for_unknown_unit_is_not_a_lie():
    assert unit_label({"base_unit": None}) == "kr/?"


# --- fold ------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Mjölk", "mjolk"),
        ("PURJOLÖK", "purjolok"),
        ("Gräddfil", "graddfil"),
        ("ÅÄÖ", "aao"),
        ("Æbler", "aebler"),
        ("Øl", "ol"),
        ("Crème fraiche", "creme fraiche"),
        (None, ""),
        ("", ""),
    ],
)
def test_fold_strips_diacritics_and_case(raw, expected):
    assert fold(raw) == expected


def test_fold_covers_the_letters_a_swedish_keyboard_cannot_type():
    """The table is deliberately limited to what a non-Swedish keyboard drops.

    A circumflex vowel (î, ô) is not one of them — French loanwords keep their
    accent, which is correct: nobody types "fraiche" for "fraîche" by accident
    on a Swedish layout. This documents the boundary rather than pretending it
    does not exist.
    """
    assert fold("fraîche") == "fraîche"
    assert fold("rôti") == "rôti"


def test_fold_does_not_mangle_ascii():
    assert fold("kycklingbrostfile 450g") == "kycklingbrostfile 450g"
