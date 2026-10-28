#!/usr/bin/env python3
"""ops_report: the daily 8 AM health and usage report, sent to you on Discord.

Collects facts with plain code (database counts, log files, HTTP checks, disk, backups), compares
them with the last 7 days, and asks Claude only to write a 5-10 line summary that leads with
anything unusual. If that fails, you get the raw numbers instead (and the run is marked "warn").
Counts only: no usernames or emails ever leave the server.

"Urgent" (🚨 at the top) means: the site or API is down, the newest backup is older than 36 hours,
or last night's sweep failed.

Mondays (New York time) add a "PokeTrace data issues" section: a ready-to-edit email DRAFT to PokeTrace support,
attached as poketrace_draft.txt together with broken_images.csv. It's built from agents/poketrace_issues.json and
the CSV, makes no PokeTrace calls, and is never sent to PokeTrace: you send it yourself if you want to.

    venv/bin/python agents/ops_report.py --dry-run            # real data, nothing sent
    venv/bin/python agents/ops_report.py --dry-run --sample   # made-up data, no database, no .env
    venv/bin/python agents/ops_report.py --dry-run --poketrace-draft   # include the Monday draft today
"""
import argparse
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                               # noqa: E402
from common import LLM, db_connect, fit_discord, load_env, redact, send_discord   # noqa: E402
from runlog import REPO, Run, is_local_time, read_runs                       # noqa: E402

AGENT = "ops_report"
URLS = {"site": "https://buyndermarket.com/", "api": "http://localhost:5050/",
        "site_api": "https://buyndermarket.com/api/",        # the path the site itself uses (Caddy -> 5050)
        "public_api": "https://api.buyndermarket.com/"}
BACKUP_MAX_HOURS = 36
SWEEP_MAX_HOURS = 26


# ---------------------------------------------------------------- facts (plain code)

def column_exists(cur, table, column):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema = DATABASE() "
                "AND table_name = %s AND column_name = %s", (table, column))
    return cur.fetchone()["n"] > 0


def count(cur, sql):
    """One COUNT query; None if it fails (e.g. a column this database doesn't have)."""
    try:
        cur.execute(sql)
        return cur.fetchone()["n"]
    except Exception:
        return None


def user_and_usage_facts():
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    users = {"total": count(cur, "SELECT COUNT(*) AS n FROM users")}
    users["new_24h"] = (count(cur, "SELECT COUNT(*) AS n FROM users WHERE created_at >= NOW() - INTERVAL 1 DAY")
                        if column_exists(cur, "users", "created_at") else None)
    users["active_24h"] = (count(cur, "SELECT COUNT(*) AS n FROM users WHERE last_seen >= NOW() - INTERVAL 1 DAY")
                           if column_exists(cur, "users", "last_seen") else None)   # None until migration 002
    day = "NOW() - INTERVAL 1 DAY"
    usage = {
        "cards_saved": count(cur, f"SELECT COUNT(*) AS n FROM products WHERE created_at >= {day}"),
        "collection_adds": count(cur, f"SELECT COUNT(*) AS n FROM collection WHERE date_added >= {day}"),
        "cards_sold": count(cur, f"SELECT COUNT(*) AS n FROM sold WHERE sold_at >= {day}"),
        "trades_logged": count(cur, "SELECT COUNT(*) AS n FROM trades WHERE trade_date >= CURDATE() - INTERVAL 1 DAY"),
        "share_links_opened": count(cur, f"SELECT COUNT(*) AS n FROM share_access WHERE first_opened >= {day}"),
    }
    cur.close()
    conn.close()
    return users, usage


def tail(path, lines=400):
    try:
        with open(path, errors="replace") as f:
            return f.readlines()[-lines:]
    except OSError:
        return []


