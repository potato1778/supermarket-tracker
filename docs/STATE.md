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
```

The managed Python environment does not have `requests`. Use the project venv.

## Current status

| | |
|---|---|
| Milestones | M0 done, M1 done, M2 next, M3 to M5 planned |
| Data | Willys 119 offers, Willys Hemma 33, mostly valid to 2026-10-11 |
| Next up | Tests, CI, and a source drift canary (M2) |

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

## What does not work yet

- **Pack-size extraction (FR-8).** Blocks two things at once: offers priced per
  `piece` (toilet paper, eggs) and the entire Lidl source. Lidl exposes only a
  unit hint such as `/kg`, never a unit price, so both need the same work.
- **Lidl.** It appears in the store list but returns zero offers. Confirmed with
  `businessIds=['03a7b3']`. The route is `lidl.se`, whose category pages embed
  products as JSON in `data-grid-data` attributes.
- Notifications (FR-9) and a web UI on the new data layer.
- Tests and CI (M2).

## Known open questions

- `cheapest mjolk` returns gräddfil and coconut milk, because the category's
  match list lumps dairy together. Splitting it is a curation decision, not a
  bug fix.
- Which region number `lidl.se` serves for Gothenburg. It appears to follow the
  request IP, so from Sweden it returns region 1.

## Conventions

- Repository holds code only. No scraped data, no database, no credentials.
- Never convert kilograms to litres. They are not interchangeable without a
  density, and a precise-looking wrong number is worse than no number.
- A unit price of zero means unknown, not free.
- Category matching is on word boundaries, because plain substring matching
  puts chicken in the cheese ranking (`kycklingbröstfilé` contains `ost`).
