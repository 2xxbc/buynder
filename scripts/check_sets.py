"""READ-ONLY: compare PokeTrace's real set list with our database's tracked_sets and market_cards.

Why: our tracked_sets slugs were loaded once from PokeTrace. PokeTrace has since renamed at least one set
(team-magma-vs-team-aqua -> ex-team-magma-vs-team-aqua), so the nightly sweep asks for an old slug, gets
3 cards instead of 120, and the rest of the set's market_cards rows stop updating.

What it does:
  - PokeTrace: GET /v1/sets, 100 per page (about 5 requests in total). Nothing else.
  - Database: SELECT only, inside a READ ONLY transaction (MySQL refuses any write in it).
  - Reads POKETRACE_API_KEY and DB_* from .env itself; never prints them.
Run:  ~/pokemarket/venv/bin/python scripts/check_sets.py
Writes set_check.json next to this script and prints a summary.
"""
import json, os, sys, time
import requests
import mysql.connector
from dotenv import load_dotenv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.expanduser("~/pokemarket/.env"))
KEY = os.getenv("POKETRACE_API_KEY")
if not KEY:
    sys.exit("POKETRACE_API_KEY not found")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "set_check.json")

# 1. PokeTrace's sets (same call as load_all_sets.py)
pt_sets, cursor_token, requests_used, remaining = [], None, 0, None
while True:
    params = {"game": "pokemon", "limit": 100}
    if cursor_token:
        params["cursor"] = cursor_token
    r = requests.get("https://api.poketrace.com/v1/sets", headers={"X-API-Key": KEY}, params=params, timeout=60)
    requests_used += 1
    remaining = r.headers.get("x-ratelimit-remaining")
    if r.status_code != 200:
        sys.exit(f"PokeTrace /sets returned {r.status_code}")
    body = r.json()
    pt_sets += body.get("data", []) or []
    p = body.get("pagination") or {}
    if not (p.get("hasMore") and p.get("nextCursor")) or requests_used >= 20:
        break
    cursor_token = p["nextCursor"]
    time.sleep(0.3)

# 2. Our database, read-only
conn = mysql.connector.connect(host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER"),
                               password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME", "pokemarket"))
cur = conn.cursor(dictionary=True)
cur.execute("START TRANSACTION READ ONLY")
cur.execute("SHOW CREATE TABLE tracked_sets")
schema = {"tracked_sets": list(cur.fetchone().values())[1]}
cur.execute("SHOW CREATE TABLE market_cards")
schema["market_cards"] = list(cur.fetchone().values())[1]
cur.execute("SELECT * FROM tracked_sets")
ours = cur.fetchall()
cur.execute("""SELECT set_slug, COUNT(*) AS cards, MIN(last_synced) AS oldest, MAX(last_synced) AS newest,
                      SUM(last_synced < NOW() - INTERVAL 3 DAY) AS stale_3d
               FROM market_cards GROUP BY set_slug""")
mc = {r["set_slug"]: r for r in cur.fetchall()}
cur.execute("""SELECT COUNT(*) AS n FROM market_cards WHERE last_synced < NOW() - INTERVAL 3 DAY
                 AND avg1d IS NOT NULL AND avg30d >= 10 AND sale_count >= 50""")
stale_in_movers = cur.fetchone()["n"]
cur.execute("SELECT NOW() AS now")
db_now = cur.fetchone()["now"]
cur.execute("ROLLBACK")
cur.close()
conn.close()

# 3. Compare
norm = lambda s: " ".join((s or "").lower().replace("&", "and").replace("-", " ").split())
pt_by_slug = {s["slug"]: s for s in pt_sets}
pt_by_name = {}
for s in pt_sets:
    pt_by_name.setdefault(norm(s.get("name")), []).append(s["slug"])
ours_by_slug = {s["slug"]: s for s in ours}

renamed, gone, new, same = [], [], [], []
for o in ours:
    if o["slug"] in pt_by_slug:
        same.append(o["slug"])
        continue
    cand = [x for x in pt_by_name.get(norm(o.get("name")), []) if x not in ours_by_slug]
    row = {"our_slug": o["slug"], "name": o.get("name"), "active": o.get("active"),
           "market_cards": (mc.get(o["slug"]) or {}).get("cards", 0),
           "newest_sync": str((mc.get(o["slug"]) or {}).get("newest"))}
    (renamed if cand else gone).append({**row, "poketrace_slug": cand})
taken = {x for r in renamed for x in r["poketrace_slug"]}
for s in pt_sets:
    if s["slug"] not in ours_by_slug and s["slug"] not in taken and s.get("cardCount"):
        new.append({"slug": s["slug"], "name": s.get("name"), "cardCount": s.get("cardCount"),
                    "releaseDate": s.get("releaseDate")})

# Sweep cost: one request per 20 cards per set
cost = lambda slugs: sum(-(-(pt_by_slug[x].get("cardCount") or 0) // 20) for x in slugs if x in pt_by_slug)
summary = {
    "db_now": str(db_now), "poketrace_requests_used": requests_used, "poketrace_remaining": remaining,
    "poketrace_sets": len(pt_sets), "our_sets": len(ours), "same_slug": len(same),
    "renamed": renamed, "gone_from_poketrace": gone, "new_in_poketrace": new,
    "stale_rows_shown_on_movers": stale_in_movers,
    "first_sweep_cost_renamed_and_new": cost([x for r in renamed for x in r["poketrace_slug"]] + [n["slug"] for n in new]),
    "nightly_requests_saved_by_dropping_dead_slugs": len(renamed) + len(gone),
    "poketrace_set_fields": sorted(pt_sets[0].keys()) if pt_sets else [],
    "schema": schema,
    "market_cards_by_slug": {k: {kk: str(vv) for kk, vv in v.items()} for k, v in mc.items()},
}
with open(OUT, "w") as f:
    json.dump(summary, f, indent=1, default=str)

print(f"PokeTrace sets: {len(pt_sets)} | ours: {len(ours)} | same slug: {len(same)}")
print(f"Renamed (our old slug -> PokeTrace's): {len(renamed)}")
for r in renamed[:25]:
    print(f"   {r['our_slug']:40} -> {', '.join(r['poketrace_slug'])}   ({r['market_cards']} rows, newest sync {r['newest_sync']})")
print(f"Gone from PokeTrace (no name match): {len(gone)}")
for g in gone[:15]:
    print(f"   {g['our_slug']:40} {g['name']}  ({g['market_cards']} rows)")
print(f"New in PokeTrace, not tracked: {len(new)}  (first sweep about {cost([n['slug'] for n in new])} requests)")
for n in sorted(new, key=lambda n: str(n.get('releaseDate')), reverse=True)[:15]:
    print(f"   {n['slug']:40} {n['name']}  {n['cardCount']} cards  released {n.get('releaseDate')}")
print(f"market_cards rows Movers can show that weren't synced in 3+ days: {stale_in_movers}")
print(f"\nSaved: {OUT} | PokeTrace requests used: {requests_used} | left today: {remaining}")
