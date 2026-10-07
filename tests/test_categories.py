"""FR-10 — categories are data, not code.

Adding a category must be an edit to the tables in categories.py. These tests
assert the invariants the ranking code relies on, so a malformed entry fails
here rather than silently producing an empty or mixed ranking.
"""

from __future__ import annotations

import pytest

import categories
from normalize import BASE_UNIT_SYMBOL, COMPARABLE_BASE_UNITS


def _all():
    return {**categories.CATEGORIES, **categories.NEEDS_SPEC_PARSING}


def test_there_are_categories_to_check():
    assert categories.CATEGORIES
    assert categories.NEEDS_SPEC_PARSING


@pytest.mark.parametrize("key", sorted(_all()))
def test_every_category_carries_three_labels(key):
    labels = _all()[key]["labels"]
    assert set(labels) >= {"sv", "en", "zh"}
    assert all(labels[lang].strip() for lang in ("sv", "en", "zh"))


@pytest.mark.parametrize("key", sorted(_all()))
def test_every_category_has_match_terms(key):
    assert _all()[key]["match"], "%s has no match terms" % key


@pytest.mark.parametrize("key", sorted(_all()))
def test_match_and_exclude_are_lists_of_strings(key):
    category = _all()[key]
    for field in ("match", "exclude"):
        values = category.get(field, [])
        assert isinstance(values, list)
        assert all(isinstance(v, str) and v.strip() for v in values)


@pytest.mark.parametrize("key", sorted(categories.CATEGORIES))
def test_rankable_categories_declare_a_comparable_base_unit(key):
    category = categories.CATEGORIES[key]
    allowed = category["allowed_base_units"]
    assert allowed, "%s declares no base unit" % key
    for unit in allowed:
        assert unit in COMPARABLE_BASE_UNITS, "%s: %r is not comparable" % (key, unit)


@pytest.mark.parametrize("key", sorted(categories.CATEGORIES))
def test_canonical_unit_matches_a_single_allowed_base_unit(key):
    """A category that mixes units cannot state one canonical unit honestly."""
    category = categories.CATEGORIES[key]
    allowed = category["allowed_base_units"]
    canonical = category["canonical_unit"]
    if len(allowed) == 1:
        assert BASE_UNIT_SYMBOL[allowed[0]] == canonical
    else:
        assert canonical in {BASE_UNIT_SYMBOL[u] for u in allowed}


@pytest.mark.parametrize("key", sorted(categories.CATEGORIES))
def test_exclude_terms_are_not_also_match_terms(key):
    """An exclude term that also matches would remove every result."""
    category = categories.CATEGORIES[key]
    overlap = set(category["match"]) & set(category.get("exclude", []))
    assert not overlap, "%s excludes a term it also matches: %s" % (key, overlap)


def test_piece_categories_are_kept_separate():
    """Per-piece categories need pack size before a unit price means anything."""
    for key in categories.NEEDS_SPEC_PARSING:
        assert key not in categories.CATEGORIES
        assert "allowed_base_units" not in categories.NEEDS_SPEC_PARSING[key]


def test_get_returns_a_rankable_category():
    assert categories.get("ost") is categories.CATEGORIES["ost"]


def test_get_rejects_an_unknown_category_with_a_helpful_message():
    with pytest.raises(KeyError) as excinfo:
        categories.get("nonsense")
    assert "nonsense" in str(excinfo.value)
    assert "ost" in str(excinfo.value)  # the message lists the known keys


def test_get_refuses_a_spec_parsing_category():
    """These are not rankable yet, so get() must not hand them out."""
    with pytest.raises(KeyError):
        categories.get("agg")


def test_all_keys_is_sorted_and_complete():
    keys = categories.all_keys()
    assert keys == sorted(keys)
    assert set(keys) == set(categories.CATEGORIES)
