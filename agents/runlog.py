"""Shared run log for the ops agents.

Every run appends one line to data/agent_runs.jsonl (history, for 7-day comparisons and the dashboard)
and keeps data/agent_status/<agent>.json up to date while it runs (current step, "N of M"),
so the dashboard can show live progress. Dry runs write to data/dryrun/ instead, so they never
mix with real history.

    with Run("ops_report", steps=8, dry_run=args.dry_run) as run:
        run.step("Counting users")
        ...
        run.finish("ok", summary="...", metrics={...}, urgent=False)
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# When each agent runs: (hour, minute, time zone), so the status file can say when the next run is.
# Keep in sync with the cron lines in agents/README.md.
SCHEDULES = {
    "image_doctor": (3, 15, "UTC"),                # starts 03:15 UTC, waits for the 03:00 sweep's lock, so really ~04:00
    "price_doctor": (3, 20, "UTC"),                # starts 03:20 UTC, waits for the same lock (after the sweep and Image Doctor)
    "ops_report": (8, 0, "America/New_York"),      # 8 AM Eastern; cron fires at 12:00 and 13:00 UTC and the
}                                                  # script skips the one that isn't 8 AM there (daylight saving)


def data_dir(dry_run=False):
    path = os.path.join(REPO, "data", "dryrun" if dry_run else "")
    os.makedirs(os.path.join(path, "agent_status"), exist_ok=True)
    return path


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def next_run(agent, after=None):
    """Next time a daily schedule fires, as ISO text in server time (None if unknown).
    Worked out in the schedule's own time zone, so 8 AM New York stays 8 AM across daylight saving."""
    spec = SCHEDULES.get(agent)
    if not spec:
        return None
    hour, minute, tz = spec
    after = (after or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz))
    nxt = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= after:
        nxt = (after + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return nxt.astimezone().isoformat(timespec="seconds")


def is_local_time(agent, now=None):
    """True when it's the scheduled hour in the agent's time zone (used by the cron guard)."""
    hour, _, tz = SCHEDULES[agent]
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz)).hour == hour


def write_json_atomic(path, data):
    """Write to a temp file, then rename over the real one, so a reader never sees half a file."""
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def read_runs(agent=None, days=7, dry_run=False):
    """Past runs (newest last), optionally for one agent and only the last N days."""
    path = os.path.join(data_dir(dry_run), "agent_runs.jsonl")
    if not os.path.exists(path):
        return []
    cutoff = time.time() - days * 86400
    runs = []
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue                     # skip a damaged line instead of failing the whole report
            if agent and r.get("agent") != agent:
                continue
            if r.get("finished_ts", 0) >= cutoff:
                runs.append(r)
    return runs


class _SafeStream:
    """stdout/stderr that never crashes the agent. If whatever reads the output goes away (`| tee` stopped by Ctrl-C,
    a closed terminal), printing raises BrokenPipeError; this switches to /dev/null instead, so the agent can still
    save its progress and record how the run ended."""

    def __init__(self, stream):
        self._stream = stream

    def _swap(self):
        self._stream = open(os.devnull, "w")

    def write(self, text):
        try:
            return self._stream.write(text)
        except (BrokenPipeError, OSError, ValueError):
            self._swap()
            return len(text)

    def flush(self):
        try:
            self._stream.flush()
        except (BrokenPipeError, OSError, ValueError):
            self._swap()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def keep_output_safe():
    for name in ("stdout", "stderr"):
        if not isinstance(getattr(sys, name), _SafeStream):
            setattr(sys, name, _SafeStream(getattr(sys, name)))


STOP_EXCEPTIONS = (KeyboardInterrupt, BrokenPipeError)   # Ctrl-C / output closed: the run was stopped, it didn't crash


class Run:
    def __init__(self, agent, steps, dry_run=False):
        self.agent, self.steps, self.dry_run = agent, steps, dry_run
        self.dir = data_dir(dry_run)
        self.status_path = os.path.join(self.dir, "agent_status", f"{agent}.json")
        self.started = time.time()
        self.step_no = 0
        self.api_calls = 0
        self.finished = False
        self._progress_saved = 0.0
        keep_output_safe()
        self.status = {
            "agent": agent, "state": "running", "step": "Starting", "step_no": 0, "steps": steps,
            "started_at": now_iso(), "updated_at": now_iso(), "dry_run": dry_run, "pid": os.getpid(),
            "next_run": next_run(agent),
        }
        # Keep the last finished run's numbers visible on the dashboard while this one runs
        try:
            with open(self.status_path) as f:
                prev = json.load(f)
            self.status["last"] = prev.get("last") if prev.get("state") == "running" else {
                k: prev.get(k) for k in ("state", "finished_at", "duration_s", "metrics", "summary", "urgent")}
        except (OSError, ValueError):
            pass
        self._save()

    def _save(self):
        self.status["updated_at"] = now_iso()
        write_json_atomic(self.status_path, self.status)

    def step(self, label):
        """Mark the start of the next step: 'Checking images' (3 of 6)."""
        self.step_no += 1
        self.status.update(step=label, step_no=self.step_no)
        self._save()
        print(f"[{self.agent}] {self.step_no}/{self.steps} {label}", flush=True)

    def progress(self, done, total, every_s=5):
        """During a long step: 'Checking 2800 cards (250 of 2,800)' on the board, saved at most every few seconds."""
        if time.time() - self._progress_saved < every_s and done < total:
            return
        self._progress_saved = time.time()
        self.status["detail"] = f"{done:,} of {total:,}"
        self._save()

    def finish(self, state, summary="", metrics=None, urgent=False, notes=None):
        """state: ok | warn | stopped (ended early on purpose; picks up next time) | error. Writes the history line
        and the final status."""
        self.finished = True
        duration = round(time.time() - self.started, 1)
        record = {
            "agent": self.agent, "state": state, "started_at": self.status["started_at"],
            "finished_at": now_iso(), "finished_ts": time.time(), "duration_s": duration,
            "metrics": metrics or {}, "summary": summary, "urgent": bool(urgent),
            "api_calls": self.api_calls, "notes": notes or [], "dry_run": self.dry_run,
        }
        with open(os.path.join(self.dir, "agent_runs.jsonl"), "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        self.status.pop("detail", None)
        self.status.update(state=state, step="Done", step_no=self.steps, finished_at=record["finished_at"],
                           duration_s=duration, metrics=record["metrics"], summary=summary,
                           urgent=bool(urgent), notes=record["notes"], next_run=next_run(self.agent))
        self.status["last"] = {k: record[k] for k in ("state", "finished_at", "duration_s", "metrics", "summary", "urgent")}
        self._save()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Ctrl-C or a closed output is a stop, not a crash: record "stopped" and exit quietly
        if exc_type and issubclass(exc_type, STOP_EXCEPTIONS):
            if not self.finished:
                how = "Ctrl-C" if issubclass(exc_type, KeyboardInterrupt) else "its output was closed"
                self.finish("stopped", summary=f"Stopped ({how})")
            return True
        # A real crash still leaves a record ("error") instead of a status stuck on "running"
        if exc_type and not self.finished:
            self.finish("error", summary=f"Crashed: {exc_type.__name__}", notes=[str(exc)[:300]])
        return False
