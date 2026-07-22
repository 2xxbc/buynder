"""Sweep tracked sets from PokeTrace into market_cards for the discovery feed."""
import os
import time
import requests
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POKETRACE_API_KEY")
BASE = "https://api.poketrace.com/v1"
TIMEOUT = 60
MAX_RETRIES = 3

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "pokemarket"),
}


def fetch_page(params, headers):
    """GET /cards with retries. Returns response body dict, or None if it kept failing."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{BASE}/cards", headers=headers, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code}: {r.text[:100]}")
        except requests.exceptions.RequestException as e:
            print(f"    attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}")
        if attempt < MAX_RETRIES:
            time.sleep(3 * attempt)                    
    return None


def nm_prices(card):
    """TCGPlayer NEAR_MINT price block, or None."""
    prices = card.get("prices") or {}
    tcg = prices.get("tcgplayer") or {}
    return tcg.get("NEAR_MINT")


def sweep():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT slug, name FROM tracked_sets WHERE active = 1 AND (last_swept IS NULL OR last_swept < NOW() - INTERVAL 20 HOUR)")
    sets = cursor.fetchall()
    print(f"Sweeping {len(sets)} sets...\n")

    headers = {"X-API-Key": API_KEY}
    total_cards = 0
    total_requests = 0
    failed_pages = 0

    for s in sets:
        slug = s["slug"]
        cursor_token = None
        set_count = 0
        print(f"[{slug}]")

        while True:
            params = {"set": slug, "market": "US", "limit": 20}
            if cursor_token:
                params["cursor"] = cursor_token

            body = fetch_page(params, headers)
            total_requests += 1

            if body is None:
                print(f"    giving up on this page, moving on")
                failed_pages += 1
                break

            cards = body.get("data", []) or []

            for card in cards:
                nm = nm_prices(card)
                if not nm:
                    continue

                cursor.execute("""
                    INSERT INTO market_cards
                      (poketrace_id, name, set_slug, set_name, card_number, rarity, image_url,
                       avg, avg1d, avg7d, avg30d, median7d, sale_count, trend)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      name=VALUES(name), set_name=VALUES(set_name), card_number=VALUES(card_number),
                      rarity=VALUES(rarity), image_url=VALUES(image_url),
                      avg=VALUES(avg), avg1d=VALUES(avg1d), avg7d=VALUES(avg7d),
                      avg30d=VALUES(avg30d), median7d=VALUES(median7d),
                      sale_count=VALUES(sale_count), trend=VALUES(trend)
                """, (
                    card.get("id"),
                    card.get("name"),
                    slug,
                    (card.get("set") or {}).get("name"),
                    card.get("cardNumber"),
                    card.get("rarity"),
                    card.get("image"),
                    nm.get("avg"),
                    nm.get("avg1d"),
                    nm.get("avg7d"),
                    nm.get("avg30d"),
                    nm.get("median7d"),
                    nm.get("saleCount") or 0,
                    nm.get("trend"),
                ))
                set_count += 1
                total_cards += 1

            conn.commit()
            print(f"    page done — {set_count} priced so far")

            pagination = body.get("pagination") or {}
            if pagination.get("hasMore") and pagination.get("nextCursor"):
                cursor_token = pagination["nextCursor"]
                time.sleep(0.5)
            else:
                break

        cursor.execute("UPDATE tracked_sets SET last_swept = NOW() WHERE slug = %s", (slug,))
        conn.commit()
        print(f"  → {set_count} priced cards\n")

    cursor.close()
    conn.close()
    print(f"Done. {total_cards} cards saved, {total_requests} requests, {failed_pages} failed pages.")


if __name__ == "__main__":
    sweep()
