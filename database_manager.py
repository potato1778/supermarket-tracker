"""SQLite storage for normalized offers.

NOTE: this module is the legacy store used by app.py / main.py. It now routes
every record through normalize.normalize_offer(), which fixes a bug where the
web path wrote price=0.0 and supermarket=NULL for every row, because it read
keys that the cleaning step does not produce.
"""

import sqlite3

from normalize import normalize_offer

DATABASE_FILE = "search_results.db"


def _connect():
    return sqlite3.connect(DATABASE_FILE)


def setup_database():
    con = _connect()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS products(
                id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                price REAL,
                supermarket TEXT,
                unit_price REAL,
                keyword TEXT
            )
            """
        )
        con.commit()
    except sqlite3.Error as e:
        print(f"数据库错误：{e}")
        raise
    finally:
        con.close()
    print(f"数据库{DATABASE_FILE}已就绪")


def store_products(product_list, keyword):
    """Store a batch of offers.

    Accepts raw payloads or cleaned products: normalize_offer() understands
    both shapes, so the CLI and the web path cannot drift apart again.
    """
    if not product_list:
        print(f"没有关于'{keyword}'的商品可存储。")
        return 0

    rows = []
    for item in product_list:
        offer = normalize_offer(item)
        if not offer:
            continue
        rows.append(
            (
                offer["public_id"],
                offer["name"] or "未知商品",
                offer["price"],
                offer["store"],
                offer["unit_price"],
                keyword,
            )
        )

    if not rows:
        print(f"关于'{keyword}'的 {len(product_list)} 条数据全部无效，已跳过。")
        return 0

    con = _connect()
    try:
        con.executemany(
            """
            INSERT OR REPLACE INTO products
            (id, product_name, price, supermarket, unit_price, keyword)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        con.commit()
    except sqlite3.Error as e:
        print(f"错误：{e}")
        raise
    finally:
        con.close()

    print(f"{len(rows)}件关于'{keyword}'的商品已成功存入数据库。")
    return len(rows)


if __name__ == "__main__":
    setup_database()
