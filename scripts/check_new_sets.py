"""READ-ONLY: look inside every set PokeTrace has that we don't track, so you can pick which to add.

For each untracked set it prints the first 20 cards (names, numbers, the set the cards say they're in) and how many
of them we ALREADY have in market_cards, matched by PokeTrace card ID or by name + card number.
Many matches = the set repeats cards we track under another slug (adding it would sweep them twice).

What it does:
  - PokeTrace: GET /v1/sets (about 5 requests), then ONE page of /v1/cards per untracked set (about 24). ~29 in total.
  - Database: SELECT only, inside a READ ONLY transaction (MySQL refuses any write in it).
  - Reads POKETRACE_API_KEY and DB_* from .env itself; never prints them.
Run:  ~/pokemarket/venv/bin/python scripts/check_new_sets.py
Writes new_sets_check.json next to this script.
"""
import json, os, sys, time
import requests
import mysql.connector
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/pokemarket/.env"))
KEY = os.getenv("POKETRACE_API_KEY")
if not KEY:
    sys.exit("POKETRACE_API_KEY not found")
H = {"X-API-Key": KEY}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "new_sets_check.json")
MAX_REQUESTS = 60  # hard stop, far under the daily budget
used, remaining = 0, None


def get(path, params):
    global used, remaining
    if used >= MAX_REQUESTS:
        sys.exit(f"Stopped at {used} PokeTrace requests (limit {MAX_REQUESTS}).")
    r = requests.get("https://api.poketrace.com/v1" + path, headers=H, params=params, timeout=60)
    used += 1
    remaining = r.headers.get("x-ratelimit-remaining")
    time.sleep(0.3)
    return r.status_code, (r.json() if r.status_code == 200 else {})


# 1. PokeTrace's sets with cards (same call as load_all_sets.py)
theirs, token = {}, None
while True:
    status, body = get("/sets", {"game": "pokemon", "limit": 100, **({"cursor": token} if token else {})})
    if status != 200:
        sys.exit(f"PokeTrace /sets returned {status}")
    for s in body.get("data", []) or []:
        if s.get("cardCount"):
            theirs[s["slug"]] = s
    p = body.get("pagination") or {}
    if not (p.get("hasMore") and p.get("nextCursor")):
        break
    token = p["nextCursor"]

# 2. Our database, read-only
conn = mysql.connector.connect(host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER"),
                               password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME", "pokemarket"))
cur = conn.cursor(dictionary=True)
cur.execute("START TRANSACTION READ ONLY")
cur.execute("SELECT slug FROM tracked_sets")
ours = {r["slug"] for r in cur.fetchall()}
cur.execute("SELECT poketrace_id, LOWER(name) AS name, card_number, set_slug FROM market_cards")
by_id, by_name_num = {}, {}
for r in cur.fetchall():
    by_id[r["poketrace_id"]] = r["set_slug"]
    by_name_num[(r["name"], r["card_number"])] = r["set_slug"]
cur.execute("ROLLBACK")
cur.close()
conn.close()

# 3. One page of each untracked set
report = []
for slug in sorted(s for s in theirs if s not in ours):
    status, body = get("/cards", {"set": slug, "market": "US", "limit": 20})
    cards = body.get("data", []) or []
    same_id = [by_id[c.get("id")] for c in cards if c.get("id") in by_id]
    same_card = [by_name_num[k] for c in cards
                 if (k := ((c.get("name") or "").lower(), c.get("cardNumber"))) in by_name_num]
    report.append({
        "slug": slug, "name": theirs[slug].get("name"), "cardCount": theirs[slug].get("cardCount"), "status": status,
        "page_cards": len(cards),
        "cards_say_set": sorted({(c.get("set") or {}).get("slug") for c in cards} - {None}),
        "japanese_named": sum("japanese" in (c.get("name") or "").lower() for c in cards),
        "already_tracked_same_id": len(same_id),
        "already_tracked_same_name_number": len(same_card),
        "our_sets_with_those_cards": sorted(set(same_id + same_card)),
        "sample": [f"{c.get('name')} {c.get('cardNumber')} ({c.get('rarity')})" for c in cards[:6]],
    })

with open(OUT, "w") as f:
    json.dump({"poketrace_requests_used": used, "poketrace_remaining": remaining, "sets": report}, f, indent=1)

for s in report:
    dup = max(s["already_tracked_same_id"], s["already_tracked_same_name_number"])
    flag = "DUPLICATE?" if s["page_cards"] and dup >= s["page_cards"] / 2 else ""
    print(f"\n{s['slug']}  |  {s['name']}  |  {s['cardCount']} cards  {flag}")
    print(f"   first page: {s['page_cards']} cards, already in market_cards: {s['already_tracked_same_id']} by ID, "
          f"{s['already_tracked_same_name_number']} by name+number {s['our_sets_with_those_cards'] or ''}")
    if s["japanese_named"]:
        print(f"   '(Japanese)' in {s['japanese_named']} card names")
    for line in s["sample"]:
        print("     ", line)
print(f"\nSaved {OUT} | PokeTrace requests used: {used} | left today: {remaining}")
