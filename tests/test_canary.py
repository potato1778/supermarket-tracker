"""The canary's own logic, tested offline.

A canary that cries wolf gets ignored, so the pure helpers are pinned down here
and the live checks are kept as thin as possible. Nothing in this file touches
the network.
"""

from __future__ import annotations

import pytest

from tools import canary


# --- _num / _close ---------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [(1, 1.0), ("2.5", 2.5), (0, 0.0), (None, None), ("", None), ("x", None)],
)
def test_num(value, expected):
    assert canary._num(value) == expected


def test_close_is_relative():
    assert canary._close(100.0, 101.0)          # 1% off
    assert not canary._close(100.0, 120.0)      # 20% off
    assert canary._close(0, 0)
    assert not canary._close(0, 1)
    assert not canary._close(None, 1)


# --- size_in_base_unit -----------------------------------------------------

@pytest.mark.parametrize(
    "record,expected",
    [
        ({"baseUnit": "kilogram", "unitSymbol": "g", "unitSizeFrom": 450}, 0.45),
        ({"baseUnit": "kilogram", "unitSymbol": "kg", "unitSizeFrom": 1}, 1.0),
        ({"baseUnit": "liter", "unitSymbol": "ml", "unitSizeFrom": 500}, 0.5),
        ({"baseUnit": "liter", "unitSymbol": "cl", "unitSizeFrom": 33}, 0.33),
        ({"baseUnit": "liter", "unitSymbol": "dl", "unitSizeFrom": 5}, 0.5),
        ({"baseUnit": "liter", "unitSymbol": "l", "unitSizeFrom": 1.5}, 1.5),
        ({"baseUnit": "piece", "unitSymbol": "pcs", "unitSizeFrom": 6}, 6.0),
        ({"baseUnit": "piece", "unitSymbol": "st", "unitSizeFrom": 12}, 12.0),
        ({"baseUnit": "piece", "unitSymbol": "st", "unitSizeFrom": 24, "unitSizeTo": 24}, 24.0),
    ],
)
def test_size_in_base_unit_converts_known_symbols(record, expected):
    assert canary.size_in_base_unit(record) == pytest.approx(expected)


@pytest.mark.parametrize(
    "record",
    [
        {"baseUnit": "kilogram", "unitSymbol": "g"},                                  # no size
        {"baseUnit": "furlong", "unitSymbol": "g", "unitSizeFrom": 450},              # unknown unit
        {"baseUnit": "kilogram", "unitSymbol": "furlong", "unitSizeFrom": 450},       # unknown symbol
        {"baseUnit": None, "unitSymbol": "g", "unitSizeFrom": 450},
        {"baseUnit": "kilogram", "unitSymbol": "g", "unitSizeFrom": 0},
        {"baseUnit": "kilogram", "unitSymbol": "g", "unitSizeFrom": -1},
        {"baseUnit": "kilogram", "unitSymbol": "g", "unitSizeFrom": "junk"},
    ],
)
def test_size_in_base_unit_refuses_what_it_cannot_derive(record):
    assert canary.size_in_base_unit(record) is None


def test_size_in_base_unit_skips_a_range():
    """350-500 g: the source may use either end, so reconciling is unsound."""
    record = {"baseUnit": "kilogram", "unitSymbol": "g", "unitSizeFrom": 350, "unitSizeTo": 500}
    assert canary.size_in_base_unit(record) is None


# --- unit_price_reconciles -------------------------------------------------

def test_single_item_reconciles():
    """The documented worked example: 450 g at 39.9 kr -> 88.67 kr/kg."""
    record = {
        "unitPrice": 88.67, "baseUnit": "kilogram", "unitSymbol": "g",
        "unitSizeFrom": 450, "unitSizeTo": 450, "price": 39.9,
    }
    assert canary.unit_price_reconciles(record) is True


def test_a_membership_price_is_accepted_as_the_source_of_the_unit_price():
    record = {
        "unitPrice": 44.33, "baseUnit": "kilogram", "unitSymbol": "g",
        "unitSizeFrom": 450, "unitSizeTo": 450, "price": 39.9, "membershipPrice": 19.95,
    }
    assert canary.unit_price_reconciles(record) is True


def test_a_multipack_reconciles_through_the_pack_count():
    """unitSizeFrom is one pack; a 6-pack divides the price by six times that."""
    record = {
        "unitPrice": 88.67 / 6, "baseUnit": "kilogram", "unitSymbol": "g",
        "unitSizeFrom": 450, "unitSizeTo": 450, "price": 39.9,
    }
    assert canary.unit_price_reconciles(record) is True


def test_a_redefined_unit_price_does_not_reconcile():
    """unitPrice that merely echoes the total is the drift this exists to catch."""
    record = {
        "unitPrice": 39.9, "baseUnit": "kilogram", "unitSymbol": "g",
        "unitSizeFrom": 450, "unitSizeTo": 450, "price": 39.9,
    }
    assert canary.unit_price_reconciles(record) is False


def test_a_price_in_ore_does_not_reconcile():
    record = {
        "unitPrice": 8867.0, "baseUnit": "kilogram", "unitSymbol": "g",
        "unitSizeFrom": 450, "unitSizeTo": 450, "price": 39.9,
    }
    assert canary.unit_price_reconciles(record) is False


@pytest.mark.parametrize(
    "record",
    [
        {"baseUnit": "kilogram", "unitSymbol": "kg", "unitSizeFrom": 450},          # no unitPrice
        {"unitPrice": 0, "baseUnit": "kilogram", "unitSymbol": "kg", "unitSizeFrom": 450},
        {"unitPrice": 88.67, "baseUnit": "kilogram", "unitSymbol": "kg"},           # no size
        {"unitPrice": 88.67, "baseUnit": "piece", "unitSymbol": "rulle", "unitSizeFrom": 24},
    ],
)
def test_uncheckable_records_return_none(record):
    assert canary.unit_price_reconciles(record) is None


# --- store directory helper ------------------------------------------------

def test_pick_business_matches_case_insensitively():
    directory = {"Willys Hemma": "a", "ICA Maxi": "b"}
    assert canary._pick_business(directory, "willys") == "a"
    assert canary._pick_business(directory, "ica") == "b"
    assert canary._pick_business(directory, "coop") is None


# --- Result ----------------------------------------------------------------

def test_result_serialises():
    result = canary.Result("x", False, "broke", metrics={"n": 1})
    assert result.as_dict() == {
        "name": "x", "ok": False, "severity": "fail",
        "detail": "broke", "metrics": {"n": 1},
    }


def test_every_check_has_a_unique_name():
    names = [c.__name__ for c in canary.CHECKS]
    assert len(names) == len(set(names))
    assert all(n.startswith("check_") for n in names)
