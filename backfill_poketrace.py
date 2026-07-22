"""
One-time backfill: look up each existing card on PokeTrace by name + set,
then populate poketrace_id, poketrace_history (period=all), and poketrace_stats.

Runs in PREVIEW mode by default — won't write to the database until you re-run
with `--apply`.

Usage:
    python backfill_poketrace.py           # preview matches, no DB changes
    python backfill_poketrace.py --apply   # actually update the database
"""
import os
import sys
import json
import time
import mysql.connector
import requests
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
    print("ERROR: POKETRACE_API_KEY not in .env")
    sys.exit(1)

APPLY = "--apply" in sys.argv
headers = {"X-API-Key": API_KEY}


def call(path, params=None):
    time.sleep(2.5)                                    
    return requests.get(f"{BASE}{path}", headers=headers, params=params, timeout=15)


def normalize_set_name(name):
    """Normalize set names for comparison. Strips prefixes like 'ME01:', 'SV:', etc."""
    if not name:
        return ""
    import re
    n = re.sub(r'^[A-Z]+\d*:\s*', '', name)
    return n.lower().strip()


def normalize_number(num):
    """Strip leading zeros and only keep the part before the slash."""
    if not num:
        return ""
    n = num.split("/")[0].strip()
    return n.lstrip("0") or n


def find_poketrace_match(name, set_name, card_number):
    """
    Search PokeTrace and pick the best match by set + card number.
    Returns the full card dict from PokeTrace, or None.
    """
                                                                              
    search_name = name.split(" - ")[0].strip()
    target_set = normalize_set_name(set_name)
    target_num = normalize_number(card_number)

                                                            
    query = f"{search_name} {target_num}" if target_num else search_name
    r = call("/cards", params={"search": query, "market": "US", "limit": 20})
    if not r.ok:
        print(f"  Search failed: {r.status_code} {r.text[:200]}")
        return None
    
    candidates = r.json().get("data", []) or []
    if not candidates:
        return None

                          
    best = None
    best_score = -1
    for c in candidates:
        score = 0
        c_set = normalize_set_name((c.get("set") or {}).get("name", ""))
        c_num = normalize_number(c.get("cardNumber", ""))

        if c_set == target_set:
            score += 10
        elif target_set and (target_set in c_set or c_set in target_set):
            score += 5

        if target_num and c_num == target_num:
            score += 10

        if score > best_score:
            best_score = score
            best = c

    return best if best_score >= 5 else None                           


def fetch_full_history(poketrace_id):
    """Get period=all, up to 365 daily points."""
    r = call(f"/cards/{poketrace_id}/prices/NEAR_MINT/history", params={"period": "all", "limit": 365})
    if not r.ok:
        return []
    return r.json().get("data", []) or []


def extract_stats(card_detail):
    """Build the stats dict from the card detail response."""
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


def main():
    mode = "APPLY (writing to DB)" if APPLY else "PREVIEW (no DB changes)"
    print(f"\n{'=' * 70}")
    print(f"  Backfill mode: {mode}")
    print(f"{'=' * 70}\n")

    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

                                                          
    cur.execute("""
        SELECT id, name, set_name, card_number
        FROM products
        WHERE poketrace_id IS NULL
        ORDER BY id
    """)
    cards = cur.fetchall()
    print(f"Found {len(cards)} cards to backfill.\n")

    matched = 0
    skipped = 0

    for card in cards:
        print(f"[{card['id']}] {card['name']} ({card['set_name']}) #{card['card_number']}")
        match = find_poketrace_match(card["name"], card["set_name"], card["card_number"])
        if not match:
            print(f"  ✗ No confident match found on PokeTrace. Skipping.\n")
            skipped += 1
            continue

        pt_id = match["id"]
        pt_set = (match.get("set") or {}).get("name")
        pt_num = match.get("cardNumber")
        print(f"  ✓ Matched: {pt_id}")
        print(f"    Name: {match.get('name')}")
        print(f"    Set:  {pt_set}")
        print(f"    Num:  {pt_num}")

                                                                    
        r = call(f"/cards/{pt_id}")
        if not r.ok:
            print(f"  ✗ Detail fetch failed: {r.status_code}. Skipping.\n")
            skipped += 1
            continue
        detail = r.json().get("data") or {}

        history = fetch_full_history(pt_id)
        stats = extract_stats(detail)
        image_url = detail.get("image") or ""

        print(f"  ✓ History: {len(history)} points")
        print(f"  ✓ Image: {'yes' if image_url else 'no'}")

        if APPLY:
            cur.execute(
                """UPDATE products
                   SET poketrace_id = %s,
                       poketrace_history = %s,
                       poketrace_stats = %s,
                       image_url = COALESCE(NULLIF(image_url, ''), %s)
                   WHERE id = %s""",
                (pt_id, json.dumps(history), json.dumps(stats), image_url, card["id"])
            )
            print(f"  ✓ Database updated.")
        else:
            print(f"  (PREVIEW: not writing to DB)")

        matched += 1
        print()

    if APPLY:
        conn.commit()
        print(f"{'=' * 70}")
        print(f"  DONE. Matched: {matched}, Skipped: {skipped}")
        print(f"{'=' * 70}")
    else:
        print(f"{'=' * 70}")
        print(f"  PREVIEW DONE. Would match: {matched}, Skip: {skipped}")
        print(f"  Re-run with --apply to actually update the database.")
        print(f"{'=' * 70}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()