def sweep_facts():
    """Last night's market sweep (sweep.log) and price update (prices.log)."""
    lines = tail(os.path.join(REPO, "sweep.log"), 100000)   # one night is ~3-4k lines; the log rotates daily
    start_i = max((i for i, l in enumerate(lines) if l.startswith("=== Sweep started")), default=None)
    out = {"status": "missing", "cards": None, "requests": None, "failed_pages": None, "finished": None, "hours_ago": None}
    if start_i is not None:
        run = lines[start_i:]
        for l in run:
            m = re.search(r"Done\. (\d+) cards saved, (\d+) requests, (\d+) failed pages", l)
            if m:
                out.update(cards=int(m[1]), requests=int(m[2]), failed_pages=int(m[3]))
            if l.startswith("=== Sweep finished"):
                out["finished"] = l.replace("=== Sweep finished", "").strip(" =\n")
        crashed = any("Traceback" in l for l in run)
        mtime_hours = (time.time() - os.path.getmtime(os.path.join(REPO, "sweep.log"))) / 3600
        out["hours_ago"] = round(mtime_hours, 1)
        if crashed or out["cards"] is None:
            out["status"] = "failed"
        elif mtime_hours > SWEEP_MAX_HOURS:
            out["status"] = "stale"
        elif out["failed_pages"]:
            out["status"] = "partial"
        else:
            out["status"] = "ok"
    prices = next((l.strip() for l in reversed(tail(os.path.join(REPO, "prices.log"))) if l.startswith("Done.")), None)
    m = re.search(r"Updated: (\d+), Failed: (\d+)", prices or "")
    out["price_update"] = {"updated": int(m[1]), "failed": int(m[2])} if m else None
    return out


def http_status(url):
    try:
        return requests.get(url, timeout=10).status_code
    except requests.RequestException:
        return None


