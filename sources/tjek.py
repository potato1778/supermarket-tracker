"""Offer source: ereklamblad.se.

The site's search endpoint does not accept a plain JSON body. It expects a
base64-encoded command array, so the payload is built and encoded here.

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


def build_payload(search_term, limit=PAGE_SIZE, offset=0):
    """Build the base64-encoded command array the endpoint expects."""
    command = [
        "offers",
        {
            "hideUpcoming": False,
            "pagination": {"limit": limit, "offset": offset},
            "searchTerm": search_term,
            "sort": ["score_desc"],
        },
    ]
    encoded = base64.b64encode(
        json.dumps(command, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return {"data": [encoded]}


def fetch_page(search_term, offset=0, limit=PAGE_SIZE, session=None):
    """Fetch a single page of raw records. Returns a list (possibly empty)."""
    session = session or requests
    response = session.post(
        API_URL,
        json=build_payload(search_term, limit, offset),
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return ((payload.get("value") or {}).get("data")) or []


def fetch(search_term, max_pages=MAX_PAGES, pause=PAUSE_SECONDS, verbose=False):
    """Fetch every offer matching one search term.

    Returns a list of canonical offer dicts. Invalid records are dropped
    rather than raising, because one malformed entry should not lose a page.
    """
    session = requests.Session()
    offers = []
    seen = set()

    for page in range(max_pages):
        offset = page * PAGE_SIZE
        try:
            raw_records = fetch_page(search_term, offset=offset, session=session)
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
            print(f"[{SOURCE}] '{search_term}' 第 {page + 1} 页 +{len(raw_records)}（累计 {len(offers)}）")

        # A short page means we reached the end.
        if len(raw_records) < PAGE_SIZE:
            break

        time.sleep(pause)

    return offers
