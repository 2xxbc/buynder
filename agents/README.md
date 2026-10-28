# agents/: ops agents

Small Python scripts that **collect facts with plain code** (database counts, log files, HTTP checks) and use Claude (`claude-haiku-5-5`) **only to write the summary**. If Claude isn't available (no key, rate limit, overload), you get the raw numbers and the run is marked `warn`. They never retry an API call, and they make at most 5 calls per run.

| Agent | When | Sends you |
|---|---|---|
| `image_doctor.py` | Nightly, right after the 3 AM sweep | Newly broken / fixed / still broken card images, `broken_images.csv` attached, a 1-2 line pattern note. "No new broken images ✅" on quiet nights. (The weekly PokeTrace email draft is in the Ops report, not here.) |
| `price_doctor.py` | Nightly, after the sweep and Image Doctor (same lock) | Cards whose played condition (LP/MP/HP/Damaged) is priced at least 5% and $1 above Near Mint on the same source, with a likely cause (stale NM / thin data / unclear): counts, the worst 10, `data/mispriced_cards.csv` attached. Up to 3,000 PokeTrace requests a run (1 card detail each), stops when fewer than 2,000 would be left today, resumes where it stopped. Every fetched detail is saved, so `--from-saved` re-applies a new threshold with 0 requests. |
| `ops_report.py` | Daily 8 AM US Eastern (follows daylight saving) | 5-10 lines: users, usage, sweep, health, backups, failed logins / rate limits, unusual vs the last 7 days. 🚨 URGENT when the site/API is down, the backup is >36 h old, or the sweep failed. Mondays: THE PokeTrace data-issues email **draft** (condition prices first, then set naming, broken images) attached (`poketrace_draft.txt` + `broken_images.csv`), from `agents/poketrace_issues.json`; never sent to PokeTrace. |

`runlog.py` writes `data/agent_runs.jsonl` (one line per run) and `data/agent_status/<agent>.json` (live: current step, "3 of 7"). The ops dashboard reads both. Dry runs use `data/dryrun/` instead, so tests never mix with real history.

## Setup (you do these)

1. **Package** (no sudo, into the project's venv, 5.8 MB download, about 25 MB unpacked, with 15 helper packages):
   ```bash
   ~/pokemarket/venv/bin/pip install anthropic==2.3.0
   ```
   Pinned so a future major version can't change things under you. It also nudges `idna` (3.11 → 3.20) and
   `typing_extensions` (4.15 → 4.16) up a minor version, because the new packages need them.
   Everything else it uses (`requests`, `mysql-connector-python`, `python-dotenv`) is already installed for the API.
2. **Two lines in `.env`** (add them yourself; never commit `.env`):
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   OPS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...   # a channel only you can see
   ```
3. **Migration 002** (for the "active users" count): `~/pokemarket/db/migrate.sh db/migrations/002_users_last_seen.sql`. The API notices the new column within 10 minutes, no restart needed. Until then the report says "n/a (needs migration 002)".
4. **Try them, sending nothing:**
   ```bash
   cd ~/pokemarket
   venv/bin/python agents/image_doctor.py --dry-run --max-checks 200
   venv/bin/python agents/ops_report.py --dry-run
   ```
   Then once for real (drop `--dry-run`) to see the Discord messages.
5. **Cron lines** (`crontab -e`, add at the bottom):
   ```
   # image_doctor: starts 03:15 and waits (flock -w) until the 03:00 sweep releases its lock, so it runs right after it
   15 3 * * * flock -w 7200 /tmp/sweep.lock /path/to/buynder/venv/bin/python /path/to/buynder/agents/image_doctor.py >> /path/to/buynder/agents.log 2>&1
   # ops_report: 8 AM US Eastern. The server's cron only knows UTC, and 8 AM Eastern is 12:00 UTC in summer (EDT)
   # but 13:00 UTC in winter (EST). So it fires at both; --scheduled makes the script quit unless it's 8 AM in New York.
   0 12,13 * * * /path/to/buynder/venv/bin/python /path/to/buynder/agents/ops_report.py --scheduled >> /path/to/buynder/agents.log 2>&1
   ```
   If you change these times, also change `SCHEDULES` in `runlog.py` (it powers "next run" on the dashboard).

## Good to know
- **First image_doctor run:** your existing `broken_images.csv` (1,042 cards) becomes the starting list, and the original is copied to `data/broken_images.before-image-doctor.csv`. All ~43k market cards count as "new" the first night, so the 6,000-per-night cap spreads that first full pass over about a week. After that, only new or changed image URLs plus the known-broken ones are checked (usually a few hundred).
- **Polite checking:** HEAD requests only (no downloads), 6 at a time, a short pause per request, and a User-Agent that names the site. Timeouts and "busy" answers count as *unknown*, not broken, and are retried the next night.
- **Never contacts PokeTrace:** no `api.poketrace.com` calls and no email. It only loads the public image files on `cdn.poketrace.com`, like a visitor's browser does.
- **Privacy:** reports contain counts only, never usernames or emails. Failed logins are logged by `app.py` as just `login failed`.