def journal_counts():
    """Counts from the API's log in the last 24h: server errors, failed logins, rate-limit blocks.
    (Failed logins / rate limits are logged since the ops-agents change to app.py.)"""
    try:
        out = subprocess.run(["journalctl", "-u", "buynder-api", "--since", "24 hours ago", "-o", "cat", "--no-pager"],
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return {"errors": None, "failed_logins": None, "rate_limited": None}
    return {"errors": len(re.findall(r"ERROR in app", out)),
            "failed_logins": len(re.findall(r"login failed", out)),
            "rate_limited": len(re.findall(r"rate limit hit", out))}


def backup_facts():
    """Newest nightly backup: how old and how big (only file dates/sizes are read)."""
    files = glob.glob(os.path.join(REPO, "backups", "pokemarket-*.sql.gz"))
    if not files:
        return {"newest": None, "age_hours": None, "size_mb": None}
    newest = max(files, key=os.path.getmtime)
    return {"newest": os.path.basename(newest),
            "age_hours": round((time.time() - os.path.getmtime(newest)) / 3600, 1),
            "size_mb": round(os.path.getsize(newest) / 1e6, 1)}


def health_facts():
    disk = shutil.disk_usage("/")
    return {
        "http": {name: http_status(url) for name, url in URLS.items()},
        "disk_used_pct": round(disk.used / disk.total * 100, 1),
        "disk_free_gb": round(disk.free / 1e9, 1),
        "backup": backup_facts(),
        **journal_counts(),
    }


def sample_facts():
    """--sample: made-up numbers, with a quiet failed-login spike to show the 'unusual' logic."""
    users = {"total": 14, "new_24h": 1, "active_24h": None}
    usage = {"cards_saved": 6, "collection_adds": 3, "cards_sold": 0, "trades_logged": 1, "share_links_opened": 2}
    sweep = {"status": "ok", "cards": 43234, "requests": 2708, "failed_pages": 0, "finished": "Fri Oct 23 04:02:28 AM UTC 2026",
             "hours_ago": 4.2, "price_update": {"updated": 42, "failed": 0}}
    health = {"http": {"site": 200, "api": 200, "site_api": 200, "public_api": 200}, "disk_used_pct": 61.3, "disk_free_gb": 180.4,
              "backup": {"newest": "pokemarket-2026-10-23.sql.gz", "age_hours": 14.5, "size_mb": 38.2},
              "errors": 2, "failed_logins": 19, "rate_limited": 4}
    return users, usage, sweep, health


# ---------------------------------------------------------------- compare + flags

def flat(metrics):
    """{'health': {'errors': 2}} -> {'health.errors': 2}, numbers only."""
    out = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            out.update({f"{k}.{kk}": vv for kk, vv in flat(v).items()})
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out


WATCH = {  # metrics worth flagging when they jump, with a human name
    "health.errors": "server errors", "health.failed_logins": "failed logins", "health.rate_limited": "rate-limit blocks",
    "users.new_24h": "new users", "users.active_24h": "active users", "usage.cards_saved": "cards saved",
    "usage.collection_adds": "collection adds", "sweep.failed_pages": "sweep failed pages",
}


def unusual(now, history):
    """Compare today with the average of the last 7 days. 'Unusual' = at least 3 more than usual and
    at least double, or dropped to 0 from an average of 3+. Needs 3+ past days to say anything."""
    if len(history) < 3:
        return [], f"only {len(history)} earlier report(s), so no 7-day comparison yet"
    flags = []
    for key, label in WATCH.items():
        today = now.get(key)
        past = [h[key] for h in history if isinstance(h.get(key), (int, float))]
        if today is None or len(past) < 3:
            continue
        avg = sum(past) / len(past)
        if today >= avg + 3 and today >= 2 * avg:
            flags.append(f"{label}: {today} (usually about {avg:.0f})")
        elif today == 0 and avg >= 3:
            flags.append(f"{label}: 0 (usually about {avg:.0f})")
    return flags, None


def urgent_reasons(sweep, health):
    reasons = []
    for name, code in health["http"].items():
        if code != 200:
            reasons.append(f"{name.replace('_', ' ')} is down (answered {code or 'nothing'})")
    age = health["backup"]["age_hours"]
    if age is None:
        reasons.append("no database backup found")
    elif age > BACKUP_MAX_HOURS:
        reasons.append(f"newest backup is {age:.0f} hours old")
    if sweep["status"] in ("failed", "stale", "missing"):
        reasons.append(f"last sweep {sweep['status']}")
    return reasons


def raw_lines(users, usage, sweep, health):
    """The numbers, as plain lines. Used when the LLM summary isn't available, and as the detail block."""
    h, b = health, health["backup"]
    active = users["active_24h"] if users["active_24h"] is not None else "n/a (needs migration 002)"
    return [
        f"Users: {users['total']} total, {users['new_24h'] if users['new_24h'] is not None else 'n/a'} new, {active} active (24h)",
        "Usage (24h): " + ", ".join(f"{k.replace('_', ' ')} {v if v is not None else 'n/a'}" for k, v in usage.items()),
        f"Sweep: {sweep['status']}, {sweep['cards']} cards, {sweep['failed_pages']} failed pages"
        + (f"; price update {sweep['price_update']['updated']} updated, {sweep['price_update']['failed']} failed" if sweep.get("price_update") else ""),
        "Health: " + ", ".join(f"{k.replace('_', ' ')} {v or 'down'}" for k, v in h["http"].items())
        + f"; {h['errors']} server errors; disk {h['disk_used_pct']}% used ({h['disk_free_gb']} GB free)",
        f"Backup: {b['newest']} ({b['age_hours']} h old, {b['size_mb']} MB)",
        f"Security (24h): {h['failed_logins']} failed logins, {h['rate_limited']} rate-limit blocks",
    ]


# ---------------------------------------------------------------- Mondays: PokeTrace data issues (a draft, never sent)

ISSUES_FILE = os.path.join(REPO, "agents", "poketrace_issues.json")
DRAFT_NAME = "poketrace_draft.txt"


def is_draft_day(now=None):
    """Monday in New York, where the report is read (it runs at 8 AM Eastern)."""
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York")).weekday() == 0


def broken_images(csv_path):
    """(count, top sets, file bytes) from broken_images.csv (image_doctor's or the older format), or (None, [], None)."""
    try:
        with open(csv_path, "rb") as f:
            data = f.read()
    except OSError:
        return None, [], None
    rows = list(csv.DictReader(data.decode("utf-8", errors="replace").splitlines()))
    sets = Counter((r.get("set") or r.get("set_name") or "?") for r in rows).most_common(5)
    return len(rows), sets, data


def mispriced_line(summary_path):
    """'X cards have a lower condition priced above Near Mint (CSV attached)' from Price Doctor, or None."""
    try:
        with open(summary_path) as f:
            r = json.load(f)
    except (OSError, ValueError):
        return None
    x, n, stale = r.get("cards") or 0, r.get("cards_checked") or 0, r.get("stale_nm_cards") or 0
    pct, dollars = r.get("min_pct", 10), r.get("min_dollars", 1)
    line = (f"{x:,} card{'' if x == 1 else 's'} {'has' if x == 1 else 'have'} a lower condition priced above Near Mint "
            f"(CSV attached): at least {pct:g}% and ${dollars:g} "
            f"above Near Mint on the same source, out of {n:,} popular cards we checked")
    return line + (f". In {stale:,} of them the Near Mint price hadn't been updated in over 30 days." if stale else ".")


def sample_line(path):
    """'In a sample of Y ... X had ...' from scripts/check_condition_order.py's results, or a [placeholder]."""
    try:
        with open(path) as f:
            r = json.load(f)
    except (OSError, ValueError):
        return ("[Run scripts/check_condition_order.py, then send the Ops report again with --poketrace-draft: "
                "this line becomes \"X of Y popular cards we checked...\". Or delete this line.]")
    n, x, stale = r.get("checked") or 0, r.get("cards_with_inversion") or 0, r.get("cards_where_nm_was_stale") or 0
    when = (r.get("run_at") or "")[:10]
    line = (f"This isn't a rare edge case: of {n} popular cards we checked on {when} (our most-sold cards over $10), "
            f"{x} had at least one played condition priced above Near Mint on the same source")
    return line + (f", and in {stale} of those the Near Mint price hadn't been updated in over 30 days." if stale else ".")


def poketrace_draft(facts, broken_count, broken_sets, sample=None):
    """The email text. Plain code from the facts file, so every number is exactly what PokeTrace sent us.
    Pricing first (the main point), then set naming, then broken images (short)."""
    out = ["Subject: PokeTrace API: condition prices out of order (played conditions priced above Near Mint)", "",
           "Hi PokeTrace team,", "",
           "I run buyndermarket.com, a Pokémon card price site built on the PokeTrace API. I found some problems in the "
           "data and wanted to pass them on with exact examples, starting with the most important one. "
           f"All card numbers below are from your API responses on {facts['data_date']}.", "",
           "1. Condition prices (the main issue)", "",
           facts["pricing_lead"], "",
           sample or "", ""]
    for c in facts["stale_prices"]:
        out.append(f"{c['card']}, {c['set']} (PokeTrace ID {c['poketrace_id']}):")
        out.append(c["headline"])
        out += [f"  - {e}" for e in c["evidence"]]
        out.append("")
    out.append("Could you:")
    out += [f"  - {a}" for a in facts["asks"]]
    out += ["", "2. Set naming", "", "Some sets appear under two slugs:"]
    out += [f"  - {' / '.join(d['slugs'])}: {d['detail']}" for d in facts["duplicate_sets"]]
    out += ["", "And the Pokémon set list (/v1/sets?game=pokemon) includes sets that don't look like Pokémon:"]
    out += [f"  - {n['name']} ({n['slug']}): {n['looks_like']}" for n in facts["non_pokemon_sets"]]
    out += ["", "Could these be merged under one slug, and the non-Pokémon sets moved to their own game?", "",
            "3. Broken card images", ""]
    if broken_count is None:
        out.append("[broken_images.csv wasn't found on the server this week; delete this section or add the count]")
    else:
        out.append(f"{broken_count:,} card images on cdn.poketrace.com currently don't load (404, 403 or a server error). "
                   "The attached broken_images.csv lists each one with its PokeTrace ID and image URL.")
    out += ["", "Thanks for looking into these. I'm happy to send more examples or re-check after a fix.", "",
            "[your name]", "PokeTrace account: [your account email]", ""]
    return "\n".join(l for l in out if l is not None)


def draft_section(dry_run=False):
    """(Discord lines, attachments, note) for Mondays."""
    try:
        with open(ISSUES_FILE) as f:
            facts = json.load(f)
    except (OSError, ValueError) as e:
        return [], [], f"PokeTrace draft skipped: {ISSUES_FILE} unreadable ({type(e).__name__})"
    count, sets, csv_bytes = broken_images(os.path.join(REPO, "broken_images.csv"))
    # Price Doctor's numbers (with its CSV) when it has run; otherwise the one-off sample script's, or a placeholder
    mispriced = mispriced_line(os.path.join(REPO, "data", "price_doctor_summary.json"))
    text = poketrace_draft(facts, count, sets,
                           mispriced or sample_line(os.path.join(REPO, "scripts", "condition_order_check.json")))
    if dry_run:
        print("\n----- PokeTrace draft (attachment, dry run) -----\n" + text + "-------------------------------------------------\n")
    files = [(DRAFT_NAME, text.encode("utf-8"), "text/plain")]
    mis_path = os.path.join(REPO, "data", "mispriced_cards.csv")
    if mispriced and os.path.exists(mis_path):
        with open(mis_path, "rb") as f:
            files.append(("mispriced_cards.csv", f.read(), "text/csv"))
    if csv_bytes:
        files.append(("broken_images.csv", csv_bytes, "text/csv"))
    attached = [f[0] for f in files[1:]]
    lines = ["", "**PokeTrace data issues (weekly)**",
             f"A draft email to PokeTrace support is attached ({DRAFT_NAME}"
             + (f", plus {' and '.join(attached)}" if attached else "") + "). "
             "It was NOT sent: fill in your name and account email, then send it yourself if you want to."]
    return lines, files, None


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="collect everything, send nothing")
    ap.add_argument("--sample", action="store_true", help="made-up numbers: no database, no .env, no network")
    ap.add_argument("--poketrace-draft", action="store_true", help="include the Monday PokeTrace draft today")
    ap.add_argument("--scheduled", action="store_true",
                    help="for cron: run only if it's 8 AM in New York right now, else exit quietly. Cron fires at "
                         "12:00 and 13:00 UTC; this keeps the one that is 8 AM Eastern (EDT = UTC-4, EST = UTC-5)")
    args = ap.parse_args()
    if args.scheduled and not is_local_time(AGENT):
        return                                                # the other of the two cron times today
    if args.sample:
        args.dry_run = True
    else:
        load_env()

    with Run(AGENT, steps=7, dry_run=args.dry_run) as run:
        notes = []
        if args.sample:
            for label in ("Counting users and usage", "Reading the sweep logs", "Checking site, API, disk and backups"):
                run.step(label)
            users, usage, sweep, health = sample_facts()
        else:
            run.step("Counting users and usage")
            users, usage = user_and_usage_facts()
            run.step("Reading the sweep logs")
            sweep = sweep_facts()
            run.step("Checking site, API, disk and backups")
            health = health_facts()

        run.step("Comparing with the last 7 days")
        metrics = {"users": users, "usage": usage, "sweep": {k: v for k, v in sweep.items() if k != "finished"}, "health": health}
        history = [flat(r["metrics"]) for r in read_runs(AGENT, days=7, dry_run=args.dry_run)]
        flags, why_not = unusual(flat(metrics), history)
        if why_not:
            notes.append(why_not)

        run.step("Checking for urgent problems")
        urgent = urgent_reasons(sweep, health)

        run.step("Writing the summary")
        llm = LLM(run, dry_run=args.dry_run)
        facts = json.dumps({"unusual_vs_last_7_days": flags, "urgent": urgent, "numbers": metrics}, default=str)
        text, problem = llm.summarize(
            system=("You write the daily operations report for buyndermarket.com, a small Pokémon card price site, "
                    "for its owner. 5 to 10 short plain-text lines. Start with anything urgent, then anything unusual "
                    "compared with the last 7 days, then a one-line all-clear for everything else. Use only the numbers "
                    "given; say 'n/a' when a number is missing. No emoji, no markdown headings, no greeting."),
            facts=facts, max_tokens=700)
        if problem:
            notes.append(f"summary: {problem}")

        run.step("Sending the report")
        head = f"**Ops report, {datetime.now().strftime('%a %b %d')}**"
        lines = ([f"🚨 **URGENT:** " + "; ".join(urgent)] if urgent else []) + [head]
        if text:
            lines += text.splitlines()
        else:
            if flags:
                lines.append("Unusual vs last 7 days: " + "; ".join(flags))
            lines += raw_lines(users, usage, sweep, health)
        files = []
        if args.poketrace_draft or (is_draft_day() and not args.sample):
            extra, files, skipped = draft_section(dry_run=args.dry_run)
            if skipped:
                notes.append(skipped)
            # Put the section near the top, so cutting a long report to Discord's 2,000 characters never drops it
            lines = lines[:1 + bool(urgent)] + extra + [""] + lines[1 + bool(urgent):]
        ok, send_problem = send_discord(fit_discord(lines), files=files or None, dry_run=args.dry_run)
        if not ok:
            notes.append(send_problem)

        real_problem = problem and problem != "dry run: no API call made"
        state = "error" if urgent else ("warn" if real_problem or not ok or flags else "ok")
        summary = ("URGENT: " + "; ".join(urgent)) if urgent else (("Unusual: " + "; ".join(flags)) if flags else "All normal")
        run.finish(state, summary=summary, metrics=metrics, urgent=bool(urgent), notes=[redact(n) for n in notes])
        print(f"[{AGENT}] {state}: {summary}")


if __name__ == "__main__":
    main()
