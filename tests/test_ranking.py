"""FR-6 cross-store ranking, FR-7 refuse to compare incomparable units."""

from __future__ import annotations

import pytest

import categories
import store


def _cat(**overrides):
    base = {
        "labels": {"sv": "Test", "en": "Test", "zh": "测试"},
        "match": ["ost"],
        "exclude": [],
        "allowed_base_units": ["kilogram"],
        "canonical_unit": "kg",
    }
    base.update(overrides)
    return base


# --- FR-6: ordering --------------------------------------------------------

def test_results_are_sorted_by_unit_price_ascending(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="a", name="Hushållsost", unit_price=99.0),
        offer_factory(public_id="b", name="Grevéost", unit_price=49.0),
        offer_factory(public_id="c", name="Prästost", unit_price=79.0),
    ])
    assert [r["public_id"] for r in store.cheapest(con, _cat())] == ["b", "c", "a"]


def test_limit_is_respected(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="p%d" % i, name="Ost %d" % i, unit_price=float(i + 1))
        for i in range(10)
    ])
    assert len(store.cheapest(con, _cat(), limit=4)) == 4


def test_empty_category_returns_empty_list(con):
    assert store.cheapest(con, _cat()) == []


def test_a_row_carries_price_unit_price_store_and_size(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(
            public_id="a", name="Hushållsost 1 kg", store="Coop",
            price=89.0, unit_price=89.0, size_from=1.0, size_to=1.0, unit_symbol="kg",
        )
    ])
    row = store.cheapest(con, _cat())[0]
    assert row["price"] == 89.0
    assert row["unit_price"] == 89.0
    assert row["store"] == "Coop"
    assert (row["size_from"], row["size_to"]) == (1.0, 1.0)


# --- FR-6 / NFR-3: unknown or zero unit prices never appear -----------------

@pytest.mark.parametrize("unit_price", [None, 0, 0.0, -5.0])
def test_offers_without_a_usable_unit_price_are_excluded(con, offer_factory, unit_price):
    store.upsert_offers(con, [offer_factory(name="Hushållsost", unit_price=unit_price)])
    assert store.cheapest(con, _cat()) == []


def test_zero_unit_price_is_not_treated_as_free(con, offer_factory):
    """A restaurant meal at 0 kr/portion must not top the ranking."""
    store.upsert_offers(con, [
        offer_factory(public_id="free", name="Osttallrik", unit_price=0),
        offer_factory(public_id="real", name="Hushållsost", unit_price=89.0),
    ])
    assert [r["public_id"] for r in store.cheapest(con, _cat())] == ["real"]


# --- FR-6: currencies are never mixed --------------------------------------

@pytest.mark.parametrize("currency", ["EUR", "USD", "DKK"])
def test_foreign_currency_is_excluded(con, offer_factory, currency):
    store.upsert_offers(con, [
        offer_factory(public_id="foreign", name="Hushållsost", unit_price=1.0, currency=currency),
        offer_factory(public_id="sek", name="Hushållsost", unit_price=89.0, currency="SEK"),
    ])
    assert [r["public_id"] for r in store.cheapest(con, _cat())] == ["sek"]


# --- FR-7: incomparable units are excluded, never converted ----------------

def test_a_category_only_admits_its_declared_base_units(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="kg", name="Hushållsost", base_unit="kilogram", unit_price=89.0),
        offer_factory(public_id="l", name="Ostolja", base_unit="liter", unit_price=1.0),
        offer_factory(public_id="st", name="Ostbricka", base_unit="piece", unit_price=0.5),
    ])
    # Only the kilogram offer takes part, even though the litre offer has the
    # lowest number. Converting would be a fabricated comparison.
    assert [r["public_id"] for r in store.cheapest(con, _cat())] == ["kg"]


def test_kilogram_and_litre_are_never_ranked_together(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="kg", name="Smör", base_unit="kilogram", unit_price=120.0),
        offer_factory(public_id="l", name="Matolja", base_unit="liter", unit_price=30.0),
    ])
    weights = store.cheapest(con, categories.get("smor"))
    assert {r["public_id"] for r in weights} == {"kg"}


def test_laundry_detergent_is_split_by_unit(con, offer_factory):
    """Liquid, powder and pods cannot share one ranking."""
    store.upsert_offers(con, [
        offer_factory(public_id="liq", name="Flytande tvättmedel 1 l",
                      base_unit="liter", unit_price=40.0),
        offer_factory(public_id="pow", name="Tvättmedel pulver 1 kg",
                      base_unit="kilogram", unit_price=35.0),
    ])
    liquid = {r["public_id"] for r in store.cheapest(con, categories.get("tvattmedel_flytande"))}
    powder = {r["public_id"] for r in store.cheapest(con, categories.get("tvattmedel_pulver"))}
    assert liquid == {"liq"}
    assert powder == {"pow"}


# --- FR-7 / the ost regression ---------------------------------------------

def test_ost_does_not_match_kycklingbrostfile(con, offer_factory):
    """Regression: raw substring matching put chicken at the top of the cheese
    ranking, because "kycklingbröstfilé" contains the letters o-s-t."""
    store.upsert_offers(con, [
        offer_factory(public_id="chicken", name="Kycklingbröstfilé 450 g",
                      base_unit="kilogram", unit_price=24.98),
        offer_factory(public_id="cheese", name="Hushållsost 1 kg",
                      base_unit="kilogram", unit_price=89.0),
    ])
    assert [r["public_id"] for r in store.cheapest(con, categories.get("ost"))] == ["cheese"]


def test_compounds_that_end_in_the_term_still_match(con, offer_factory):
    """Swedish puts the head last, so "hushållsost" must count as cheese."""
    store.upsert_offers(con, [
        offer_factory(public_id="a", name="Hushållsost", base_unit="kilogram", unit_price=89.0),
        offer_factory(public_id="b", name="Herrgårdsost", base_unit="kilogram", unit_price=99.0),
    ])
    assert len(store.cheapest(con, categories.get("ost"))) == 2


def test_exclude_terms_suppress_known_noise(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="cake", name="Ostkaka 500 g", base_unit="kilogram", unit_price=50.0),
        offer_factory(public_id="cheese", name="Hushållsost", base_unit="kilogram", unit_price=89.0),
    ])
    assert [r["public_id"] for r in store.cheapest(con, categories.get("ost"))] == ["cheese"]


def test_pet_food_is_excluded_from_meat_categories(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="cat", name="Kattmat kyckling 400 g",
                      base_unit="kilogram", unit_price=40.68),
        offer_factory(public_id="meat", name="Färsk kycklingfilé",
                      base_unit="kilogram", unit_price=88.67),
    ])
    assert [r["public_id"] for r in store.cheapest(con, categories.get("kyckling"))] == ["meat"]


# --- word-boundary helper --------------------------------------------------

@pytest.mark.parametrize(
    "name_folded,term,expected",
    [
        ("kycklingbrostfile", "ost", False),
        ("hushallsost", "ost", True),
        ("ostkaka", "ost", True),
        ("graddfil", "graddfil", True),
        ("mjolk", "mjolk", True),
        ("mjolkchoklad", "choklad", True),
        ("", "ost", False),
    ],
)
def test_word_boundary_matching(name_folded, term, expected):
    assert store._matches_terms(name_folded, [term]) is expected
