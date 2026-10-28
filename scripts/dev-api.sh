#!/usr/bin/env bash
# dev-api.sh — run a second copy of the Flask API on port 5051 for testing.
# The dev site (npm run dev, port 5173) talks to this one; the live site keeps using 5050.
# Run it in its own terminal:  ./scripts/dev-api.sh     Stop it with Ctrl+C.

set -euo pipefail                                  # stop at the first error, error on unset variables

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root, found from this script's folder
cd "$REPO"                                         # gunicorn imports app.py from the current folder

# exec: replace this shell with gunicorn, so Ctrl+C goes straight to gunicorn
# venv/bin/gunicorn: the same gunicorn the live API uses, from the project's Python virtualenv
# --bind 0.0.0.0:5051: listen on every network (LAN + Tailscale) on port 5051, not the live 5050
# --workers 1: one worker is plenty for one tester (and keeps the in-memory rate limits in one place)
# --reload: restart automatically whenever app.py changes, so new backend code is live in ~1 second
# --timeout 120: same as live; slow PokeTrace calls get 2 minutes before gunicorn gives up
# app:app: "in app.py, use the variable named app" (the Flask app)
exec venv/bin/gunicorn --bind 0.0.0.0:5051 --workers 1 --reload --timeout 120 app:app
