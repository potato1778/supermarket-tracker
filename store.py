"""SQLite storage: schema, upserts, price history and the comparison queries.

Two tables matter for the cross-store comparison:

  offer              current offers only. Rows whose validity has passed are
                     deleted, so this table never grows into an archive.
  price_observation  a slim (product, day, price) log that is kept forever.
                     Without it a "discount" cannot be checked against what
                     the item actually cost before.

Full-text search uses FTS5 with the trigram tokenizer, which needs the text to
be diacritic-folded first (see normalize.fold).
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from normalize import fold

DB_FILE = "offers.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS offer (
    public_id   TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    name        TEXT NOT NULL,
    name_folded TEXT NOT NULL,
    store       TEXT,
    price       REAL,
    unit_price  REAL,
    base_unit   TEXT,
    unit_symbol TEXT,
    size_from   REAL,
    size_to     REAL,
    currency    TEXT,
    department  TEXT,
    valid_from  TEXT,
    valid_until TEXT,
    image       TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_offer_base_unit ON offer(base_unit);
CREATE INDEX IF NOT EXISTS idx_offer_unit_price ON offer(unit_price);

CREATE TABLE IF NOT EXISTS price_observation (
    public_id   TEXT NOT NULL,
    observed_on TEXT NOT NULL,
    price       REAL,
    unit_price  REAL,
    PRIMARY KEY (public_id, observed_on)
);

CREATE VIRTUAL TABLE IF NOT EXISTS offer_fts USING fts5(
    public_id UNINDEXED,
    name_folded,
    tokenize = 'trigram'
);
"""

OFFER_COLUMNS = (
    "public_id",
    "source",
    "name",
    "name_folded",
    "store",
    "price",
    "unit_price",
    "base_unit",
    "unit_symbol",
    "size_from",
    "size_to",
    "currency",
    "department",
    "valid_from",
    "valid_until",
    "image",
    "first_seen",
    "last_seen",
)


def connect(path=DB_FILE):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_db(con):
    con.executescript(SCHEMA)
    con.commit()


def _today():
    return dt.date.today().isoformat()


def upsert_offers(con, offers, observed_on=None):
    """Insert or update offers and log today's price observation.

    Returns a dict with counts of new / updated / unchanged rows. A row counts
    as updated only when a price actually moved, which is what later drives
    notifications: alerting on every run would be noise.

    Uses ON CONFLICT DO UPDATE rather than INSERT OR REPLACE. REPLACE deletes
    the row and re-inserts it, which would reset first_seen on every run.
    """
    observed_on = observed_on or _today()
    today = dt.datetime.now().isoformat(timespec="seconds")

    new = updated = unchanged = 0

    update_columns = [c for c in OFFER_COLUMNS if c != "first_seen"]
    sql = (
        "INSERT INTO offer (%s) VALUES (%s) "
        "ON CONFLICT(public_id) DO UPDATE SET %s"
        % (
            ", ".join(OFFER_COLUMNS),
            ", ".join(":" + c for c in OFFER_COLUMNS),
            ", ".join("%s = excluded.%s" % (c, c) for c in update_columns),
        )
    )

    for offer in offers:
        existing = con.execute(
            "SELECT price, unit_price FROM offer WHERE public_id = ?",
            (offer["public_id"],),
        ).fetchone()

        if existing is None:
            new += 1
        elif (existing["price"], existing["unit_price"]) != (
            offer["price"],
            offer["unit_price"],
        ):
            updated += 1
        else:
            unchanged += 1

        values = {col: offer.get(col) for col in OFFER_COLUMNS}
        values["name_folded"] = offer.get("name_folded") or fold(offer.get("name"))
        values["first_seen"] = today  # ignored on conflict, so the original is kept
        values["last_seen"] = today
        con.execute(sql, values)

        # Keep the FTS index in step: FTS5 has no upsert.
        con.execute("DELETE FROM offer_fts WHERE public_id = ?", (offer["public_id"],))
        con.execute(
            "INSERT INTO offer_fts (public_id, name_folded) VALUES (?, ?)",
            (offer["public_id"], values["name_folded"]),
        )

        # Price history: one row per product per day.
        con.execute(
            "INSERT OR REPLACE INTO price_observation "
            "(public_id, observed_on, price, unit_price) VALUES (?, ?, ?, ?)",
            (offer["public_id"], observed_on, offer["price"], offer["unit_price"]),
        )

    con.commit()
    return {"new": new, "updated": updated, "unchanged": unchanged}


