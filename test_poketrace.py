"""
PokeTrace test v3 - figure out pagination on the history endpoint.
The default returns 7 days. We want to find out if free tier supports more.
"""
import os
import time
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POKETRACE_API_KEY")
BASE = "https://api.poketrace.com/v1"
CARD_ID = "019bff77-befa-771d-bab0-f5909f0a78c9"                                       

if not API_KEY:
    print("ERROR: POKETRACE_API_KEY not found in .env")
    exit(1)

headers = {"X-API-Key": API_KEY}


def section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def call(path, params=None):
    time.sleep(3)
    return requests.get(f"{BASE}{path}", headers=headers, params=params, timeout=15)


                                                             
section("TEST 1: Default response (no params) - inspect pagination block")
r = call(f"/cards/{CARD_ID}/prices/NEAR_MINT/history")
print(f"Status: {r.status_code}, Remaining: {r.headers.get('x-ratelimit-remaining')}")
if r.ok:
    body = r.json()
    print(f"Top-level keys: {list(body.keys())}")
    print(f"Pagination block: {json.dumps(body.get('pagination'), indent=2)}")
    print(f"Data length: {len(body.get('data', []))}")
    if body.get('data'):
        first = body['data'][-1]
        last = body['data'][0]
        print(f"Oldest: {first.get('date')}")
        print(f"Newest: {last.get('date')}")

                                             
section("TEST 2: Try params to get MORE data points")
attempts = [
    {"limit": 100},
    {"limit": 365},
    {"days": 90},
    {"days": 365},
    {"pageSize": 100},
    {"perPage": 100},
    {"from": "2025-01-01"},
    {"startDate": "2025-01-01"},
    {"start": "2025-01-01"},
    {"page": 2},
]

best_count = 7
best_params = None
for params in attempts:
    r = call(f"/cards/{CARD_ID}/prices/NEAR_MINT/history", params=params)
    rem = r.headers.get("x-ratelimit-remaining")
    if r.status_code == 200:
        body = r.json()
        count = len(body.get("data", []))
        pag = body.get("pagination", {})
        data = body.get("data", [])
        oldest = data[-1].get("date") if data else "?"
        newest = data[0].get("date") if data else "?"
        marker = ""
        if count > best_count:
            marker = " <<< MORE DATA!"
            best_count = count
            best_params = params
        print(f"  params={params} -> {count} points ({oldest} to {newest}) pagination={pag} rem={rem}{marker}")
    else:
        try:
            err = r.json()
            print(f"  params={params} -> {r.status_code} {err.get('error', err)} rem={rem}")
        except Exception:
            print(f"  params={params} -> {r.status_code} {r.text[:120]} rem={rem}")

                   
section("VERDICT")
if best_params:
    print(f"YES! Best result: {best_count} points with params: {best_params}")
else:
    print(f"Free tier is capped at {best_count} days. No params unlocked more.")
print(f"Requests remaining today: {rem}")