"""Ops dashboard: a read-only status board for the ops agents, on port 5190.

Separate from the public API (../app.py) and not behind the Cloudflare tunnel. Only the LAN
(10.0.0.0/24), Tailscale (100.64.0.0/10) and this machine may connect; everyone else gets 403.

    GET /            the TV page (refreshes itself every 10 s)
    GET /api/status  the same data as JSON, plus a "spoken_summary" for the voice assistant

It only READS files the agents write (data/agent_status/*.json, data/agent_runs.jsonl, agents.log),
the newest backup's date/size, and the disk. It never touches the database or .env.

    venv/bin/python ops_dashboard/dashboard.py          # real data in data/
    venv/bin/python ops_dashboard/dashboard.py --sample # made-up data, for trying it out
"""
import argparse
import glob
import ipaddress
import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, abort, jsonify, request, send_from_directory

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("OPS_DATA_DIR", os.path.join(REPO, "data"))

ALLOWED_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/24", "100.64.0.0/10", "127.0.0.0/8", "::1/128")]
# Browsers on these origins may call /api/status: a page on port 8080 of this machine, plus any listed in
# OPS_CORS_ORIGINS=http://a:8080,http://b:8080 (e.g. a Raspberry Pi's voice-assistant page on the LAN; set it in
# the systemd unit). Server-to-server requests don't need CORS at all.
LOCAL_ORIGINS = {"http://localhost:8080", "http://127.0.0.1:8080"}
CORS_ORIGINS = LOCAL_ORIGINS | {o.strip() for o in os.environ.get("OPS_CORS_ORIGINS", "").split(",") if o.strip()}

AGENTS = {  # what each card shows: label, how often it runs, which numbers, which one the sparkline draws
    "image_doctor": {"label": "Image doctor", "every_hours": 24,
                     "numbers": [("newly_broken", "New breaks"), ("fixed", "Fixed"), ("broken_total", "Broken now"), ("checked", "Checked")],
                     "spark": ("broken_total", "Broken images, 7 days")},
    "price_doctor": {"label": "Price doctor", "every_hours": 24,
                     "numbers": [("flagged_cards", "Cards flagged"), ("stale_nm_cards", "Stale NM"), ("checked", "Checked"), ("requests", "Requests")],
                     "spark": ("flagged_cards", "Cards priced above NM, 7 days")},
    "ops_report": {"label": "Ops report", "every_hours": 24,
                   "numbers": [("users.total", "Users"), ("users.active_24h", "Active 24h"), ("health.errors", "Errors 24h"), ("health.failed_logins", "Failed logins")],
                   "spark": ("health.errors", "Server errors, 7 days")},
}
URLS = {"Site": "https://buyndermarket.com/", "API": "http://localhost:5050/", "Public API": "https://api.buyndermarket.com/"}
STALE_GRACE_HOURS = 2       # a daily agent is "stale" if its last run is more than 24 + 2 hours old

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------- who may connect

@app.before_request
def only_home_network():
    """403 for anyone outside the LAN / Tailscale / this machine, and for anything that came
    through Cloudflare (the tunnel connects from 127.0.0.1, but always adds CF-Connecting-IP)."""
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        abort(403)
    if not any(ip in net for net in ALLOWED_NETS) or "CF-Connecting-IP" in request.headers:
        abort(403)


@app.after_request
def headers(resp):
    origin = request.headers.get("Origin")
    if origin and origin in CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# ---------------------------------------------------------------- reading the agents' files

def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get(metrics, dotted):
    """metrics['users']['total'] via 'users.total'."""
    for part in dotted.split("."):
        if not isinstance(metrics, dict):
            return None
        metrics = metrics.get(part)
    return metrics if isinstance(metrics, (int, float)) and not isinstance(metrics, bool) else None


def history(agent, days=7):
    """Runs from the last N days, oldest first."""
    path = os.path.join(DATA, "agent_runs.jsonl")
    cutoff = time.time() - days * 86400
    runs = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("agent") == agent and r.get("finished_ts", 0) >= cutoff:
                    runs.append(r)
    except OSError:
        pass
    return runs


def hours_since(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def process_alive(pid):
    """Is that agent process still there? (The board runs as the same user, so asking is allowed.)"""
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, ValueError, TypeError, OverflowError):
        return False


def agent_card(agent, cfg):
    st = read_json(os.path.join(DATA, "agent_status", f"{agent}.json")) or {}
    running = st.get("state") == "running"
    died = running and st.get("pid") and not process_alive(st["pid"])   # killed hard (power cut, kill -9): no record
    if died:
        running = False
        st = {**st, "state": "stopped", "summary": f"Stopped without finishing (during: {st.get('step')})",
              "finished_at": st.get("updated_at"), "metrics": (st.get("last") or {}).get("metrics")}
    last = st.get("last") if running else st                       # numbers from the last *finished* run
    last = last or {}
    metrics = last.get("metrics") or {}
    age = hours_since(last.get("finished_at"))
    stale = age is None or age > cfg["every_hours"] + STALE_GRACE_HOURS
    runs = history(agent)
    spark_key, spark_label = cfg["spark"]
    return {
        "agent": agent, "label": cfg["label"],
        "state": "running" if running else (last.get("state") or "never"),
        "stale": stale and not running,
        # While it runs: the current step and how far along, NOT the last run's result
        "step": (f"{st.get('step')} ({st['detail']})" if st.get("detail") else st.get("step")) if running else None,
        "step_no": st.get("step_no") if running else None,
        "steps": st.get("steps") if running else None,
        "last_run": last.get("finished_at"), "hours_ago": round(age, 1) if age is not None else None,
        "duration_s": last.get("duration_s"),
        "summary": None if running else last.get("summary"),
        "last_state": last.get("state") if running else None,
        "urgent": bool(last.get("urgent")),
        "next_run": st.get("next_run"),
        "numbers": [{"label": label, "value": get(metrics, key)} for key, label in cfg["numbers"]],
        "sparkline": {"label": spark_label, "values": [get(r.get("metrics") or {}, spark_key) for r in runs][-7:]},
        "dry_run": bool(st.get("dry_run")),
    }


