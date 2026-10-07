"""FR-1 — ingest from the ereklamblad.se (Tjek) endpoint.

No test here touches the network. The transport is faked at `_post` and at
`fetch_page`, which is the seam the paging loop actually uses, so the tests
cover the logic that decides when to stop, what to skip and what to keep.
"""

from __future__ import annotations

import base64
import json

import pytest
import requests

from sources import tjek


def _raw(public_id, name="Mjölk", **extra):
    return {"publicId": public_id, "name": name, **extra}


@pytest.fixture
def paged(monkeypatch):
    """Drive `_paged` from a list of pages, with a tiny page size and no sleep.

    `pause` is injected as an explicit keyword rather than by patching the
    module constant, because the default argument was bound at import time.
    """
    monkeypatch.setattr(tjek, "PAGE_SIZE", 3)
    sleeps = []
    monkeypatch.setattr(tjek.time, "sleep", lambda s: sleeps.append(s))

    def _run(pages, **kwargs):
        calls = {"n": 0}

        def fake_fetch_page(search_term=None, offset=0, limit=None, business_ids=None):
            index = calls["n"]
            calls["n"] += 1
            if index >= len(pages):
                return []  # ran off the end of the scripted pages
            if isinstance(pages[index], Exception):
                raise pages[index]
            return pages[index]

        monkeypatch.setattr(tjek, "fetch_page", fake_fetch_page)
        kwargs.setdefault("pause", 0)
        return tjek._paged(**kwargs), calls, sleeps

    return _run


# --- the request payload ---------------------------------------------------

def test_offer_params_only_includes_a_search_term_when_given():
    assert "searchTerm" not in tjek._offer_params()
    assert tjek._offer_params(search_term="ost")["searchTerm"] == "ost"


def test_offer_params_uses_the_one_spelling_the_endpoint_honours():
    params = tjek._offer_params(business_ids=["03a7b3"])
    assert params["businessIds"] == ["03a7b3"]
    # The spellings that are silently ignored; a typo here looks like "no offers".
    for wrong in ("dealerIds", "businessId", "businessPublicIds"):
        assert wrong not in params


def test_offer_params_always_carries_paging_and_sort():
    params = tjek._offer_params()
    assert params["pagination"] == {"limit": tjek.PAGE_SIZE, "offset": 0}
    assert params["sort"] == ["score_desc"]
    assert params["hideUpcoming"] is False


