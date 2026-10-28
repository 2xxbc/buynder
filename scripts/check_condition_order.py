"""READ-ONLY: how often does PokeTrace price a played condition ABOVE Near Mint on the same source?

For the PokeTrace data-issues email ("X of Y cards we checked"). Near Mint should be the highest price, then
Lightly Played, Moderately Played, Heavily Played, Damaged.

What it does:
  - Database: picks popular English cards from market_cards (most sales, $10+ average, synced in the last 7 days),
    SELECT only, inside a READ ONLY transaction (MySQL refuses any write in it).
  - PokeTrace: 1 request per card (GET /v1/cards/<id>, the same detail the card page uses), --cards of them
    (default 150, at most 190, so under 200 requests in total), one every 2.1 seconds (about 5 minutes).
  - Compares, per source (TCGplayer, eBay), each played condition's avg with that source's Near Mint avg, and
    notes whether the Near Mint price is stale (lastUpdated more than 30 days ago).
  - Reads POKETRACE_API_KEY and DB_* from .env itself; never prints them.
  - Writes scripts/condition_order_check.json; the Ops report's PokeTrace draft reads the totals from it.
Run:  ~/pokemarket/venv/bin/python scripts/check_condition_order.py            (150 cards)
      ~/pokemarket/venv/bin/python scripts/check_condition_order.py --cards 50 (a quicker look)
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

CONDITIONS = ["NEAR_MINT", "LIGHTLY_PLAYED", "MODERATELY_PLAYED", "HEAVILY_PLAYED", "DAMAGED"]
SHORT = {"LIGHTLY_PLAYED": "LP", "MODERATELY_PLAYED": "MP", "HEAVILY_PLAYED": "HP", "DAMAGED": "DMG"}
MAX_CARDS = 190
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "condition_order_check.json")


def inversions(detail, today):
    """[{source, condition, price, nm_price, nm_last_updated, nm_stale, cond_last_updated}] for every played
    condition priced ABOVE Near Mint on the same source."""
    out = []
    stale_before = (today - timedelta(days=30)).isoformat()
    for source, block in (detail.get("prices") or {}).items():
        nm = (block or {}).get("NEAR_MINT") or {}
        if nm.get("avg") is None:
            continue
        for cond in CONDITIONS[1:]:
            p = (block or {}).get(cond) or {}
            if p.get("avg") is not None and p["avg"] > nm["avg"]:
                nm_upd = (nm.get("lastUpdated") or "")[:10]
                out.append({"source": source, "condition": cond, "price": p["avg"], "sale_count": p.get("saleCount"),
                            "cond_last_updated": (p.get("lastUpdated") or "")[:10], "nm_price": nm["avg"],
                            "nm_sale_count": nm.get("saleCount"), "nm_last_updated": nm_upd,
                            "nm_stale": bool(nm_upd) and nm_upd < stale_before})
    return out


def summarize(checked, today):
    """Totals for the email, from [{card, detail or None}]."""
    ok = [c for c in checked if c.get("detail")]
    bad = []
    by_source, by_cond = {}, {}
    for c in ok:
        inv = inversions(c["detail"], today)
        if inv:
            bad.append({"poketrace_id": c["poketrace_id"], "name": c["name"], "set": c["set_name"],
                        "number": c["card_number"], "inversions": inv})
            for i in inv:
                by_source[i["source"]] = by_source.get(i["source"], 0) + 1
                by_cond[SHORT[i["condition"]]] = by_cond.get(SHORT[i["condition"]], 0) + 1
    stale_nm = sum(1 for b in bad if any(i["nm_stale"] for i in b["inversions"]))
    return {"checked": len(ok), "failed": len(checked) - len(ok), "cards_with_inversion": len(bad),
            "cards_where_nm_was_stale": stale_nm, "inversions_by_source": by_source,
            "inversions_by_condition": by_cond, "examples": bad[:25]}


def main():
    ap = argparse.ArgumentParser(description="Count cards with a played condition priced above Near Mint (read-only)")
    ap.add_argument("--cards", type=int, default=150, help=f"cards to check (1 PokeTrace request each, max {MAX_CARDS})")
    args = ap.parse_args()
    n = max(1, min(args.cards, MAX_CARDS))

    import requests
    import mysql.connector
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/pokemarket/.env"))
    key = os.getenv("POKETRACE_API_KEY")
    if not key:
        sys.exit("POKETRACE_API_KEY not found")

    conn = mysql.connector.connect(host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER"),
                                   password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME", "pokemarket"))
    cur = conn.cursor(dictionary=True)
    cur.execute("START TRANSACTION READ ONLY")
    cur.execute("""
        SELECT poketrace_id, name, set_name, card_number, sale_count, avg30d
        FROM market_cards
        WHERE avg30d >= 10 AND sale_count >= 50 AND last_synced >= NOW() - INTERVAL 7 DAY
          AND name NOT LIKE %s AND set_name NOT LIKE %s
        ORDER BY sale_count DESC LIMIT %s
    """, ("%(Japanese)%", "%Japan%", n))
    cards = cur.fetchall()
    cur.execute("ROLLBACK")
    cur.close()
    conn.close()
    print(f"Checking {len(cards)} popular cards (1 PokeTrace request each, about {len(cards) * 2.1 / 60:.0f} min)...")

    checked, remaining = [], None
    for i, c in enumerate(cards, 1):
        r = requests.get(f"https://api.poketrace.com/v1/cards/{c['poketrace_id']}", headers={"X-API-Key": key}, timeout=20)
        remaining = r.headers.get("x-ratelimit-remaining", remaining)
        detail = (r.json() or {}).get("data") if r.status_code == 200 else None
        checked.append({**c, "detail": detail})
        if r.status_code == 429:
            print("PokeTrace said 'too many requests': stopping early; the totals cover the cards checked so far.")
            break
        if i % 25 == 0:
            print(f"  {i}/{len(cards)}")
        time.sleep(2.1)

    s = summarize(checked, date.today())
    s.update(run_at=datetime.now().isoformat(timespec="seconds"), poketrace_requests=len(checked),
             poketrace_remaining=remaining,
             sample="most-sold English cards in market_cards ($10+ 30-day average, 50+ sales, synced in the last 7 days)")
    with open(OUT, "w") as f:
        json.dump(s, f, indent=1)

    print(f"\n{s['cards_with_inversion']} of {s['checked']} cards have a played condition priced above Near Mint on the same source"
          f" ({s['failed']} lookups failed).")
    print(f"  In {s['cards_where_nm_was_stale']} of them the Near Mint price hadn't been updated in 30+ days.")
    print(f"  By source: {s['inversions_by_source']}   By condition: {s['inversions_by_condition']}")
    for b in s["examples"][:8]:
        i = b["inversions"][0]
        print(f"  {b['name']} {b['number']} ({b['set']}): {i['source']} {SHORT[i['condition']]} ${i['price']} > NM ${i['nm_price']}"
              f" (NM updated {i['nm_last_updated']})")
    print(f"\nSaved {OUT} | PokeTrace requests used: {len(checked)} | left today: {remaining}")


if __name__ == "__main__":
    main()
