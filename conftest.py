"""Shared pytest fixtures.

Lives at the repository root on purpose: pytest inserts the directory that
holds a conftest.py onto sys.path, which is what lets the tests import the
top-level modules (`store`, `normalize`, `categories`, `sources.tjek`) without
an installable package.

The database fixture is in-memory. Tests must never touch the real `offers.db`
— the repository is code-only (NFR-1) and a test run must not be able to write
into the working copy.
"""

from __future__ import annotations

import pytest

import store


@pytest.fixture
def con():
    """A fresh, empty database with the real schema, in memory."""
    connection = store.connect(":memory:")
    store.init_db(connection)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def offer_factory():
    """Build a canonical offer dict, overriding any field.

    The defaults describe a valid, rankable, currently-valid offer so that a
    test only has to state the one field it cares about.
    """

    def _make(**overrides):
        offer = {
            "public_id": "p1",
            "source": "tjek",
            "name": "Kaffe 1 kg",
            # None so that upsert_offers() derives it from the name. A hard
            # coded value here would survive a name override and silently make
            # every category match fail.
            "name_folded": None,
            "store": "Willys",
            "price": 12.0,
            "unit_price": 12.0,
            "base_unit": "kilogram",
            "unit_symbol": "kg",
            "size_from": 1.0,
            "size_to": 1.0,
            "currency": "SEK",
            "department": "mejeri",
            "valid_from": "2026-10-01T00:00:00+00:00",
            "valid_until": "2026-10-11T00:00:00+00:00",
            "image": None,
        }
        offer.update(overrides)
        return offer

    return _make