def test_post_base64_encodes_the_command_array(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": {"data": []}}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(tjek.requests, "post", fake_post)
    tjek._post(["offers", {"searchTerm": "ost"}])

    assert captured["url"] == tjek.API_URL
    encoded = captured["body"]["data"][0]
    assert json.loads(base64.b64decode(encoded)) == ["offers", {"searchTerm": "ost"}]
    # The endpoint rejects a request without these.
    assert captured["headers"]["origin"] == "https://ereklamblad.se"
    assert captured["headers"]["referer"] == "https://ereklamblad.se/"
    assert captured["timeout"] == tjek.REQUEST_TIMEOUT


def test_post_raises_on_an_http_error(monkeypatch):
    class Failing:
        def raise_for_status(self):
            raise requests.HTTPError("500")

    monkeypatch.setattr(tjek.requests, "post", lambda *a, **k: Failing())
    with pytest.raises(requests.HTTPError):
        tjek._post(["offers", {}])


# --- paging ----------------------------------------------------------------

def test_a_short_page_ends_the_paging(paged):
    offers, calls, _ = paged(
        [[_raw("a"), _raw("b"), _raw("c")], [_raw("d")]],
        search_term="ost",
    )
    assert [o["public_id"] for o in offers] == ["a", "b", "c", "d"]
    assert calls["n"] == 2


def test_an_empty_first_page_returns_nothing(paged):
    offers, calls, _ = paged([[]], search_term="ost")
    assert offers == []
    assert calls["n"] == 1


def test_a_full_page_followed_by_nothing_stops(paged):
    offers, calls, _ = paged([[_raw("a"), _raw("b"), _raw("c")], []], search_term="ost")
    assert len(offers) == 3
    assert calls["n"] == 2


def test_duplicate_ids_across_pages_are_collapsed(paged):
    offers, _, _ = paged(
        [[_raw("a"), _raw("b"), _raw("c")], [_raw("c"), _raw("d")]],
        search_term="ost",
    )
    assert [o["public_id"] for o in offers] == ["a", "b", "c", "d"]


def test_a_malformed_record_is_skipped_without_losing_the_page(paged):
    """One bad record must not cost the rest of the page."""
    offers, _, _ = paged(
        [[_raw("a"), {"name": "no id"}, "not a dict", _raw("b")]],
        search_term="ost",
    )
    assert [o["public_id"] for o in offers] == ["a", "b"]


def test_a_network_failure_stops_the_term_but_keeps_what_was_fetched(paged):
    offers, calls, _ = paged(
        [[_raw("a"), _raw("b"), _raw("c")], requests.ConnectionError("boom")],
        search_term="ost",
    )
    assert [o["public_id"] for o in offers] == ["a", "b", "c"]
    assert calls["n"] == 2


def test_a_failure_on_the_first_page_returns_nothing_and_does_not_raise(paged):
    offers, _, _ = paged([requests.Timeout("slow")], search_term="ost")
    assert offers == []


def test_a_bad_json_body_is_treated_like_a_network_failure(paged):
    offers, _, _ = paged([[ValueError("not json")]], search_term="ost")
    assert offers == []


def test_paging_is_capped(paged, monkeypatch):
    """A misbehaving endpoint that never comes back short must not loop forever."""

    def always_full(search_term=None, offset=0, limit=None, business_ids=None):
        return [_raw("p%d-%d" % (offset, i)) for i in range(3)]

    monkeypatch.setattr(tjek, "fetch_page", always_full)
    offers = tjek._paged(search_term="ost", max_pages=4, pause=0)
    assert len(offers) == 12


def test_pause_happens_between_pages_but_not_after_the_last(paged):
    _, calls, sleeps = paged(
        [[_raw("a"), _raw("b"), _raw("c")], [_raw("d")]],
        search_term="ost",
        pause=0.6,
    )
    assert calls["n"] == 2
    assert sleeps == [0.6]  # one gap between two pages, none after the short page


# --- the two public entry points -------------------------------------------

def test_fetch_passes_the_search_term(monkeypatch):
    seen = {}

    def fake_paged(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(tjek, "_paged", fake_paged)
    tjek.fetch("mjölk")
    assert seen["search_term"] == "mjölk"
    assert "business_ids" not in seen or seen.get("business_ids") is None


def test_fetch_business_passes_the_business_id(monkeypatch):
    seen = {}

    def fake_paged(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(tjek, "_paged", fake_paged)
    tjek.fetch_business("03a7b3", label="Willys")
    assert seen["business_ids"] == ["03a7b3"]
    assert seen["label"] == "Willys"


def test_list_businesses_maps_name_to_public_id(monkeypatch):
    monkeypatch.setattr(
        tjek, "_post",
        lambda command: {"value": [
            {"name": "Willys", "publicId": "abc"},
            {"name": "Coop", "publicId": "def"},
            {"name": None, "publicId": "skip"},
            {"publicId": "nameless"},
        ]},
    )
    assert tjek.list_businesses() == {"Willys": "abc", "Coop": "def"}


def test_fetch_page_unwraps_the_response(monkeypatch):
    """fetch_page returns raw source records, not canonical offers."""
    monkeypatch.setattr(tjek, "_post", lambda command: {"value": {"data": [_raw("a")]}})
    assert [r["publicId"] for r in tjek.fetch_page()] == ["a"]


def test_fetch_page_tolerates_a_missing_data_key(monkeypatch):
    monkeypatch.setattr(tjek, "_post", lambda command: {"value": {}})
    assert tjek.fetch_page() == []


def test_rate_limiting_constants_are_sane():
    """NFR-2: a timeout, a delay, and a hard page cap must all be present."""
    assert tjek.REQUEST_TIMEOUT > 0
    assert tjek.PAUSE_SECONDS > 0
    assert 0 < tjek.MAX_PAGES <= 100
    assert tjek.PAGE_SIZE > 0
