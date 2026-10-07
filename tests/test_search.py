"""FR-5 — free-text search tolerant of missing Swedish diacritics.

Search goes through FTS5 with the trigram tokenizer, which does not fold
diacritics on its own. Both the index and the query are folded first, so the
tests write the umlaut-free form the way a non-Swedish keyboard would.
"""

from __future__ import annotations

import sqlite3

import pytest

import store


def _seed(con, offer_factory, *names):
    store.upsert_offers(
        con,
        [
            offer_factory(public_id="p%d" % i, name=name, name_folded=None)
            for i, name in enumerate(names)
        ],
        observed_on="2026-10-07",
    )


def test_fts5_trigram_tokenizer_is_available(con):
    """The whole search design rests on this; fail loudly if the build lacks it."""
    try:
        con.execute("CREATE VIRTUAL TABLE probe USING fts5(x, tokenize='trigram')")
    except sqlite3.OperationalError as exc:  # pragma: no cover - environment guard
        pytest.fail("SQLite has no FTS5 trigram tokenizer: %s" % exc)


@pytest.mark.parametrize(
    "query,expected",
    [
        ("mjolk", {"Mjölk 3%", "Mjölkchoklad"}),
        ("mjölk", {"Mjölk 3%", "Mjölkchoklad"}),
        ("MJOLK", {"Mjölk 3%", "Mjölkchoklad"}),
        ("choklad", {"Mjölkchoklad"}),
        ("purjolok", {"Purjolök"}),
        ("purjolök", {"Purjolök"}),
        ("graddfil", {"Gräddfil"}),
        ("fars", {"Köttfärs"}),
    ],
)
def test_diacritics_are_optional(con, offer_factory, query, expected):
    _seed(con, offer_factory, "Mjölk 3%", "Mjölkchoklad", "Purjolök", "Gräddfil", "Köttfärs")
    assert {row["name"] for row in store.search(con, query)} == expected


def test_case_is_irrelevant(con, offer_factory):
    _seed(con, offer_factory, "KYCKLINGFILÉ")
    assert len(store.search(con, "kycklingfile")) == 1
    assert len(store.search(con, "Kycklingfilé")) == 1


def test_short_query_falls_back_to_substring_match(con, offer_factory):
    """Trigram needs three characters; a two-letter query must still work."""
    _seed(con, offer_factory, "Ägg 12-pack", "Ost")
    assert [row["name"] for row in store.search(con, "gg")] == ["Ägg 12-pack"]


@pytest.mark.parametrize("query", ['mjölk*', 'a-b', '"', 'mjölk"', "NEAR(", "((("])
def test_index_syntax_characters_do_not_raise(con, offer_factory, query):
    _seed(con, offer_factory, "Mjölk 3%")
    store.search(con, query)  # must not raise


@pytest.mark.parametrize("query", ["", "   ", None])
def test_blank_query_returns_nothing(con, offer_factory, query):
    _seed(con, offer_factory, "Mjölk 3%")
    assert store.search(con, query) == []


def test_no_match_returns_empty_not_an_error(con, offer_factory):
    _seed(con, offer_factory, "Mjölk 3%")
    assert store.search(con, "kaviar") == []


def test_results_are_ordered_by_unit_price_with_unknown_last(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="a", name="Kaffe A", name_folded=None, unit_price=99.0),
        offer_factory(public_id="b", name="Kaffe B", name_folded=None, unit_price=49.0),
        offer_factory(public_id="c", name="Kaffe C", name_folded=None, unit_price=None),
    ])
    assert [r["public_id"] for r in store.search(con, "kaffe")] == ["b", "a", "c"]


def test_limit_is_respected(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="p%d" % i, name="Kaffe %d" % i, name_folded=None, unit_price=float(i))
        for i in range(10)
    ])
    assert len(store.search(con, "kaffe", limit=3)) == 3
