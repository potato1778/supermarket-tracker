"""Offer source: ereklamblad.se.

The site's search endpoint does not accept a plain JSON body. It expects a
base64-encoded command array, so the payload is built and encoded here.

Two ways in, both verified:

  searchTerm    matches product names
  businessIds   matches the store, and returns everything that store has

businessIds is the better one for "what is on at Willys this week", because it
does not depend on guessing which product words the store happens to use.

The endpoint reports no total count, so paging continues until a page comes
back short of the requested size. Requests are rate limited on purpose: this
is an undocumented internal endpoint and hammering it is both rude and a good
way to get blocked.
"""

import base64
import json
import time

import requests

from normalize import normalize_offer

SOURCE = "tjek"

API_URL = "https://ereklamblad.se/"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "origin": "https://ereklamblad.se",
    "referer": "https://ereklamblad.se/",
}

PAGE_SIZE = 100
MAX_PAGES = 40  # hard stop so a misbehaving endpoint cannot loop forever
REQUEST_TIMEOUT = 25
PAUSE_SECONDS = 0.6  # between pages


def _post(command):
    """Send one command array and return the decoded response."""
    encoded = base64.b64encode(
        json.dumps(command, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    response = requests.post(
        API_URL,
        json={"data": [encoded]},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def list_businesses():
    """Every store the site knows about, as {name: public_id}.

    Lidl appears in this list but returns no offers, so presence here does not
    mean the store has anything to fetch.
    """
    payload = _post(["businesses", {}])
    businesses = payload.get("value") or []
    return {b["name"]: b["publicId"] for b in businesses if b.get("name")}


def _offer_params(search_term=None, business_ids=None, limit=PAGE_SIZE, offset=0):
    params = {
        "hideUpcoming": False,
        "pagination": {"limit": limit, "offset": offset},
        "sort": ["score_desc"],
    }
    if search_term:
        params["searchTerm"] = search_term
    if business_ids:
        # The only spelling the endpoint honours. dealerIds, businessId,
        # businessPublicIds and filter.businessIds are silently ignored, which
        # is easy to mistake for "this store has no offers".
        params["businessIds"] = list(business_ids)
    return params


def fetch_page(search_term=None, offset=0, limit=PAGE_SIZE, business_ids=None):
    """Fetch a single page of raw records. Returns a list (possibly empty)."""
    payload = _post(["offers", _offer_params(search_term, business_ids, limit, offset)])
    return ((payload.get("value") or {}).get("data")) or []


def _paged(search_term=None, business_ids=None, max_pages=MAX_PAGES,
           pause=PAUSE_SECONDS, verbose=False, label=""):
    """Shared paging loop. Returns canonical offer dicts, deduplicated."""
    offers = []
    seen = set()

    for page in range(max_pages):
        offset = page * PAGE_SIZE
        try:
            raw_records = fetch_page(
                search_term=search_term, offset=offset, business_ids=business_ids
            )
        except (requests.RequestException, ValueError) as exc:
            print(f"[{SOURCE}] 第 {page + 1} 页失败，停止翻页：{exc}")
            break

        if not raw_records:
            break

        for raw in raw_records:
            offer = normalize_offer(raw)
            if not offer:
                continue
            offer["source"] = SOURCE
            if offer["public_id"] in seen:
                continue
            seen.add(offer["public_id"])
            offers.append(offer)

        if verbose:
            print(f"[{SOURCE}] {label} 第 {page + 1} 页 +{len(raw_records)}（累计 {len(offers)}）")

        # A short page means we reached the end.
        if len(raw_records) < PAGE_SIZE:
            break

        time.sleep(pause)

    return offers


def fetch(search_term, max_pages=MAX_PAGES, pause=PAUSE_SECONDS, verbose=False):
    """Fetch every offer matching one search term."""
    return _paged(
        search_term=search_term, max_pages=max_pages, pause=pause,
        verbose=verbose, label=f"'{search_term}'",
    )


def fetch_business(business_id, max_pages=MAX_PAGES, pause=PAUSE_SECONDS,
                   verbose=False, label=""):
    """Fetch everything one store currently has on offer."""
    return _paged(
        business_ids=[business_id], max_pages=max_pages, pause=pause,
        verbose=verbose, label=label or business_id,
    )
