#!/usr/bin/env python3
"""image_doctor: nightly check of card images, after the market sweep.

1. Find cards that are new or got a new image URL in the last 24 hours, plus every card that was
   broken last time (to see if it's fixed).
2. HEAD-check those images politely (a few at a time, small pauses, our own User-Agent).
3. Compare with the last run: newly broken / fixed / still broken.
4. Rewrite broken_images.csv (every card that's broken right now).
5. Message you on Discord with the counts, up to 10 cards per list, the CSV attached, and a
   1-2 line pattern summary. (The weekly email draft for PokeTrace is in the Ops report on Mondays,
   with this CSV attached: one draft that covers prices, sets and images.)

It never contacts PokeTrace (no API calls, no email): it only loads the public image files, the
same way a visitor's browser does.

    venv/bin/python agents/image_doctor.py --dry-run            # real data, nothing sent or written
    venv/bin/python agents/image_doctor.py --dry-run --sample   # made-up data, no database, no .env
"""
import argparse
import csv
import io
import json
import os
import random
import shutil
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests                                       # noqa: E402
from common import LLM, db_connect, fit_discord, load_env, redact, send_discord   # noqa: E402
from runlog import REPO, Run, data_dir, write_json_atomic                    # noqa: E402

AGENT = "image_doctor"
CSV_COLUMNS = ["poketrace_id", "name", "set", "number", "image_url", "first_seen_broken", "last_checked"]
USER_AGENT = "BuynderImageDoctor/1.0 (+https://buyndermarket.com; nightly image check)"
LIST_MAX = 10


def today():
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- data in

