#!/usr/bin/env python3
"""Source drift canary (NFR-5).

Both sources behind this project are undocumented and unsupported: Tjek's API
is customer-only, and Lidl has none. The failure mode that matters is not a
crash — it is a *silent* one. If the endpoint keeps answering 200 but renames a
field or redefines `unitPrice`, ingest happily stores wrong numbers and every
ranking is wrong without a single error in the log.

This script polls the live sources and asserts the assumptions the rest of the
code depends on, then exits:

    0   everything still matches the documented shape
    1   drift — the source changed under us
    2   unreachable — the source could not be contacted at all

The distinction matters. Exit 2 is not a drift alarm; it means we could not
tell, and the check should be retried rather than "fixed". A scheduler should
alert on 1 and retry or warn on 2.

It is read-only and deliberately low-frequency: one page per source, no paging.

Usage:
    python tools/canary.py                 # human readable report
    python tools/canary.py --json          # machine readable
    python tools/canary.py --only businesses --only store_offers
    python tools/canary.py --insecure      # ONLY for the WorkBuddy sandbox proxy

`--insecure` disables TLS verification. The sandbox proxy presents a
self-signed certificate, so lidl.se cannot be reached from inside it otherwise.
Never use it for production code or in CI — that is an environment problem, not
a site problem.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from html import unescape
from statistics import median

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import requests  # noqa: E402

import normalize  # noqa: E402
from sources import tjek  # noqa: E402

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNREACHABLE = 2

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Chains that must still be in the store directory. Presence is a cheap proof
# that the businesses command still returns the real thing and not an error
# payload shaped like an empty list.
EXPECTED_CHAINS = ("willys", "ica", "coop", "hemköp", "lidl")

KNOWN_BASE_UNITS = set(normalize.COMPARABLE_BASE_UNITS)

# A per-unit price outside this band means `unitPrice` stopped being a per-unit
# price at all (a total, a percentage, a currency in öre).
SANE_UNIT_PRICE = (0.5, 5000.0)

# How much of the sample must reconcile before the semantic check passes.
SEMANTIC_AGREEMENT = 0.70
SEMANTIC_TOLERANCE = 0.10

# Multiples of a base unit, as they appear in `unitSymbol`.
_SIZE_SCALE = {
    ("kilogram", "g"): 0.001,
    ("kilogram", "kg"): 1.0,
    ("liter", "ml"): 0.001,
    ("liter", "cl"): 0.01,
    ("liter", "dl"): 0.1,
    ("liter", "l"): 1.0,
    ("piece", "pcs"): 1.0,
    ("piece", "st"): 1.0,
    ("piece", "styck"): 1.0,
}


class Unreachable(Exception):
    """The source could not be contacted, so nothing can be concluded."""


@dataclass
class Result:
    # Field order matters: checks build these positionally as
    # Result(name, ok, detail), and a reordered field would silently land the
    # detail string in `severity` — which would also stop it counting as a
    # failure.
    name: str
    ok: bool
    detail: str = ""
    severity: str = "fail"          # "fail" counts towards the exit code
    metrics: dict = field(default_factory=dict)

    def as_dict(self):
        return {
            "name": self.name,
            "ok": self.ok,
            "severity": self.severity,
            "detail": self.detail,
            "metrics": self.metrics,
        }


# --- pure helpers (unit-tested offline) ------------------------------------

def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(a, b, tolerance=SEMANTIC_TOLERANCE):
    """Relative closeness, guarding against a zero denominator."""
    if a is None or b is None:
        return False
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tolerance


def size_in_base_unit(record):
    """The pack size in the record's base unit, or None when not derivable.

    Returns None for a size *range* (350-500 g): the source may use either end,
    so reconciling against it would produce a false drift report.
    """
    base_unit = record.get("baseUnit")
    if base_unit not in KNOWN_BASE_UNITS:
        return None

    low = _num(record.get("unitSizeFrom"))
    high = _num(record.get("unitSizeTo"))
    if low is None or low <= 0:
        return None
    if high is not None and abs(high - low) > 1e-9:
        return None

    symbol = (record.get("unitSymbol") or "").strip().lower()
    scale = _SIZE_SCALE.get((base_unit, symbol))
    if scale is None:
        return None
    return low * scale


def unit_price_reconciles(record, max_pack=24):
    """Whether `unitPrice` still means "price per base unit".

    The source computes `unitPrice` from one of the four price fields and does
    not say which, so the record is accepted when *any* documented price field
    reproduces it.

    Multi-pack offers need care: `unitSizeFrom` holds the size of one pack, not
    of the bundle, so a 6 x 450 g pack legitimately reports
    `unitPrice = price / (6 x 0.45)`. The check therefore also accepts a whole
    number of packs. That is a deliberate loosening — it would let a wholesale
    redefinition of `unitPrice` slip through only if it happened to land on a
    small whole-number multiple of price/size for most records, which is not
    what a field redefinition looks like.

    Returns True, False, or None when the record cannot be checked.
    """
    size = size_in_base_unit(record)
    unit_price = _num(record.get("unitPrice"))
    if size is None or size <= 0 or unit_price is None or unit_price <= 0:
        return None

    for key in normalize.PRICE_PRECEDENCE:
        price = _num(record.get(key))
        if price is None or price <= 0:
            continue
        if _close(price, unit_price * size):
            return True
        packs = price / (unit_price * size)
        if 2 <= round(packs) <= max_pack and abs(packs - round(packs)) <= 0.05:
            return True
    return False


# --- checks ----------------------------------------------------------------

def check_businesses(ctx):
    directory = tjek.list_businesses()
    if not directory:
        return Result("businesses", False, "the businesses command returned an empty list")

    lowered = [name.lower() for name in directory]
    found = [chain for chain in EXPECTED_CHAINS if any(chain in name for name in lowered)]

    ctx.businesses = directory
    ctx.business_id = _pick_business(directory, "willys")

    return Result(
        "businesses",
        len(found) >= 3,
        "%d stores; expected chains present: %s"
        % (len(directory), ", ".join(found) or "none"),
        metrics={"count": len(directory), "chains": found},
    )


def _pick_business(directory, needle):
    for name, public_id in directory.items():
        if needle in name.lower():
            return public_id
    return None


def check_store_offers(ctx):
    if not ctx.business_id:
        return Result("store_offers", True, "skipped: no store id available", severity="info")

    ctx.records = tjek.fetch_page(business_ids=[ctx.business_id], limit=ctx.sample)
    if not ctx.records:
        return Result(
            "store_offers",
            False,
            "the store returned zero offers; either the store has none or the "
            "businessIds spelling stopped working",
        )
    return Result(
        "store_offers",
        True,
        "%d offers for the sampled store" % len(ctx.records),
        metrics={"records": len(ctx.records)},
    )


def check_record_shape(ctx):
    if not ctx.records:
        return Result("record_shape", True, "skipped: no records", severity="info")

    total = len(ctx.records)
    no_id = [r for r in ctx.records if not (r.get("publicId") or r.get("public_id"))]
    no_name = [r for r in ctx.records if not r.get("name")]
    with_store = [
        r for r in ctx.records
        if isinstance(r.get("business"), dict) and r["business"].get("name")
    ]
    store_ratio = len(with_store) / total

    ok = not no_id and not no_name and store_ratio >= 0.90
    return Result(
        "record_shape",
        ok,
        "%d/%d records carry a store name; %d without an id, %d without a name"
        % (len(with_store), total, len(no_id), len(no_name)),
        metrics={
            "records": total,
            "with_store": len(with_store),
            "missing_id": len(no_id),
            "missing_name": len(no_name),
        },
    )


def check_unit_fields(ctx):
    if not ctx.records:
        return Result("unit_fields", True, "skipped: no records", severity="info")

    unknown_unit = [r for r in ctx.records if r.get("baseUnit") not in KNOWN_BASE_UNITS | {None}]
    missing_symbol = [
        r for r in ctx.records
        if r.get("baseUnit") and not r.get("unitSymbol")
    ]
    with_unit_price = [r for r in ctx.records if _num(r.get("unitPrice")) is not None]
    zero_prices = [r for r in with_unit_price if _num(r["unitPrice"]) == 0]

    ok = not unknown_unit and not missing_symbol
    return Result(
        "unit_fields",
        ok,
        "baseUnit values within %s; %d/%d carry a unitPrice (%d of them exactly 0)"
        % (
            sorted(KNOWN_BASE_UNITS),
            len(with_unit_price),
            len(ctx.records),
            len(zero_prices),
        ),
        metrics={
            "unknown_base_unit": len(unknown_unit),
            "missing_unit_symbol": len(missing_symbol),
            "with_unit_price": len(with_unit_price),
            "zero_unit_price": len(zero_prices),
        },
    )


def check_unit_price_semantics(ctx):
    """The check that would catch a silent redefinition of `unitPrice`."""
    if not ctx.records:
        return Result("unit_price_semantics", True, "skipped: no records", severity="info")

    checked = consistent = 0
    disagreements = []
    values = []

    for record in ctx.records:
        verdict = unit_price_reconciles(record)
        if verdict is None:
            continue
        checked += 1
        unit_price = _num(record["unitPrice"])
        values.append(unit_price)
        if verdict:
            consistent += 1
        elif len(disagreements) < 5:
            disagreements.append({
                "name": record.get("name"),
                "unitPrice": unit_price,
                "size": size_in_base_unit(record),
                "prices": {k: _num(record.get(k)) for k in normalize.PRICE_PRECEDENCE},
            })

    if checked < 5:
        return Result(
            "unit_price_semantics",
            True,
            "only %d records were checkable; not enough to conclude" % checked,
            severity="info",
            metrics={"checked": checked},
        )

    ratio = consistent / checked
    med = median(values)
    in_band = SANE_UNIT_PRICE[0] <= med <= SANE_UNIT_PRICE[1]

    ok = ratio >= SEMANTIC_AGREEMENT and in_band
    return Result(
        "unit_price_semantics",
        ok,
        "%d/%d checkable records reconcile with a documented price field "
        "(%.0f%%, need %.0f%%); median unit price %.2f kr"
        % (consistent, checked, ratio * 100, SEMANTIC_AGREEMENT * 100, med),
        metrics={
            "checked": checked,
            "consistent": consistent,
            "ratio": round(ratio, 3),
            "median_unit_price": round(med, 2),
            "disagreements": disagreements,
        },
    )


def check_lidl_entry_point(ctx):
    """Advisory: lidl.se is source B, not wired into ingest yet (FR-8).

    It is reported but never fails the run, because nothing consumes it today —
    a change here should inform the M3 plan, not page anyone at 3am.
    """
    homepage = ctx.http_get("https://www.lidl.se/")
    homepage.raise_for_status()

    links = re.findall(r'href="(/c/[^"]+?/a\d+)"', homepage.text)
    page_url = "https://www.lidl.se" + links[0] if links else "https://www.lidl.se/"
    page = homepage if not links else ctx.http_get(page_url)
    page.raise_for_status()

    blobs = re.findall(r'data-grid-data="([^"]+)"', page.text)
    if not blobs:
        return Result(
            "lidl_entry_point",
            False,
            "no data-grid-data blobs on %s" % page_url,
            severity="warn",
        )

    records = []
    for blob in blobs[:50]:
        try:
            records.append(json.loads(unescape(blob)))
        except ValueError:
            return Result(
                "lidl_entry_point",
                False,
                "a data-grid-data blob is no longer valid JSON",
                severity="warn",
            )

    has_title = sum(1 for r in records if r.get("title"))
    has_price = sum(1 for r in records if r.get("regionsPrices"))
    ok = has_title == len(records) and has_price > 0
    return Result(
        "lidl_entry_point",
        ok,
        "%d blobs on %s; %d with a title, %d with regionsPrices"
        % (len(records), page_url, has_title, has_price),
        severity="warn",
        metrics={"blobs": len(records), "with_title": has_title, "with_prices": has_price},
    )


CHECKS = (
    check_businesses,
    check_store_offers,
    check_record_shape,
    check_unit_fields,
    check_unit_price_semantics,
    check_lidl_entry_point,
)


# --- runner ----------------------------------------------------------------

class Context:
    def __init__(self, args):
        self.sample = args.sample
        self.timeout = args.timeout
        self.insecure = args.insecure
        self.businesses = {}
        self.business_id = None
        self.records = None
        self._real_requests = None

    def http_get(self, url):
        return requests.get(
            url,
            timeout=self.timeout,
            verify=not self.insecure,
            headers={"User-Agent": USER_AGENT},
        )

    def allow_insecure(self):
        """Let tjek's own transport skip TLS verification, for the sandbox only."""
        if not self.insecure:
            return
        self._real_requests = tjek.requests
        real = self._real_requests

        class Proxy:
            def __getattr__(self, item):
                return getattr(real, item)

            def post(self, *args, **kwargs):
                kwargs.setdefault("verify", False)
                return real.post(*args, **kwargs)

        tjek.requests = Proxy()

    def restore(self):
        if self._real_requests is not None:
            tjek.requests = self._real_requests


