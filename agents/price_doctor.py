#!/usr/bin/env python3
"""price_doctor: find cards whose played conditions are priced ABOVE Near Mint, like Image Doctor does for images.

For each card it asks PokeTrace for the card detail (1 request: every condition, both sources, saleCount and
lastUpdated) and, for each source separately (TCGplayer vs TCGplayer, eBay vs eBay), flags LP / MP / HP / Damaged
priced above Near Mint by at least 5% AND at least $1. Each flag gets a likely cause:
  stale NM    Near Mint's lastUpdated is 30+ days old (an old price carried forward)
  thin data   Near Mint or the condition has fewer than 10 sales
  unclear     neither
Every card detail it fetches is saved in data/price_doctor_cards/<id>.json, so a new threshold can be applied later
with --from-saved: 0 PokeTrace requests.
Results: data/mispriced_cards.csv (every flag, worst first, with first_seen / last_checked), a Discord summary with
the CSV attached, data/price_doctor_summary.json (read by the Monday PokeTrace draft), and a run log for the Pi board.

Which cards, and the PokeTrace budget (about 10,000 requests a day; the sweep uses ~2,700):
  - at most --max-requests per run (default 3,000)
  - it stops early when fewer than --reserve (2,000) would be left today
  - order: cards someone saved (watchlist/collection), then the TOP_NIGHTLY most-sold cards, then a rotating slice
    of the rest, so every card gets checked every few weeks
  - progress is saved every 25 cards: a run that stopped (budget, rate limit, Ctrl-C, crash) carries on where it
    left off next time, unless --fresh
It never sends anything to PokeTrace except these read requests.

    venv/bin/python agents/price_doctor.py                       # the real run (also cron, after the sweep)
    venv/bin/python agents/price_doctor.py --dry-run --max-requests 20     # 20 real cards, nothing written or sent
    venv/bin/python agents/price_doctor.py --from-saved          # re-judge every saved card detail, 0 requests
    venv/bin/python agents/price_doctor.py --dry-run --from-file a.json b.json   # any saved card details, no network
"""
import argparse
import csv
import io
import json
import os
import re
import signal
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                                         # noqa: E402
from common import db_connect, fit_discord, load_env, redact, send_discord   # noqa: E402
from runlog import Run, data_dir, write_json_atomic                    # noqa: E402

AGENT = "price_doctor"
PLAYED = ["LIGHTLY_PLAYED", "MODERATELY_PLAYED", "HEAVILY_PLAYED", "DAMAGED"]
SHORT = {"LIGHTLY_PLAYED": "LP", "MODERATELY_PLAYED": "MP", "HEAVILY_PLAYED": "HP", "DAMAGED": "Damaged"}
SOURCES = {"tcgplayer": "TCGplayer", "ebay": "eBay"}
MIN_PCT, MIN_DOLLARS = 5.0, 1.0        # flag only when BOTH: at least 5% and at least $1 above Near Mint
STALE_DAYS, THIN_SALES = 30, 10
TOP_NIGHTLY = 1000                     # the most-sold cards are checked every run
SAVE_EVERY = 25
PAUSE = 1.2                            # seconds between requests (the sweep runs at about 1 request per 1.5 s)
CSV_COLUMNS = ["poketrace_id", "name", "set", "number", "source", "nm_price", "nm_last_updated", "nm_sale_count",
               "condition", "price", "last_updated", "sale_count", "pct_above_nm", "likely_cause",
               "first_seen", "last_checked"]
STOP = {"now": False}


# ---------------------------------------------------------------- the rule (plain functions, tested on saved data)

def likely_cause(nm, p, today):
    nm_day = (nm.get("lastUpdated") or "")[:10]
    if not nm_day or nm_day < (today - timedelta(days=STALE_DAYS)).isoformat():
        return "stale NM"
    if (nm.get("saleCount") or 0) < THIN_SALES or (p.get("saleCount") or 0) < THIN_SALES:
        return "thin data"
    return "unclear"


