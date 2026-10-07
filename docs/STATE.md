# State — where this project stands

Last updated 2026-10-07.

This file exists so the project carries its own status. Conversation history
lives in one WorkBuddy workspace, but the code does not, so anything a new
session needs to pick up belongs here.

## How to run it

```bash
cd D:\Dev\supermarket-tracker
.venv\Scripts\activate                 # the project's own venv, not the global one
pip install -r requirements.txt

python cli.py fetch --store Willys "Willys Hemma" --pages 5
python cli.py stores                   # what is in the database
python cli.py deals Willys             # everything one store has, grouped
python cli.py cheapest kyckling        # rank by unit price across stores
python cli.py search mjolk             # diacritics optional
python cli.py purge                    # drop expired offers, keep price history
python cli.py stats

python -m pytest                       # offline test suite, no network
python tools/canary.py                 # live source drift check
```

The managed Python environment does not have `requests`. Use the project venv.

## Current status

| | |
|---|---|
| Milestones | M0, M1, M2 done; M3 to M5 planned |
| Data | Willys 119 offers, Willys Hemma 33, mostly valid to 2026-10-11 |
| Tests | 283 tests, all passing, offline and hermetic |
| Next up | Pack-size extraction (M3), which unblocks `piece` and Lidl |

Machine-specific notes, including local credentials and uncommitted work, are
deliberately kept out of this file because the repository is public. See
`NOTES.local.md` (not tracked) on the machine that runs the tool.

## What works

- Ingest by search term, and by store (`businessIds`). The store route is the
  better one and returns everything a store has.
- Normalization onto one canonical offer shape.
- Price history, one observation per product per day.
- Free-text search that ignores missing diacritics.
- Per-unit ranking across stores, with incompatible units excluded.
- Expiry purge that keeps price history.
- **Tests and CI (M2).** `tests/` covers FR-1..FR-7, FR-10 and NFR-3/NFR-4;
  `.github/workflows/ci.yml` runs them on Linux and Windows.
- **Source drift canary (M2).** `tools/canary.py`, also run daily by
  `.github/workflows/canary.yml`. See `docs/STATE.md` "The canary" below.

## What does not work yet

- **Pack-size extraction (FR-8).** Blocks two things at once: offers priced per
  `piece` (toilet paper, eggs) and the entire Lidl source. Lidl exposes only a
  unit hint such as `/kg`, never a unit price, so both need the same work.
- **Lidl.** It appears in the store list but returns zero offers. Confirmed with
  `businessIds=['03a7b3']`. The route is `lidl.se`, whose category pages embed
  products as JSON in `data-grid-data` attributes. The canary already checks
  that this entry point is still intact, so M3 starts from a known-good shape.
- Notifications (FR-9) and a web UI on the new data layer.

## The canary

`tools/canary.py` exits `0` (no drift), `1` (drift) or `2` (unreachable). The
third code is separate on purpose: a network failure is not a drift signal.

Its most useful check is not a schema check. For each sampled record it verifies
that `unitPrice` still reconciles with some documented price field divided by
the pack size — including a whole-number pack count, because `unitSizeFrom`
holds one pack, not the bundle. That is the check that would catch the source
redefining `unitPrice`, which would make every ranking wrong without any error.

Measured 2026-10-07 against the live source: 186 stores, 100/100 records shaped
as expected, 86/86 checkable records reconciled (100%, threshold 70%), median
unit price 51.79 kr. The margin is comfortable, so the threshold should not
produce false alarms.

`--insecure` skips TLS verification for the WorkBuddy sandbox proxy only. The
live run on this machine did not need it; never use it in CI or production.

## Known open questions

- `cheapest mjolk` returns gräddfil and coconut milk, because the category's
  match list lumps dairy together. Splitting it is a curation decision, not a
  bug fix.
- Which region number `lidl.se` serves for Gothenburg. It appears to follow the
  request IP, so from Sweden it returns region 1.
- The canary runs from GitHub's IPs on a schedule, so it may see a different
  store directory and region than the ingesting machine. That is fine for a
  shape check, but a drift report should be reproduced locally before acting.

## Conventions

- Repository holds code only. No scraped data, no database, no credentials.
- Never convert kilograms to litres. They are not interchangeable without a
  density, and a precise-looking wrong number is worse than no number.
- A unit price of zero means unknown, not free.
- Category matching is on word boundaries, because plain substring matching
  puts chicken in the cheese ranking (`kycklingbröstfilé` contains `ost`).
- A term in both a category's `match` and `exclude` is dead: it can never
  contribute a result. `tests/test_categories.py` fails if one appears. This is
  how the redundant `olivolja` entry in the `olja` category was found and
  removed (2026-10-07); behaviour is unchanged, since `exclude` already won.
