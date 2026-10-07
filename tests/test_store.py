"""FR-3 storage, FR-4 price history, NFR-4 idempotency."""

from __future__ import annotations

import datetime as dt

import pytest

import store


def _count(con, table):
    return con.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]


# --- FR-3: upsert updates in place, never duplicates ------------------------

def test_first_ingest_inserts(con, offer_factory):
    counts = store.upsert_offers(con, [offer_factory()])
    assert counts == {"new": 1, "updated": 0, "unchanged": 0}
    assert _count(con, "offer") == 1


def test_re_ingesting_the_same_offer_does_not_duplicate(con, offer_factory):
    offer = offer_factory()
    store.upsert_offers(con, [offer])
    counts = store.upsert_offers(con, [offer])

    assert counts == {"new": 0, "updated": 0, "unchanged": 1}
    assert _count(con, "offer") == 1


def test_a_price_move_counts_as_updated(con, offer_factory):
    store.upsert_offers(con, [offer_factory(price=12.0, unit_price=12.0)])
    counts = store.upsert_offers(con, [offer_factory(price=10.0, unit_price=10.0)])

    assert counts == {"new": 0, "updated": 1, "unchanged": 0}
    assert _count(con, "offer") == 1


def test_a_unit_price_move_alone_also_counts_as_updated(con, offer_factory):
    store.upsert_offers(con, [offer_factory(price=12.0, unit_price=12.0)])
    counts = store.upsert_offers(con, [offer_factory(price=12.0, unit_price=9.0)])
    assert counts["updated"] == 1


def test_counts_add_up_to_the_batch_size(con, offer_factory):
    batch = [offer_factory(public_id="a"), offer_factory(public_id="b")]
    store.upsert_offers(con, batch)
    counts = store.upsert_offers(con, batch + [offer_factory(public_id="c")])
    assert sum(counts.values()) == 3


def test_first_seen_is_never_overwritten(con, offer_factory):
    """Regression: INSERT OR REPLACE reset first_seen on every run.

    A sentinel value is written straight into the row, so the assertion does
    not depend on the two runs landing in different seconds.
    """
    offer = offer_factory()
    store.upsert_offers(con, [offer])
    con.execute("UPDATE offer SET first_seen = '1999-01-01T00:00:00' WHERE public_id = 'p1'")
    con.commit()

    store.upsert_offers(con, [offer_factory(price=99.0, unit_price=99.0)])

    row = con.execute("SELECT first_seen, last_seen FROM offer").fetchone()
    assert row["first_seen"] == "1999-01-01T00:00:00"


def test_last_seen_moves_forward(con, offer_factory):
    offer = offer_factory()
    store.upsert_offers(con, [offer])
    con.execute("UPDATE offer SET last_seen = '1999-01-01T00:00:00'")
    con.commit()

    store.upsert_offers(con, [offer])
    assert con.execute("SELECT last_seen FROM offer").fetchone()["last_seen"] != "1999-01-01T00:00:00"


def test_name_folded_is_derived_when_the_caller_omits_it(con, offer_factory):
    offer = offer_factory(name="Mjölkchoklad", name_folded=None)
    store.upsert_offers(con, [offer])
    assert con.execute("SELECT name_folded FROM offer").fetchone()["name_folded"] == "mjolkchoklad"


# --- FR-3: expiry purge ----------------------------------------------------

def test_purge_deletes_expired_offers(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="old", valid_until="2026-01-01T00:00:00+00:00"),
        offer_factory(public_id="current", valid_until="2099-01-01T00:00:00+00:00"),
    ])
    removed = store.purge_expired(con, now="2026-06-01T00:00:00+00:00")

    assert removed == 1
    remaining = [r["public_id"] for r in con.execute("SELECT public_id FROM offer")]
    assert remaining == ["current"]


def test_purge_also_clears_the_search_index(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="old", name="Mjölk", valid_until="2026-01-01T00:00:00+00:00"),
    ])
    store.purge_expired(con, now="2026-06-01T00:00:00+00:00")

    assert _count(con, "offer_fts") == 0
    assert store.search(con, "mjolk") == []


def test_offer_without_valid_until_is_kept(con, offer_factory):
    """We cannot tell whether it expired, and dropping it would hide data."""
    store.upsert_offers(con, [offer_factory(public_id="nodate", valid_until=None)])
    assert store.purge_expired(con, now="2099-01-01T00:00:00+00:00") == 0
    assert _count(con, "offer") == 1