def _run(ctx, checks):
    results = []
    for check in checks:
        try:
            results.append(check(ctx))
        except requests.RequestException as exc:
            results.append(Result(
                check.__name__.replace("check_", ""),
                False,
                "unreachable: %s: %s" % (type(exc).__name__, exc),
                severity="unreachable",
            ))
        except Exception as exc:  # noqa: BLE001 - a check must not kill the run
            results.append(Result(
                check.__name__.replace("check_", ""),
                False,
                "crashed: %s: %s" % (type(exc).__name__, exc),
            ))
    return results


def _print_report(results, stream=sys.stdout):
    width = max(len(r.name) for r in results)
    for result in results:
        if result.severity == "info":
            mark = " -- "
        elif result.ok:
            mark = " ok "
        elif result.severity == "warn":
            mark = "warn"
        elif result.severity == "unreachable":
            mark = " ?? "
        else:
            mark = "FAIL"
        print("[%s] %-*s  %s" % (mark, width, result.name, result.detail), file=stream)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="canary.py", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine readable output")
    parser.add_argument("--sample", type=int, default=100,
                        help="how many offers to inspect (default 100)")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--insecure", action="store_true",
                        help="skip TLS verification (WorkBuddy sandbox proxy only)")
    parser.add_argument("--only", action="append", default=None, metavar="NAME",
                        help="run only the named check(s); repeatable")
    args = parser.parse_args(argv)

    checks = CHECKS
    if args.only:
        wanted = set(args.only)
        checks = tuple(c for c in CHECKS if c.__name__.replace("check_", "") in wanted)
        unknown = wanted - {c.__name__.replace("check_", "") for c in CHECKS}
        if unknown:
            parser.error("unknown check(s): %s" % ", ".join(sorted(unknown)))

    ctx = Context(args)
    ctx.allow_insecure()
    try:
        results = _run(ctx, checks)
    finally:
        ctx.restore()

    failed = [r for r in results if not r.ok and r.severity == "fail"]
    unreachable = [r for r in results if r.severity == "unreachable"]

    if args.json:
        print(json.dumps({
            "results": [r.as_dict() for r in results],
            "drift": bool(failed),
            "unreachable": bool(unreachable) and not failed,
            "exit_code": EXIT_DRIFT if failed else (EXIT_UNREACHABLE if unreachable else EXIT_OK),
        }, indent=2, ensure_ascii=False))
    else:
        _print_report(results)
        if failed:
            print("\nDRIFT: %s" % ", ".join(r.name for r in failed))
        elif unreachable:
            print("\nCOULD NOT REACH A SOURCE — retry, this is not a drift signal.")
        else:
            print("\nNo drift. Every documented assumption still holds.")

    if failed:
        return EXIT_DRIFT
    if unreachable:
        return EXIT_UNREACHABLE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
