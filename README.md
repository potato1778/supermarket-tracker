# Supermarket Discount Tracker

A tool that collects current supermarket discounts in Sweden and makes them searchable. It talks to the undocumented search API behind [ereklamblad.se](https://ereklamblad.se/), normalizes the results, stores them in SQLite, and serves them through a small Flask web interface.

## How it works

The site's search endpoint does not accept a plain JSON body. It expects a base64-encoded command array, so the client has to build and encode the payload itself:

```python
["offers", {"pagination": {"limit": 100, "offset": 0},
            "searchTerm": "ost",
            "sort": ["score_desc"]}]
```

`api_communicator.py` builds that payload, base64-encodes it, and posts it. `fetch_search_results` catches both network failures and JSON decoding failures instead of letting them propagate, since the endpoint occasionally returns a non-JSON error page.

## Price normalization

The raw response carries several different price fields with no documented precedence, and a single product can have more than one of them. `clean_and_prepare_products` in `app.py` resolves them in a fixed order:

1. `membershipPrice`
2. `appPrice`
3. `fromPrice`
4. `price`

It also extracts the supermarket name defensively, because the `business` object is sometimes absent, and substitutes a placeholder image when the response has none. Keeping this logic in one place is what keeps the stored rows and the front end consistent with each other.

## Storage and interface

- `database_manager.py` sets up the SQLite schema and stores normalized products.
- `main.py` is a command-line version. It prompts for a keyword, fetches, and stores.
- `app.py` serves a Flask app with a search box and a results page, with CORS enabled so the front end can call the API directly.

## Running it

```bash
pip install requests flask flask-cors

python main.py     # command line
python app.py      # web interface
```

## Notes

- Search terms are in Swedish (`mjölk`, `ost`, `bröd`), because that is what the source site indexes.
- The `_archive/` directory holds earlier scripts, kept for reference.
- Written in Python with `requests`, Flask and SQLite.