def purge_expired(con, now=None):
    """Delete offers whose validity window has closed.

    Offers without a valid_until are kept: we cannot tell whether they expired,
    and silently dropping them would hide data.
    """
    now = now or dt.datetime.now(dt.timezone.utc).isoformat()
    stale = [
        row["public_id"]
        for row in con.execute(
            "SELECT public_id FROM offer WHERE valid_until IS NOT NULL AND valid_until < ?",
            (now,),
        )
    ]
    for public_id in stale:
        con.execute("DELETE FROM offer_fts WHERE public_id = ?", (public_id,))
        con.execute("DELETE FROM offer WHERE public_id = ?", (public_id,))
    con.commit()
    return len(stale)


def _fts_query(text):
    """Turn free text into a safe FTS5 phrase query.

    Wrapping in double quotes makes FTS5 treat the input as a literal phrase,
    which avoids syntax errors on characters like * or -.
    """
    return '"%s"' % text.replace('"', '""')


def search(con, text, limit=50):
    """Free-text search over product names.

    The trigram tokenizer needs at least three characters, so shorter queries
    fall back to a substring match.
    """
    needle = fold(text).strip()
    if not needle:
        return []

    if len(needle) < 3:
        rows = con.execute(
            "SELECT * FROM offer WHERE name_folded LIKE ? "
            "ORDER BY (unit_price IS NULL), unit_price LIMIT ?",
            ("%" + needle + "%", limit),
        )
    else:
        rows = con.execute(
            "SELECT offer.* FROM offer_fts "
            "JOIN offer ON offer.public_id = offer_fts.public_id "
            "WHERE offer_fts.name_folded MATCH ? "
            "ORDER BY (offer.unit_price IS NULL), offer.unit_price LIMIT ?",
            (_fts_query(needle), limit),
        )
    return [dict(r) for r in rows]


def cheapest(con, category, limit=20):
    """Rank current offers in one category by unit price.

    Only offers whose base unit is compatible with the category take part.
    Mixing kilograms with litres (or with per-piece prices) would produce a
    number that looks precise and is meaningless, so those are excluded rather
    than converted.
    """
    allowed = category["allowed_base_units"]
    match_terms = category["match"]
    exclude_terms = category.get("exclude", [])

    where = ["base_unit IN (%s)" % ",".join("?" * len(allowed))]
    params = list(allowed)

    where.append("unit_price IS NOT NULL AND unit_price > 0")
    where.append("(currency IS NULL OR currency = 'SEK')")

    like_any = " OR ".join("name_folded LIKE ?" for _ in match_terms)
    where.append("(%s)" % like_any)
    params += ["%" + fold(t) + "%" for t in match_terms]

    for term in exclude_terms:
        where.append("name_folded NOT LIKE ?")
        params.append("%" + fold(term) + "%")

    sql = (
        "SELECT * FROM offer WHERE %s ORDER BY unit_price ASC LIMIT ?"
        % " AND ".join(where)
    )
    params.append(limit)
    return [dict(r) for r in con.execute(sql, params)]


def price_history(con, public_id):
    return [
        dict(r)
        for r in con.execute(
            "SELECT observed_on, price, unit_price FROM price_observation "
            "WHERE public_id = ? ORDER BY observed_on",
            (public_id,),
        )
    ]


def stats(con):
    row = con.execute(
        "SELECT COUNT(*) AS offers, "
        "COUNT(unit_price) AS with_unit_price, "
        "COUNT(DISTINCT store) AS stores FROM offer"
    ).fetchone()
    obs = con.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    return {
        "offers": row["offers"],
        "with_unit_price": row["with_unit_price"],
        "stores": row["stores"],
        "price_observations": obs,
    }