# ---------------------------------------------------------------- health strip (cached, so the TV can't hammer the site)

_HEALTH = {"at": 0, "data": None}
_LOCK = threading.Lock()


def http_ok(url):
    try:
        return requests.get(url, timeout=5).status_code == 200
    except requests.RequestException:
        return False


def health(sample=False):
    if sample:
        return {"checks": [{"name": n, "ok": True} for n in URLS], "disk_used_pct": 61.3, "backup_age_hours": 14.5,
                "backup_size_mb": 38.2}
    with _LOCK:
        if time.time() - _HEALTH["at"] < 60 and _HEALTH["data"]:
            return _HEALTH["data"]
        disk = shutil.disk_usage("/")
        backups = glob.glob(os.path.join(REPO, "backups", "pokemarket-*.sql.gz"))
        newest = max(backups, key=os.path.getmtime) if backups else None
        data = {
            "checks": [{"name": n, "ok": http_ok(u)} for n, u in URLS.items()],
            "disk_used_pct": round(disk.used / disk.total * 100, 1),
            "backup_age_hours": round((time.time() - os.path.getmtime(newest)) / 3600, 1) if newest else None,
            "backup_size_mb": round(os.path.getsize(newest) / 1e6, 1) if newest else None,
        }
        _HEALTH.update(at=time.time(), data=data)
        return data


def log_lines(n=12):
    """Last lines of agents.log (where cron sends agent output), newest last."""
    path = os.environ.get("OPS_LOG_FILE", os.path.join(REPO, "agents.log"))
    try:
        with open(path, errors="replace") as f:
            lines = [l.rstrip() for l in f.readlines()[-200:] if l.strip() and not l.startswith("-----")]
        return lines[-n:]
    except OSError:
        return []


# ---------------------------------------------------------------- the summary

def spoken(agents, h, urgent):
    """1-2 plain sentences for text-to-speech. No emoji, no symbols, numbers as words-friendly digits."""
    down = [c["name"] for c in h["checks"] if not c["ok"]]
    if down:
        first = f"Heads up: the {' and the '.join(n if 'API' in n else n.lower() for n in down)} {'is' if len(down) == 1 else 'are'} not responding."
    elif urgent:
        first = "Heads up: the last ops report flagged an urgent problem. Check Discord for details."
    elif any(a["state"] == "error" for a in agents):
        first = "One of the ops agents hit an error on its last run."
    elif all(a["state"] == "never" for a in agents):
        first = "The ops agents haven't run yet."
    elif any(a["stale"] for a in agents):
        names = [a["label"].lower() for a in agents if a["stale"]]
        first = f"The {' and '.join(names)} {'has' if len(names) == 1 else 'have'} not run on schedule."
    elif any(a["state"] == "stopped" for a in agents):
        names = [a["label"].lower() for a in agents if a["state"] == "stopped"]
        first = f"The {' and the '.join(names)} stopped before finishing. It carries on where it left off next time."
    elif any(a["state"] == "warn" for a in agents):
        names = [a["label"].lower() for a in agents if a["state"] == "warn"]
        first = f"The {' and the '.join(names)} finished with a warning. Check Discord for details."
    else:
        first = "Everything is running normally."
    img = next((a for a in agents if a["agent"] == "image_doctor"), None)
    second = ""
    if img and img["state"] not in ("never",):
        nb = next((x["value"] for x in img["numbers"] if x["label"] == "New breaks"), None)
        if nb:
            second = f" Last night {nb} card {'image' if nb == 1 else 'images'} broke."
        elif nb == 0:
            second = " No new broken card images last night."
    if h.get("backup_age_hours") is not None and h["backup_age_hours"] > 36:
        second += f" The newest backup is {round(h['backup_age_hours'])} hours old."
    return (first + second).strip()


def status(sample=False):
    agents = [agent_card(a, cfg) for a, cfg in AGENTS.items()]
    h = health(sample)
    urgent = any(a["urgent"] for a in agents) or not all(c["ok"] for c in h["checks"]) \
        or (h.get("backup_age_hours") or 0) > 36
    if urgent or any(a["state"] == "error" for a in agents):
        overall = "error"
    elif any(a["state"] in ("warn", "stopped") or a["stale"] for a in agents):
        overall = "warn"
    else:
        overall = "ok"
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "overall": overall, "urgent": urgent,
        "agents": agents, "health": h, "log": log_lines(),
        "spoken_summary": spoken(agents, h, urgent),
    }


# ---------------------------------------------------------------- routes

@app.get("/api/status")
def api_status():
    return jsonify(status(app.config.get("SAMPLE", False)))


@app.get("/")
def page():
    return send_from_directory(HERE, "index.html")


def main():
    global DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="show made-up data (writes it to a temp folder)")
    ap.add_argument("--port", type=int, default=5190)
    args = ap.parse_args()
    if args.sample:
        from sample_data import make_sample
        DATA = make_sample()
        os.environ["OPS_LOG_FILE"] = os.path.join(DATA, "agents.log")
        app.config["SAMPLE"] = True
        print(f"Sample data in {DATA}")
    app.run(host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