def flags_for(card, today):
    """Every played condition priced >=MIN_PCT% and >=MIN_DOLLARS above Near Mint on the same source, as CSV-ready dicts."""
    out = []
    for source, block in (card.get("prices") or {}).items():
        nm = (block or {}).get("NEAR_MINT") or {}
        if not nm.get("avg"):
            continue
        for cond in PLAYED:
            p = (block or {}).get(cond) or {}
            if p.get("avg") is None:
                continue
            diff = p["avg"] - nm["avg"]
            pct = diff / nm["avg"] * 100
            if pct >= MIN_PCT and diff >= MIN_DOLLARS:
                out.append({
                    "poketrace_id": card.get("id"), "name": card.get("name"), "set": (card.get("set") or {}).get("name"),
                    "number": card.get("cardNumber"), "source": SOURCES.get(source, source),
                    "nm_price": round(nm["avg"], 2), "nm_last_updated": (nm.get("lastUpdated") or "")[:10],
                    "nm_sale_count": nm.get("saleCount"), "condition": SHORT[cond], "price": round(p["avg"], 2),
                    "last_updated": (p.get("lastUpdated") or "")[:10], "sale_count": p.get("saleCount"),
                    "pct_above_nm": round(pct, 1), "likely_cause": likely_cause(nm, p, today)})
    return out


def flag_key(f):
    return f"{f['poketrace_id']}|{f['source']}|{f['condition']}"


def merge(state, card_id, new_flags, today):
    """Replace this card's flags with today's, keeping first_seen for flags that were already there."""
    old = {k: v for k, v in state["flags"].items() if k.startswith(f"{card_id}|")}
    for k in old:
        del state["flags"][k]
    for f in new_flags:
        k = flag_key(f)
        state["flags"][k] = {**f, "first_seen": (old.get(k) or {}).get("first_seen") or today.isoformat(),
                             "last_checked": today.isoformat()}