def test_offer_with_unparseable_valid_until_is_kept(con, offer_factory):
    store.upsert_offers(con, [offer_factory(public_id="junk", valid_until="snart")])
    assert store.purge_expired(con, now="2099-01-01T00:00:00+00:00") == 0
    assert _count(con, "offer") == 1


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-11T23:59:59+0000",   # source style, no colon in the offset
        "2026-10-11T23:59:59Z",       # Zulu
        "2026-10-11T23:59:59+00:00",  # Python style
    ],
)
def test_valid_until_offsets_are_all_understood(con, offer_factory, value):
    """A plain string compare would mis-order "+0000" against "+00:00"."""
    store.upsert_offers(con, [offer_factory(public_id="x", valid_until=value)])
    assert store.purge_expired(con, now="2099-01-01T00:00:00+00:00") == 1


def test_naive_valid_until_is_read_as_utc(con, offer_factory):
    store.upsert_offers(con, [offer_factory(public_id="x", valid_until="2026-01-01T00:00:00")])
    assert store.purge_expired(con, now="2026-06-01T00:00:00+00:00") == 1


# --- FR-4: price history ---------------------------------------------------

def test_two_ingests_in_one_day_leave_one_observation(con, offer_factory):
    offer = offer_factory()
    store.upsert_offers(con, [offer], observed_on="2026-10-07")
    store.upsert_offers(con, [offer], observed_on="2026-10-07")
    assert _count(con, "price_observation") == 1


def test_observations_accumulate_across_days(con, offer_factory):
    store.upsert_offers(con, [offer_factory(price=12.0)], observed_on="2026-10-06")
    store.upsert_offers(con, [offer_factory(price=10.0)], observed_on="2026-10-07")

    history = store.price_history(con, "p1")
    assert [h["observed_on"] for h in history] == ["2026-10-06", "2026-10-07"]
    assert [h["price"] for h in history] == [12.0, 10.0]


def test_purge_never_deletes_price_history(con, offer_factory):
    store.upsert_offers(
        con, [offer_factory(valid_until="2026-01-01T00:00:00+00:00")], observed_on="2026-01-01"
    )
    store.purge_expired(con, now="2026-06-01T00:00:00+00:00")

    assert _count(con, "offer") == 0
    assert _count(con, "price_observation") == 1


# --- NFR-4: idempotency ----------------------------------------------------

def test_a_second_full_run_changes_nothing(con, offer_factory):
    batch = [
        offer_factory(public_id="a"),
        offer_factory(public_id="b", base_unit="kilogram", unit_price=88.67),
        offer_factory(public_id="c", base_unit="piece", unit_price=None),
    ]
    store.upsert_offers(con, batch, observed_on="2026-10-07")
    first = con.execute("SELECT * FROM offer ORDER BY public_id").fetchall()

    counts = store.upsert_offers(con, batch, observed_on="2026-10-07")
    second = con.execute("SELECT * FROM offer ORDER BY public_id").fetchall()

    assert counts == {"new": 0, "updated": 0, "unchanged": 3}
    assert [dict(r) for r in first] == [dict(r) for r in second]
    assert _count(con, "price_observation") == 3


# --- read-side helpers -----------------------------------------------------

def test_store_names_counts_per_store(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="a", store="Willys"),
        offer_factory(public_id="b", store="Willys"),
        offer_factory(public_id="c", store="Coop"),
    ])
    assert store.store_names(con) == [
        {"store": "Willys", "offers": 2},
        {"store": "Coop", "offers": 1},
    ]


def test_by_store_groups_by_department_and_puts_unknown_prices_last(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="a", store="Willys", department="mejeri", unit_price=20.0),
        offer_factory(public_id="b", store="Willys", department="mejeri", unit_price=10.0),
        offer_factory(public_id="c", store="Willys", department="mejeri", unit_price=None),
        offer_factory(public_id="d", store="Willys", department="brod", unit_price=30.0),
        offer_factory(public_id="e", store="Coop"),
    ])
    rows = store.by_store(con, "Willys")
    assert [r["public_id"] for r in rows] == ["d", "b", "a", "c"]


def test_stats_reports_offers_units_stores_and_observations(con, offer_factory):
    store.upsert_offers(con, [
        offer_factory(public_id="a", store="Willys"),
        offer_factory(public_id="b", store="Coop", unit_price=None, base_unit=None),
    ], observed_on="2026-10-07")

    assert store.stats(con) == {
        "offers": 2,
        "with_unit_price": 1,
        "stores": 2,
        "price_observations": 2,
    }


def test_default_observed_on_is_today(con, offer_factory):
    store.upsert_offers(con, [offer_factory()])
    assert con.execute("SELECT observed_on FROM price_observation").fetchone()[0] == (
        dt.date.today().isoformat()
    )
