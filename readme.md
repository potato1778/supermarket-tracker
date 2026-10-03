# Supermarket Discount Tracker

Collects current supermarket offers in Sweden and answers two questions:

1. Which store currently has the cheapest X per unit?
2. Is this advertised discount actually a discount?

The first question is why offers get normalized onto a common unit. The second
is why price history exists.

## Status

Working: ingestion, normalization, storage, price history, search, and per-unit
ranking across stores.

Not yet: pack-size extraction, which would unlock both the per-piece categories
and the Lidl source. Notifications and a web interface on top of the new data
layer are also still open. See `docs/REQUIREMENTS.md`.

`app.py` and `database_manager.py` are the earlier web version. They still run
on a separate, simpler schema.

## How it works

The site's search endpoint does not accept a plain JSON body. It expects a
base64-encoded command array, so the client builds and encodes the payload
itself:

```python
["offers", {"pagination": {"limit": 100, "offset": 0},
            "searchTerm": "ost",
            "sort": ["score_desc"]}]
```

`sources/tjek.py` builds that payload, pages through the results, and pauses
between requests. The endpoint reports no total count, so paging stops when a
page comes back short.

## Price and unit normalization

The raw response carries four price fields with no documented precedence, and a
single product can have more than one. `normalize.py` resolves them in a fixed
order:

1. `membershipPrice`
2. `appPrice`
3. `fromPrice`
4. `price`

The same module extracts the store name defensively, since the `business`
object is sometimes absent. Every code path stores offers through it, so the
command line and the web app cannot write different values for the same field.

Unit prices are not recomputed here. The source already normalizes them onto a
base unit, including multi-pack offers. A six-pack of 450 g coffee at 699 kr
comes back as 129.44 kr/kg.

## Comparing across stores

`categories.py` defines what may be compared with what. Each category declares
the base units it ranks, and offers in any other base unit are excluded.

One constraint matters here. Kilogram and litre are not convertible, because no
density data is available. Laundry detergent arrives as liquid (litres), powder
(kilograms) and pods (pieces), so it is split into separate categories. A
precise-looking wrong number is worse than no number.

Offers whose unit price is zero are treated as unknown. The source emits zero
for items it cannot normalize, such as restaurant meals, and sorting ascending
would otherwise put those first.

## Storage

```
offer              current offers only; expired rows are deleted
price_observation  one row per product per day, kept indefinitely
offer_fts          FTS5 index over the diacritic-folded name
```

Search folds `å ä ö` to `a a o` before indexing and before querying, because the
trigram tokenizer does not fold diacritics on its own. `mjolk` therefore finds
`Mjölk`.

## Running it

```bash
pip install -r requirements.txt

python cli.py fetch                 # fetch every category's search terms
python cli.py fetch mjölk kyckling  # or specific terms
python cli.py cheapest kyckling     # rank by unit price across stores
python cli.py search mjolk          # diacritics optional
python cli.py purge                 # drop expired offers, keep price history
python cli.py stats

python app.py                       # earlier Flask interface
```

## Notes

- Search terms are Swedish (`mjölk`, `ost`, `bröd`), because that is what the
  source site indexes.
- The repository holds code only. No scraped data, no database file, no
  credentials. The tool is for personal, low-frequency use.
- Requirements and design decisions live in `docs/REQUIREMENTS.md`.
- The `_archive/` directory holds earlier scripts, kept for reference.
- Written in Python with `requests`, Flask and SQLite.