def csv_bytes(flags):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    w.writeheader()
    for f in sorted(flags.values(), key=lambda f: -f["pct_above_nm"]):
        w.writerow({k: f.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue().encode()


def summary(state):
    flags = list(state["flags"].values())
    return {"rows": len(flags), "cards": len({f["poketrace_id"] for f in flags}),
            "cards_checked": len(state["checked"]),
            "by_cause": dict(Counter(f["likely_cause"] for f in flags)),
            "by_source": dict(Counter(f["source"] for f in flags)),
            "stale_nm_cards": len({f["poketrace_id"] for f in flags if f["likely_cause"] == "stale NM"})}


# ---------------------------------------------------------------- state (resume) and which cards

def load_state(folder):
    try:
        with open(os.path.join(folder, "price_doctor_state.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"flags": {}, "checked": {}, "rotation": 0, "pending": [], "pending_from": None}


def save_state(folder, state):
    write_json_atomic(os.path.join(folder, "price_doctor_state.json"), state)


def plan(cur, state, max_requests):
    """The ids to check this run: an unfinished run's leftovers first, else saved cards, the most-sold, a rotating slice."""
    if state.get("pending"):
        return state["pending"][:max_requests], f"carrying on with {len(state['pending']):,} cards an earlier run didn't reach"
    cur.execute("START TRANSACTION READ ONLY")
    cur.execute("SELECT DISTINCT poketrace_id FROM products WHERE poketrace_id IS NOT NULL AND poketrace_id != ''")
    saved = [r["poketrace_id"] for r in cur.fetchall()]
    cur.execute("SELECT poketrace_id FROM market_cards WHERE last_synced >= NOW() - INTERVAL 7 DAY "
                "AND name NOT LIKE %s ORDER BY sale_count DESC, poketrace_id", ("%(Japanese)%",))
    popular = [r["poketrace_id"] for r in cur.fetchall()]
    cur.execute("ROLLBACK")
    order, seen = [], set()
    for pid in saved + popular[:TOP_NIGHTLY]:
        if pid not in seen:
            seen.add(pid)
            order.append(pid)
    rest = [p for p in popular[TOP_NIGHTLY:] if p not in seen]
    room = max(0, max_requests - len(order))
    start = state.get("rotation", 0) % len(rest) if rest else 0
    slice_ = (rest[start:] + rest[:start])[:room]
    state["rotation"] = (start + len(slice_)) % len(rest) if rest else 0
    return (order + slice_)[:max_requests], f"{len(saved)} saved, {min(len(popular), TOP_NIGHTLY)} most-sold, {len(slice_)} rotating"


class PokeTrace:
    def __init__(self, key, pause=PAUSE, sleep=time.sleep, get=requests.get):
        self.key, self.pause, self.sleep, self.get = key, pause, sleep, get
        self.used, self.remaining = 0, None

    def card(self, pid):
        """(card dict | None, problem | None). problem 'rate_limited' means: stop this run."""
        for attempt in range(3):
            try:
                r = self.get(f"https://api.poketrace.com/v1/cards/{pid}", headers={"X-API-Key": self.key}, timeout=20)
            except requests.RequestException as e:
                self.sleep(5)
                if attempt == 2:
                    return None, type(e).__name__
                continue
            self.used += 1
            rem = r.headers.get("x-ratelimit-remaining")
            if rem and str(rem).isdigit():
                self.remaining = int(rem)
            if r.status_code == 429:
                self.pause += 0.5                     # slow down for the rest of the run
                self.sleep(min(float(r.headers.get("Retry-After") or 30), 120))
                continue
            self.sleep(self.pause)
            if r.status_code == 200:
                return (r.json() or {}).get("data"), None
            return None, f"HTTP {r.status_code}"
        return None, "rate_limited"


# ---------------------------------------------------------------- the message

def n_of(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def message(s, stopped, checked_now, today):
    when = f"{today:%a %b} {today.day}"
    lines = [f"**Price doctor, {when}**",
             f"{n_of(s['cards'], 'card')} {'has' if s['cards'] == 1 else 'have'} a played condition priced at least {MIN_PCT:g}% "
             f"and ${MIN_DOLLARS:g} above Near Mint ({n_of(s['rows'], 'price')}). Checked {n_of(checked_now, 'card')} this run, "
             f"{s['cards_checked']:,} so far."]
    if s["rows"]:
        lines.append("Likely cause: " + ", ".join(f"{k} {v:,}" for k, v in sorted(s["by_cause"].items(), key=lambda kv: -kv[1]))
                     + ". Source: " + ", ".join(f"{k} {v:,}" for k, v in sorted(s["by_source"].items(), key=lambda kv: -kv[1])) + ".")
    if stopped:
        lines.append(f"Stopped early: {stopped}. The next run carries on where this one left off.")
    return lines


def top_lines(flags, n=10):
    worst = sorted(flags.values(), key=lambda f: -f["pct_above_nm"])[:n]
    out = [f"**Worst {len(worst)}**"] if worst else []
    for f in worst:
        num = f" {f['number']}" if f.get("number") else ""
        out.append(f"• {f['name']}{num} ({f['set']}): {f['source']} {f['condition']} ${f['price']:,.2f} vs NM ${f['nm_price']:,.2f} "
                   f"(+{f['pct_above_nm']:g}%, {f['likely_cause']})")
    return out


# ---------------------------------------------------------------- main

CARDS_DIR = "price_doctor_cards"


def save_card(folder, pid, card, day):
    """Keep the fetched detail, so a later threshold change needs no new requests. One small file per card."""
    name = re.sub(r"[^A-Za-z0-9_-]", "_", str(pid))[:80]
    path = os.path.join(folder, CARDS_DIR)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, f"{name}.json"), "w") as f:
        json.dump({"fetched": day.isoformat(), "data": card}, f)


def load_saved_cards(folder):
    """[(card, the date it was fetched)] for every saved detail."""
    path = os.path.join(folder, CARDS_DIR)
    out = []
    for fn in sorted(os.listdir(path)) if os.path.isdir(path) else []:
        try:
            with open(os.path.join(path, fn)) as f:
                d = json.load(f)
            out.append((d["data"], date.fromisoformat(d["fetched"])))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def read_saved(paths):
    """Card details saved earlier: a PokeTrace response {"data": card}, a bare card, or a list of either."""
    cards = []
    for p in paths:
        with open(p) as f:
            d = json.load(f)
        for item in d if isinstance(d, list) else [d]:
            cards.append(item.get("data", item) if isinstance(item, dict) else item)
    return cards


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="check, but write no CSV/state and send nothing")
    ap.add_argument("--from-file", nargs="+", metavar="JSON", help="use these saved card details instead of PokeTrace (no network, writes nothing)")
    ap.add_argument("--from-saved", action="store_true", help="re-judge every card detail saved by earlier runs: 0 PokeTrace requests")
    ap.add_argument("--max-requests", type=int, default=3000, help="PokeTrace requests this run (default 3,000)")
    ap.add_argument("--reserve", type=int, default=2000, help="stop when fewer than this many would be left today")
    ap.add_argument("--fresh", action="store_true", help="ignore an unfinished earlier run and plan a new one")
    args = ap.parse_args()
    today = date.today()
    folder = data_dir(args.dry_run)
    # systemctl stop / kill (SIGTERM) and a closed terminal (SIGHUP): finish the current card, save, record "stopped"
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: STOP.update(now=True))

    with Run(AGENT, steps=4, dry_run=args.dry_run) as run:
        notes, stopped = [], None
        state = load_state(folder)
        if args.fresh:
            state["pending"] = []

        run.step("Choosing cards")
        offline = bool(args.from_file or args.from_saved)
        fetched_on = {}
        if offline:
            if args.from_file:
                cards = [(c, today) for c in read_saved(args.from_file)]
            else:
                cards = load_saved_cards(data_dir(False))        # always the real runs' saved details
            todo, how = [c.get("id") for c, _ in cards], f"{len(cards)} saved card details, 0 PokeTrace requests"
            by_id = {c.get("id"): c for c, _ in cards}
            fetched_on = {c.get("id"): d for c, d in cards}
        else:
            load_env()
            key = os.getenv("POKETRACE_API_KEY")
            if not key:
                sys.exit("POKETRACE_API_KEY is not set in .env")
            conn = db_connect()
            cur = conn.cursor(dictionary=True)
            todo, how = plan(cur, state, args.max_requests)
            cur.close()
            conn.close()
            pt = PokeTrace(key)
        print(f"[{AGENT}] {len(todo)} cards to check ({how})", flush=True)
        # Anything an unfinished run left beyond this run's cap waits for the next run (offline runs leave it alone)
        pending_before = list(state.get("pending") or [])
        leftover = [p for p in pending_before if p not in set(todo)]
        if not offline:
            state["pending"] = todo + leftover                 # recorded before the first request, so a stop can't lose it

        run.step(f"Checking {len(todo)} cards")
        checked_now, failed = 0, Counter()
        try:
            for i, pid in enumerate(todo):
                if STOP["now"]:
                    stopped = "stopped (kill / terminal closed)"
                    break
                if offline:
                    card, problem = by_id.get(pid), None
                else:
                    if pt.remaining is not None and pt.remaining - 1 < args.reserve:
                        stopped = f"PokeTrace budget: {pt.remaining:,} requests left today (keeping {args.reserve:,})"
                        break
                    card, problem = pt.card(pid)
                    if problem == "rate_limited":
                        stopped = "PokeTrace kept saying 'too many requests'"
                        break
                if problem or not card:
                    failed[problem or "empty"] += 1
                else:
                    day = fetched_on.get(pid, today)              # "stale" is judged as of the day it was fetched
                    merge(state, pid, flags_for(card, day), day)
                    state["checked"][pid] = day.isoformat()
                    checked_now += 1
                    if not offline and not args.dry_run:
                        save_card(folder, pid, card, today)
                if not offline:
                    state["pending"] = todo[i + 1:] + leftover
                if not args.dry_run and not offline and (i + 1) % SAVE_EVERY == 0:
                    save_state(folder, state)
                run.progress(i + 1, len(todo))
                if (i + 1) % 250 == 0:
                    print(f"[{AGENT}]   {i + 1}/{len(todo)} checked, {len(state['flags'])} flagged so far"
                          + (f", {pt.remaining:,} requests left today" if not offline and pt.remaining is not None else ""), flush=True)
        except KeyboardInterrupt:
            stopped = "stopped with Ctrl-C"
        if failed:
            notes.append("lookups that failed: " + ", ".join(f"{k} {v}" for k, v in failed.items()))

        run.step("Writing mispriced_cards.csv")
        s = summary(state)
        s.update(run_at=datetime.now().isoformat(timespec="seconds"), checked_this_run=checked_now,
                 requests=0 if offline else pt.used, stopped=stopped, min_pct=MIN_PCT, min_dollars=MIN_DOLLARS)
        data = csv_bytes(state["flags"])
        if offline:
            state["pending"] = pending_before
        if not args.dry_run and not args.from_file:
            save_state(folder, state)
            with open(os.path.join(folder, "mispriced_cards.csv"), "wb") as f:
                f.write(data)
            write_json_atomic(os.path.join(folder, "price_doctor_summary.json"), s)

        run.step("Messaging you")
        lines = message(s, stopped, checked_now, today) + [""] + top_lines(state["flags"])
        ok, problem = send_discord(fit_discord(lines), files=[("mispriced_cards.csv", data, "text/csv")],
                                   dry_run=args.dry_run or bool(args.from_file))
        if not ok:
            notes.append(problem)
        metrics = {"flagged_cards": s["cards"], "flagged_prices": s["rows"], "checked": checked_now,
                   "stale_nm_cards": s["stale_nm_cards"], "requests": s["requests"]}
        level = "stopped" if stopped else ("warn" if not ok else "ok")
        summary_text = f"{n_of(s['cards'], 'card')} priced above Near Mint ({n_of(s['rows'], 'price')}); checked {checked_now:,}"
        run.finish(level, summary=summary_text, metrics=metrics, notes=[redact(n) for n in notes])
        print(f"[{AGENT}] {level}: {summary_text}" + (f" | stopped: {stopped}" if stopped else ""))


if __name__ == "__main__":
    main()
