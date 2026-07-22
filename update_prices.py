"""
Daily price updater for PokeMarket Tracker — PokeTrace edition.

For every card with a poketrace_id:
  - Fetches fresh card detail (current price + stats) from PokeTrace
  - Fetches fresh price history (period=7d is enough since we already have backfill)
  - Merges new daily points into poketrace_history (dedupe by date)
  - Refreshes poketrace_stats
  - Appends current price to legacy price_history table

Runs once per day. Cron: 0 5 * * *
"""
import os
import json
import time
import requests
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POKETRACE_API_KEY")
BASE = "https://api.poketrace.com/v1"

db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

if not API_KEY:
    print(f"[{datetime.now().isoformat()}] ERROR: POKETRACE_API_KEY not configured")
    exit(1)


def call(path, params=None):
    """GET with delay to respect the 1-per-2s burst limit."""
    time.sleep(2.5)
    return requests.get(
        f"{BASE}{path}",
        headers={"X-API-Key": API_KEY},
        params=params,
        timeout=15
    )


def fetch_card_detail(poketrace_id):
    """Returns the card detail dict or None."""
    r = call(f"/cards/{poketrace_id}")
    if not r.ok:
        return None
    return r.json().get("data")


def fetch_recent_history(poketrace_id, period="7d"):
    """Returns the list of recent price points from PokeTrace."""
    r = call(f"/cards/{poketrace_id}/prices/NEAR_MINT/history", params={"period": period, "limit": 365})
    if not r.ok:
        return []
    return r.json().get("data", []) or []


def merge_history(existing, new_points):
    """
    Merge new history points into existing.
    Dedupe by (date, source) so different sources for the same date both survive.
    History can only grow, never shrink.
    """
    by_key = {}
    if existing:
        items = json.loads(existing) if isinstance(existing, str) else existing
        for pt in items:
            date = pt.get("date")
            source = pt.get("source", "unknown")
            if date:
                by_key[(date, source)] = pt
    for pt in (new_points or []):
        date = pt.get("date")
        source = pt.get("source", "unknown")
        if date:
            by_key[(date, source)] = pt                                                    
    return sorted(by_key.values(), key=lambda x: x["date"], reverse=True)

def build_stats(card_detail):
    prices = (card_detail.get("prices") or {}).get("tcgplayer") or {}
    nm = prices.get("NEAR_MINT") or {}
    return {
        "tcgplayer_NM_avg1d": nm.get("avg1d"),
        "tcgplayer_NM_avg7d": nm.get("avg7d"),
        "tcgplayer_NM_avg30d": nm.get("avg30d"),
        "tcgplayer_NM_saleCount": nm.get("saleCount"),
        "topPrice": card_detail.get("topPrice"),
        "totalSaleCount": card_detail.get("totalSaleCount"),
        "hasGraded": card_detail.get("hasGraded"),
        "lastUpdated": card_detail.get("lastUpdated"),
        "tier": "NEAR_MINT",
        "source": "tcgplayer",
    }


def update_all_prices():
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT id, name, poketrace_id, poketrace_history, image_url
        FROM products
        WHERE poketrace_id IS NOT NULL AND poketrace_id != ''
    """)
    cards = cur.fetchall()

    print(f"[{datetime.now().isoformat()}] Updating {len(cards)} cards via PokeTrace...")
    updated = 0
    failed = 0
    new_points_total = 0

    for card in cards:
        try:
            detail = fetch_card_detail(card["poketrace_id"])
            if not detail:
                print(f"  ✗ {card['name']}: card detail fetch failed")
                failed += 1
                continue

            prices = (detail.get("prices") or {}).get("tcgplayer") or {}
            nm = prices.get("NEAR_MINT") or {}
            current_price = nm.get("avg")

            new_history = fetch_recent_history(card["poketrace_id"], period="all")

            existing_count = 0
            if card.get("poketrace_history"):
                raw = card["poketrace_history"]
                existing = json.loads(raw) if isinstance(raw, str) else raw
                existing_count = len(existing)

            merged = merge_history(card.get("poketrace_history"), new_history)
            added = len(merged) - existing_count
            new_points_total += max(added, 0)

            stats = build_stats(detail)
            new_image = detail.get("image") or ""

                                                                   
            cur.execute(
                """UPDATE products
                   SET poketrace_history = %s,
                       poketrace_stats = %s,
                       image_url = COALESCE(NULLIF(image_url, ''), %s)
                   WHERE id = %s""",
                (json.dumps(merged), json.dumps(stats), new_image, card["id"])
            )

                                                                     
            if current_price:
                cur.execute(
                    "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
                    (card["id"], float(current_price))
                )

            price_str = f"${current_price}" if current_price else "no price"
            print(f"  ✓ {card['name']}: {price_str} (history: {len(merged)} pts, +{added} new)")
            updated += 1
        except Exception as e:
            print(f"  ✗ {card['name']}: {e}")
            failed += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone. Updated: {updated}, Failed: {failed}, New history points: {new_points_total}")


if __name__ == "__main__":
    update_all_prices()