"""Command line entry point.

    python cli.py fetch                          # fetch every category term
    python cli.py fetch mjölk kyckling           # fetch specific terms
    python cli.py fetch --store Willys           # fetch everything one store has
    python cli.py fetch --store Willys "Willys Hemma" --pages 5
    python cli.py stores                         # stores present in the database
    python cli.py deals Willys                   # what is on at one store
    python cli.py cheapest kyckling              # rank by unit price
    python cli.py search mjolk                   # free text search
    python cli.py stats
    python cli.py purge                          # drop offers past their validity
"""

from __future__ import annotations

import argparse
import sys

import categories
import store
from normalize import BASE_UNIT_SYMBOL, fold
from sources import tjek


def _utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _category_terms():
    """Every Swedish match term across all categories, deduplicated."""
    terms = []
    seen = set()
    for key in categories.all_keys():
        for term in categories.CATEGORIES[key]["match"]:
            if term not in seen:
                seen.add(term)
                terms.append(term)
    for key in sorted(categories.NEEDS_SPEC_PARSING):
        for term in categories.NEEDS_SPEC_PARSING[key]["match"]:
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms


def cmd_fetch(args):
    con = store.connect()
    store.init_db(con)
    total = {"new": 0, "updated": 0, "unchanged": 0}

    if args.store:
        # Resolve store names to ids. Fetching by store beats guessing search
        # terms: it returns everything the store has, not a keyword sample.
        try:
            directory = tjek.list_businesses()
        except Exception as exc:  # noqa: BLE001
            print(f"取超市列表失败：{type(exc).__name__}: {exc}")
            return 1

        lowered = {name.lower(): pid for name, pid in directory.items()}
        jobs = []
        for wanted in args.store:
            pid = directory.get(wanted) or lowered.get(wanted.lower())
            if not pid:
                near = [n for n in directory if wanted.lower() in n.lower()][:5]
                print(f"  [!] 找不到超市 '{wanted}'" + (f"，相近的有：{near}" if near else ""))
                continue
            jobs.append((wanted, pid))

        if not jobs:
            con.close()
            return 1

        print(f"按超市抓取 {len(jobs)} 家，每家最多 {args.pages} 页…\n")
        for name, pid in jobs:
            try:
                offers = tjek.fetch_business(
                    pid, max_pages=args.pages, verbose=args.verbose, label=name
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  [{name}] 失败：{type(exc).__name__}: {exc}")
                continue
            if not offers:
                print(f"  [{name:<18}] 该超市当前没有可抓取的优惠")
                continue
            counts = store.upsert_offers(con, offers)
            for key in total:
                total[key] += counts[key]
            print(
                f"  [{name:<18}] 抓到 {len(offers):>4} 条 | "
                f"新 {counts['new']:>4} | 变动 {counts['updated']:>3} | 未变 {counts['unchanged']:>4}"
            )
    else:
        terms = args.terms or _category_terms()
        print(f"抓取 {len(terms)} 个关键词，每个最多 {args.pages} 页…\n")
        for term in terms:
            try:
                offers = tjek.fetch(term, max_pages=args.pages, verbose=args.verbose)
            except Exception as exc:  # noqa: BLE001 - one bad term must not stop the run
                print(f"  [{term}] 失败：{type(exc).__name__}: {exc}")
                continue

            if not offers:
                if args.verbose:
                    print(f"  [{term}] 无结果")
                continue

            counts = store.upsert_offers(con, offers)
            for key in total:
                total[key] += counts[key]
            print(
                f"  [{term:<18}] 抓到 {len(offers):>4} 条 | "
                f"新 {counts['new']:>4} | 变动 {counts['updated']:>3} | 未变 {counts['unchanged']:>4}"
            )

    print(f"\n合计：新增 {total['new']}，价格变动 {total['updated']}，未变 {total['unchanged']}")
    _print_stats(store.stats(con))
    con.close()
    return 0


def cmd_stores(args):
    con = store.connect()
    store.init_db(con)
    rows = store.store_names(con)
    print(f"库里的超市（{len(rows)} 家）：\n")
    for row in rows:
        print(f"  {row['store']:<30} {row['offers']:>5} 条")
    con.close()
    return 0


def cmd_deals(args):
    con = store.connect()
    store.init_db(con)
    rows = store.by_store(con, args.store, limit=args.limit)

    if not rows:
        known = [r["store"] for r in store.store_names(con)]
        near = [s for s in known if args.store.lower() in (s or "").lower()][:5]
        print(f"库里没有 '{args.store}' 的优惠。" + (f"相近的：{near}" if near else ""))
        print("先抓：python cli.py fetch --store \"%s\"" % args.store)
        con.close()
        return 1

    by_dept = {}
    for row in rows:
        by_dept.setdefault(row["department"] or "(未分类)", []).append(row)

    print(f"{args.store} —— 当前 {len(rows)} 条优惠，按类别分组\n")
    for dept in sorted(by_dept):
        group = by_dept[dept]
        print(f"── {dept} ({len(group)}) " + "─" * max(0, 44 - len(dept)))
        for row in group:
            unit = ""
            if row["unit_price"]:
                symbol = BASE_UNIT_SYMBOL.get(row["base_unit"], row["base_unit"] or "?")
                unit = f"{row['unit_price']:>8.2f} kr/{symbol}"
            price = f"{row['price']:>7.2f}" if row["price"] is not None else "      -"
            size = ""
            if row["size_from"] and row["size_to"]:
                size = f"  {row['size_from']:g}-{row['size_to']:g} {row['unit_symbol'] or ''}".rstrip()
            print(f"   {row['name'][:40]:<40} {price} kr {unit}{size}")
        print()
    con.close()
    return 0


def cmd_cheapest(args):
    con = store.connect()
    store.init_db(con)

    if args.category not in categories.CATEGORIES:
        if args.category in categories.NEEDS_SPEC_PARSING:
            print(
                f"'{args.category}' 是按件计价的类别，单位价要先从商品名里抽包装规格才有意义。\n"
                f"这一步还没做 —— 见 categories.NEEDS_SPEC_PARSING。"
            )
            return 1
        print(f"未知类别 '{args.category}'。可用：{', '.join(categories.all_keys())}")
        return 1

    category = categories.CATEGORIES[args.category]
    rows = store.cheapest(con, category, limit=args.limit)
    label = category["labels"]
    unit = BASE_UNIT_SYMBOL[category["canonical_unit"]] if category["canonical_unit"] in BASE_UNIT_SYMBOL else category["canonical_unit"]

    print(f"{label['sv']} / {label['en']} / {label['zh']}  —— 按 kr/{unit} 排名（{len(rows)} 条）\n")
    if not rows:
        print("没有可比较的优惠。（数据库是空的？先跑 `python cli.py fetch`）")
        return 0

    for i, row in enumerate(rows, 1):
        size = ""
        if row["size_from"] and row["size_to"]:
            size = f"  {row['size_from']:g}-{row['size_to']:g} {row['unit_symbol'] or ''}".rstrip()
        print(
            f"{i:>2}. {row['name'][:44]:<44} "
            f"{row['unit_price']:>7.2f} kr/{unit}   "
            f"{row['price'] if row['price'] is not None else '-':>7} kr"
            f"{size}   {row['store'] or '?'}"
        )
    con.close()
    return 0


def cmd_search(args):
    con = store.connect()
    store.init_db(con)
    rows = store.search(con, args.text, limit=args.limit)

    print(f"搜索 '{args.text}'（折叠为 '{fold(args.text)}'）→ {len(rows)} 条\n")
    for row in rows:
        unit = ""
        if row["unit_price"]:
            symbol = BASE_UNIT_SYMBOL.get(row["base_unit"], row["base_unit"] or "?")
            unit = f"{row['unit_price']:>7.2f} kr/{symbol}"
        print(f"  {row['name'][:46]:<46} {unit:>14}   {row['store'] or '?'}")
    con.close()
    return 0


def cmd_purge(args):
    con = store.connect()
    store.init_db(con)
    removed = store.purge_expired(con)
    print(f"已删除 {removed} 条过期优惠（价格历史保留）")
    _print_stats(store.stats(con))
    con.close()
    return 0


def cmd_stats(args):
    con = store.connect()
    store.init_db(con)
    _print_stats(store.stats(con))
    con.close()
    return 0


def _print_stats(s):
    print(
        f"\n当前优惠 {s['offers']} 条 | 其中有单位价 {s['with_unit_price']} 条 | "
        f"超市 {s['stores']} 家 | 价格观测 {s['price_observations']} 条"
    )


def main(argv=None):
    _utf8_stdout()
    parser = argparse.ArgumentParser(prog="cli.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="抓取优惠并入库")
    p.add_argument("terms", nargs="*", help="瑞典语关键词；省略则用全部分类词")
    p.add_argument("--store", nargs="+", metavar="NAME",
                   help="按超市抓（如 --store Willys \"Willys Hemma\"）；给了这个就忽略关键词")
    p.add_argument("--pages", type=int, default=3, help="每个关键词/每家超市最多翻几页（默认 3）")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("stores", help="列出库里已有的超市")
    p.set_defaults(func=cmd_stores)

    p = sub.add_parser("deals", help="某家超市当前所有优惠，按类别分组")
    p.add_argument("store")
    p.add_argument("--limit", type=int, default=1000)
    p.set_defaults(func=cmd_deals)

    p = sub.add_parser("cheapest", help="按单位价排名")
    p.add_argument("category")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_cheapest)

    p = sub.add_parser("search", help="全文搜索（可省略变音符）")
    p.add_argument("text")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    sub.add_parser("purge", help="删除过期优惠").set_defaults(func=cmd_purge)
    sub.add_parser("stats", help="统计").set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
