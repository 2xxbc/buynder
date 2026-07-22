"""Load every English Pokemon set into tracked_sets."""
import os, time, requests, mysql.connector
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("POKETRACE_API_KEY")

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "pokemarket"),
}

conn = mysql.connector.connect(**db_config)
cursor = conn.cursor()
headers = {"X-API-Key": API_KEY}
cursor_token = None
total = 0
cards_total = 0

while True:
    params = {"game": "pokemon", "limit": 100}
    if cursor_token:
        params["cursor"] = cursor_token
    r = requests.get("https://api.poketrace.com/v1/sets", headers=headers, params=params, timeout=60)
    if r.status_code != 200:
        print(f"Failed: {r.status_code}")
        break
    body = r.json()
    for s in body.get("data", []):
        if not s.get("cardCount"):
            continue                   
        cursor.execute(
            "INSERT IGNORE INTO tracked_sets (slug, name) VALUES (%s, %s)",
            (s["slug"], s["name"])
        )
        total += 1
        cards_total += s["cardCount"]
    conn.commit()
    p = body.get("pagination") or {}
    if p.get("hasMore") and p.get("nextCursor"):
        cursor_token = p["nextCursor"]
        time.sleep(0.3)
    else:
        break

cursor.execute("SELECT COUNT(*) FROM tracked_sets WHERE active = 1")
active = cursor.fetchone()[0]
cursor.close()
conn.close()
print(f"\n{total} sets processed, {active} now active.")
print(f"~{cards_total} cards total = ~{cards_total // 20} API requests per sweep.")
