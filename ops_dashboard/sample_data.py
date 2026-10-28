"""Made-up agent files for `app.py --sample`: 7 days of history, one agent mid-run."""
import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone


def iso(dt):
    return dt.astimezone().isoformat(timespec="seconds")


def make_sample():
    folder = tempfile.mkdtemp(prefix="ops-sample-")
    os.makedirs(os.path.join(folder, "agent_status"))
    now = datetime.now(timezone.utc)
    runs = []
    broken = [1042, 1040, 1041, 1037, 1031, 1033, 1029]
    errors = [1, 0, 3, 2, 0, 1, 2]
    for d in range(7):                                   # 6 days ago ... today
        img_end = now - timedelta(days=6 - d, hours=3)
        runs.append({"agent": "image_doctor", "state": "ok", "finished_at": iso(img_end), "finished_ts": img_end.timestamp(),
                     "duration_s": 1120 + d * 13, "summary": f"{d % 3} newly broken", "urgent": False,
                     "metrics": {"newly_broken": d % 3, "fixed": (d + 1) % 4, "broken_total": broken[d], "checked": 640 + d * 9}})
        rep_end = now - timedelta(days=6 - d, hours=1)
        runs.append({"agent": "ops_report", "state": "ok", "finished_at": iso(rep_end), "finished_ts": rep_end.timestamp(),
                     "duration_s": 6.2, "summary": "All normal", "urgent": False,
                     "metrics": {"users": {"total": 14, "active_24h": 4 + d % 3}, "health": {"errors": errors[d], "failed_logins": 2 + d % 2}}})
    with open(os.path.join(folder, "agent_runs.jsonl"), "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in runs)

    last_img = runs[-2]
    with open(os.path.join(folder, "agent_status", "image_doctor.json"), "w") as f:
        json.dump({**last_img, "agent": "image_doctor", "step": "Done", "step_no": 6, "steps": 6,
                   "next_run": iso((now + timedelta(days=1)).replace(hour=3, minute=15, second=0))}, f)
    last_rep = runs[-1]
    with open(os.path.join(folder, "agent_status", "ops_report.json"), "w") as f:   # running right now
        json.dump({"agent": "ops_report", "state": "running", "step": "Checking site, API, disk and backups",
                   "step_no": 3, "steps": 7, "started_at": iso(now - timedelta(seconds=4)),
                   "next_run": iso((now + timedelta(days=1)).replace(hour=8, minute=0, second=0)),
                   "last": {k: last_rep[k] for k in ("state", "finished_at", "duration_s", "metrics", "summary", "urgent")}}, f)

    with open(os.path.join(folder, "agents.log"), "w") as f:
        stamp = now.strftime("%H:%M")
        f.write("\n".join([
            "[image_doctor] 1/6 Loading cards synced in the last 24 hours",
            "[image_doctor] 3/6 Checking 649 images",
            "[image_doctor] 6/6 Writing the summary and messaging you",
            "[image_doctor] ok: 0 newly broken, 1 fixed, 1029 still broken",
            f"[ops_report] 1/7 Counting users and usage ({stamp})",
            "[ops_report] 2/7 Reading the sweep logs",
            "[ops_report] 3/7 Checking site, API, disk and backups",
        ]) + "\n")
    os.utime(folder, (time.time(), time.time()))
    return folder
