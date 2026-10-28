"""Things both agents need: settings from .env, the database, Discord, and the one LLM helper.

Secrets (API key, webhook URL, DB password) are only ever read from the environment and are
never printed: anything that might be shown goes through redact() first.
"""
import json
import os

import requests

MODEL = "claude-haiku-5-5"
MAX_API_CALLS = 5          # per run, across all summaries
SECRET_VARS = ("ANTHROPIC_API_KEY", "OPS_DISCORD_WEBHOOK", "DB_PASSWORD", "DISCORD_WEBHOOK_URL", "POKETRACE_API_KEY")


def load_env():
    """Load .env into the environment (real runs only; --sample runs never touch it).
    Always the live app's .env (like scripts/check_sets.py), so a test copy of the repo finds it too."""
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/pokemarket/.env"))


def redact(text):
    """Replace any secret value that slipped into a message or error with [hidden]."""
    text = str(text)
    for var in SECRET_VARS:
        value = os.getenv(var)
        if value and len(value) > 6:
            text = text.replace(value, "[hidden]")
    return text


def db_connect():
    import mysql.connector
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME", "pokemarket"))


# ---------------------------------------------------------------- Discord

def send_discord(content, files=None, dry_run=False):
    """Post to the OPS webhook (to you). files: [(filename, bytes, mime)].
    Returns (ok, problem). Dry runs print instead of sending."""
    if dry_run:
        print("\n----- Discord message (dry run, not sent) -----")
        print(content)
        for name, data, _ in files or []:
            print(f"[attachment: {name}, {len(data)} bytes]")
        print("-----------------------------------------------\n")
        return True, None
    url = os.getenv("OPS_DISCORD_WEBHOOK")
    if not url:
        return False, "OPS_DISCORD_WEBHOOK is not set in .env"
    payload = {"content": content[:2000], "allowed_mentions": {"parse": []}}   # never ping @everyone
    try:
        if files:
            multipart = {f"files[{i}]": (name, data, mime) for i, (name, data, mime) in enumerate(files)}
            r = requests.post(url, params={"wait": "true"}, data={"payload_json": json.dumps(payload)},
                              files=multipart, timeout=30)
        else:
            r = requests.post(url, params={"wait": "true"}, json=payload, timeout=30)
        if r.status_code in (200, 204):
            return True, None
        return False, f"Discord answered HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, redact(f"Discord request failed: {type(e).__name__}")


def fit_discord(lines, limit=1990):
    """Join lines, cutting whole lines (not mid-word) to stay under Discord's 2000-character cap."""
    out, size = [], 0
    for line in lines:
        if size + len(line) + 1 > limit:
            out.append("…(cut to fit; see the attached file)")
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out)


# ---------------------------------------------------------------- the LLM (summaries only)

class LLM:
    """Writes short summaries from facts the agent already collected with plain code.
    At most MAX_API_CALLS per run. Never retries: a rate limit, overload or any API error
    returns (None, reason) and the agent falls back to raw numbers and marks the run "warn"."""

    def __init__(self, run, dry_run=False):
        self.run, self.dry_run = run, dry_run
        self.client = None
        self.blocked = None     # after a rate limit / overload / network error: no more calls this run

    def summarize(self, system, facts, max_tokens=600):
        if self.dry_run:
            return None, "dry run: no API call made"
        if self.blocked:
            return None, self.blocked
        if self.run.api_calls >= MAX_API_CALLS:
            return None, f"API call limit reached ({MAX_API_CALLS} per run)"
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None, "ANTHROPIC_API_KEY is not set in .env"
        try:
            import anthropic
        except ImportError:
            return None, "the anthropic package is not installed (venv/bin/pip install anthropic)"

        if self.client is None:
            # max_retries=0: the SDK would otherwise retry 429/5xx on its own
            self.client = anthropic.Anthropic(max_retries=0, timeout=60.0)
        self.run.api_calls += 1
        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},       # a short summary doesn't need thinking, and it can't
                output_config={"effort": "low"},     # use up max_tokens before the text (Haiku 5.5: ok at effort <= high)
                system=system,
                messages=[{"role": "user", "content": facts}],
            )
        except anthropic.RateLimitError:
            self.blocked = "rate limited by the Anthropic API (not retried)"
            return None, self.blocked
        except anthropic.APIStatusError as e:
            if e.status_code in (529, 503) or e.status_code >= 500:
                self.blocked = f"Anthropic API is {'overloaded' if e.status_code == 529 else 'having trouble'} (HTTP {e.status_code}, not retried)"
                return None, self.blocked
            return None, f"Anthropic API error: HTTP {e.status_code} (not retried)"
        except anthropic.APIConnectionError:
            self.blocked = "could not reach the Anthropic API (not retried)"
            return None, self.blocked

        if response.stop_reason == "refusal":
            return None, "the model declined to write this summary"
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            return None, f"empty summary (stop reason: {response.stop_reason})"
        return text, None
