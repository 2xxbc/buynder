"""HEAD-check every card image and record which ones 404."""
import os, sys, time
import requests
import mysql.connector
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "pokemarket"),
}

RANKED_ONLY = "--all" not in sys.argv
WORKERS = 20

session = requests.Session()

def check(row):
    """Returns (poketrace_id, ok) — ok is 1 if the image loads, 0 if not."""
    try:
        r = session.head(row["image_url"], timeout=10, allow_redirects=True)
        return (row["poketrace_id"], 1 if r.status_code == 200 else 0)
    except Exception:
        return (row["poketrace_id"], 0)

def main():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    where = "WHERE image_url IS NOT NULL AND image_url != ''"
    if RANKED_ONLY:
        where += " AND avg30d >= 10 AND sale_count >= 50"

    cursor.execute(f"SELECT poketrace_id, image_url FROM market_cards {where}")
    rows = cursor.fetchall()
    total = len(rows)
    scope = "ranked cards only" if RANKED_ONLY else "ALL cards"
    print(f"Checking {total} images ({scope}) with {WORKERS} threads...\n")

    start = time.time()
    results = []
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for pid, ok in pool.map(check, rows):
            results.append((ok, pid))
            done += 1
            if done % 250 == 0:
                rate = done / (time.time() - start)
                left = (total - done) / rate if rate else 0
                print(f"  {done}/{total}  ({rate:.0f}/sec, ~{left/60:.1f} min left)")

    print("\nSaving results...")
    write = conn.cursor()
    for i in range(0, len(results), 500):
        chunk = results[i:i+500]
        write.executemany(
            "UPDATE market_cards SET image_ok = %s, image_checked = NOW() WHERE poketrace_id = %s",
            chunk
        )
        conn.commit()

    broken = sum(1 for ok, _ in results if ok == 0)
    pct = (broken / total * 100) if total else 0
    print(f"\nDone in {(time.time()-start)/60:.1f} min.")
    print(f"{broken} broken out of {total} ({pct:.1f}%)")

    write.close()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