def load_cards_db(hours=24):
    """Market cards synced in the last N hours that have an image (read-only query)."""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT poketrace_id, name, set_name, card_number, image_url
        FROM market_cards
        WHERE image_url IS NOT NULL AND image_url != '' AND last_synced >= NOW() - INTERVAL %s HOUR
    """, (hours,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def sample_cards():
    """Made-up cards for --sample: 40 cards in 4 sets."""
    sets = ["Battle Academy 2024", "Prismatic Evolutions", "Base Set", "Surging Sparks"]
    return [{"poketrace_id": f"00000000-0000-4000-8000-{i:012d}", "name": f"Sample Card {i}",
             "set_name": sets[i % 4], "card_number": f"{i:03d}",
             "image_url": f"https://cdn.example.test/cards/{i:04d}.webp"} for i in range(40)]


def load_state(folder):
    path = os.path.join(folder, "image_doctor_state.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"urls": {}, "broken": {}, "last_run": None}


def seed_from_old_csv(state, csv_path):
    """First run only: the broken_images.csv you already have becomes 'known broken', so those
    cards are re-checked and reported as fixed / still broken instead of all 'newly broken'."""
    if state["broken"] or not os.path.exists(csv_path):
        return 0
    seen = datetime.fromtimestamp(os.path.getmtime(csv_path)).strftime("%Y-%m-%d")
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            pid = row.get("poketrace_id")
            if pid and row.get("image_url"):
                state["broken"][pid] = {
                    "name": row.get("name", ""), "set": row.get("set") or row.get("set_name", ""),
                    "number": row.get("number") or row.get("card_number", ""), "image_url": row["image_url"],
                    "first_seen_broken": row.get("first_seen_broken") or seen, "last_checked": row.get("last_checked", "")}
    return len(state["broken"])


# ---------------------------------------------------------------- checking

class Checker:
    """HEAD requests, a few at a time. Result per URL: 'ok', 'broken', or 'unknown' (timeout/network:
    not counted as broken, so a slow night doesn't flood you with false alarms)."""

    def __init__(self, workers=6, pause=0.05):
        self.workers, self.pause = workers, pause
        self.local = threading.local()

    def _session(self):
        if not hasattr(self.local, "s"):
            self.local.s = requests.Session()
            self.local.s.headers["User-Agent"] = USER_AGENT
        return self.local.s

    def check(self, url):
        time.sleep(self.pause)                                  # be polite to the image server
        try:
            r = self._session().head(url, timeout=10, allow_redirects=True)
            if r.status_code == 405:                            # server doesn't do HEAD: fetch, don't download
                r = self._session().get(url, timeout=10, stream=True)
                r.close()
            if r.status_code == 200:
                return "ok"
            if r.status_code in (404, 403, 410) or (r.status_code >= 500 and r.status_code != 503):
                return "broken"
            return "unknown"                                    # 429/503: they're busy, ask again tomorrow
        except requests.RequestException:
            return "unknown"

    def run(self, urls):
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return dict(zip(urls, pool.map(self.check, urls)))


class SampleChecker:
    """--sample: every 7th card is broken, a couple are 'unknown'."""
    def run(self, urls):
        out = {}
        for u in urls:
            n = int(u.rsplit("/", 1)[1].split(".")[0])
            rule = 5 if os.getenv("SAMPLE_NIGHT") == "2" else 7     # night 2: some get fixed
            out[u] = "broken" if n % rule == 0 else ("unknown" if n in (11, 22) else "ok")
        return out


# ---------------------------------------------------------------- output

def card_line(c):
    num = f" #{c['number']}" if c.get("number") else ""
    return f"{c['name']} — {c['set']}{num} ({c['poketrace_id']})"


def card_list(title, cards):
    lines = [f"**{title} ({len(cards)})**"]
    lines += [f"• {card_line(c)}" for c in cards[:LIST_MAX]]
    if len(cards) > LIST_MAX:
        lines.append(f"+{len(cards) - LIST_MAX} more")
    return lines


def csv_bytes(broken):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    w.writeheader()
    for pid, c in sorted(broken.items(), key=lambda kv: (kv[1]["set"], kv[1]["number"])):
        w.writerow({"poketrace_id": pid, **{k: c.get(k, "") for k in CSV_COLUMNS[1:]}})
    return buf.getvalue().encode()


def pattern_facts(new, still):
    """Plain-code patterns the summary can lean on: which sets and image hosts the broken cards are in."""
    sets_new = Counter(c["set"] for c in new).most_common(3)
    sets_all = Counter(c["set"] for c in new + still).most_common(3)
    hosts = Counter(urlparse(c["image_url"]).netloc for c in new + still).most_common(2)
    exts = Counter(os.path.splitext(urlparse(c["image_url"]).path)[1] for c in new + still).most_common(2)
    return {"newly_broken_by_set": sets_new, "all_broken_by_set": sets_all, "hosts": hosts, "file_types": exts}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="check images but send nothing and write no CSV")
    ap.add_argument("--sample", action="store_true", help="made-up cards and results: no database, no .env, no network")
    ap.add_argument("--max-checks", type=int, default=6000, help="cap per night; the rest wait for the next run")
    ap.add_argument("--workers", type=int, default=6, help="images checked at the same time")
    args = ap.parse_args()
    if args.sample:
        args.dry_run = True                                   # sample data is never sent anywhere
    else:
        load_env()

    folder = data_dir(args.dry_run)
    csv_path = os.path.join(REPO, "broken_images.csv")

    with Run(AGENT, steps=6, dry_run=args.dry_run) as run:
        notes, state_warn = [], False

        run.step("Loading cards synced in the last 24 hours")
        cards = sample_cards() if args.sample else load_cards_db()
        state = load_state(folder)
        seeded = 0 if args.sample else seed_from_old_csv(state, csv_path)
        if seeded:
            notes.append(f"first run: started from the {seeded} cards already in broken_images.csv")

        run.step("Choosing what to check")
        by_id = {c["poketrace_id"]: c for c in cards}
        recheck = list(state["broken"])                                    # were broken: fixed yet?
        changed = [pid for pid, c in by_id.items()
                   if pid not in state["broken"] and state["urls"].get(pid) != c["image_url"]]
        todo = (recheck + changed)[:args.max_checks]
        deferred = len(recheck) + len(changed) - len(todo)
        if deferred:
            notes.append(f"{deferred} images left for the next run (cap {args.max_checks} per night)")

        run.step(f"Checking {len(todo)} images")
        def url_of(pid):
            return (by_id.get(pid) or state["broken"].get(pid, {})).get("image_url")
        urls = {pid: url_of(pid) for pid in todo if url_of(pid)}
        checker = SampleChecker() if args.sample else Checker(workers=args.workers)
        results = checker.run(list(set(urls.values())))
        status = {pid: results[u] for pid, u in urls.items()}

        run.step("Comparing with the last run")
        prev_broken = dict(state["broken"])
        new, fixed, still = [], [], []
        for pid, s in status.items():
            card = by_id.get(pid)
            info = ({"name": card["name"], "set": card["set_name"] or "", "number": card["card_number"] or "",
                     "image_url": card["image_url"]} if card else dict(prev_broken[pid]))
            info["poketrace_id"] = pid
            if s == "broken":
                info["first_seen_broken"] = prev_broken.get(pid, {}).get("first_seen_broken") or today()
                info["last_checked"] = today()
                state["broken"][pid] = {k: v for k, v in info.items() if k != "poketrace_id"}
                (still if pid in prev_broken else new).append(info)
            elif s == "ok":
                if pid in prev_broken:
                    fixed.append(info)
                    del state["broken"][pid]
            if s != "unknown" and card:
                state["urls"][pid] = card["image_url"]          # remember it so it's only re-checked if it changes
        unknown = sum(1 for s in status.values() if s == "unknown")
        if status and unknown / len(status) > 0.10:
            state_warn = True
            notes.append(f"{unknown} of {len(status)} checks got no clear answer (timeouts or 'busy'); they'll be retried")
        state["last_run"] = datetime.now().isoformat(timespec="seconds")

        run.step("Writing broken_images.csv")
        data = csv_bytes(state["broken"])
        if not args.dry_run:
            backup = os.path.join(folder, "broken_images.before-image-doctor.csv")
            if os.path.exists(csv_path) and not os.path.exists(backup):
                shutil.copy2(csv_path, backup)                 # keep your original file the first time
            with open(csv_path, "wb") as f:
                f.write(data)
        # State lives in data/ (or data/dryrun/ for dry runs, so tests never touch the real one)
        write_json_atomic(os.path.join(folder, "image_doctor_state.json"), state)

        run.step("Writing the summary and messaging you")
        metrics = {"checked": len(status), "newly_broken": len(new), "fixed": len(fixed),
                   "still_broken": len(still), "broken_total": len(state["broken"]), "unknown": unknown,
                   "deferred": deferred, "cards_synced_24h": len(cards)}
        llm = LLM(run, dry_run=args.dry_run)
        summary_line, problem = None, None
        if new or fixed:
            facts = json.dumps({"counts": metrics, "patterns": pattern_facts(new, still)}, default=str)
            summary_line, problem = llm.summarize(
                system=("You write a 1-2 sentence plain-text note about broken Pokémon card images for the site owner. "
                        "Use only the numbers given. Point out a pattern if there is one (one set, one file type, one host). "
                        "No emoji, no markdown, no greeting."),
                facts=facts, max_tokens=300)
            if problem:
                notes.append(f"summary: {problem}")

        when = datetime.now().strftime("%a %b %d")
        if not new and not fixed:
            lines = [f"**Image doctor, {when}**", "No new broken images ✅",
                     f"{len(still)} still broken, {len(status)} checked."]
        else:
            lines = [f"**Image doctor, {when}**",
                     f"Newly broken {len(new)} · Fixed {len(fixed)} · Still broken {len(still)} · Checked {len(status)}"]
            if summary_line:
                lines.append(summary_line)
            elif new:                                          # no LLM: raw pattern instead
                top = pattern_facts(new, still)["newly_broken_by_set"]
                lines.append("Most new breaks: " + ", ".join(f"{s} ({n})" for s, n in top))
            lines += [""] + card_list("Newly broken", new) + [""] + card_list("Fixed", fixed) + [""] + card_list("Still broken", still)
        if deferred:
            lines.append(f"\n{deferred} images wait for the next run.")

        files = [("broken_images.csv", data, "text/csv")]

        ok, send_problem = send_discord(fit_discord(lines), files=files, dry_run=args.dry_run)
        if not ok:
            notes.append(send_problem)

        level = "warn" if (problem and (new or fixed)) or state_warn or not ok else "ok"
        if problem == "dry run: no API call made":
            level = "warn" if state_warn or not ok else "ok"   # skipping the LLM on purpose isn't a problem
        summary = (f"{len(new)} newly broken, {len(fixed)} fixed, {len(still)} still broken" if (new or fixed)
                   else f"No new broken images ({len(still)} still broken)")
        run.finish(level, summary=summary, metrics=metrics, notes=[redact(n) for n in notes])
        print(f"[{AGENT}] {level}: {summary}")


if __name__ == "__main__":
    main()
