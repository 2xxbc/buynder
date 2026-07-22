# Buynder — Pokemon Card Market Tracker

**Live at [buyndermarket.com](https://buyndermarket.com)**

A full-stack web app for tracking Pokemon card prices, managing a collection, and monitoring portfolio profit/loss — built and self-hosted from scratch, with real users.

## What it does

- **Live market search** — search any Pokemon card and pull real-time pricing via the JustTCG API (7d/30d/90d price changes, historical min/max, per-condition pricing)
- **OCR card scanner** — snap a photo of a card and have it auto-identified using Tesseract OCR, then add it straight to your collection
- **Collection & sold tracking** — log cards you own, track condition-specific values, and record sales
- **Portfolio dashboard** — realized and unrealized profit/loss across your whole collection
- **Card sharing** — share a collection or watchlist view with other users

## Tech stack

**Frontend:** React, Tailwind CSS, Vite
**Backend:** Python, Flask, Gunicorn
**Database:** MySQL
**Infrastructure:** Self-hosted on a home server, managed with `systemd` services, exposed to the internet via a Cloudflare Tunnel (no port forwarding)
**External APIs:** JustTCG (pricing data), Tesseract (OCR)

## Architecture notes

- Backend runs as a `systemd` service (`buynder-api`) behind Gunicorn with multiple workers
- Frontend is built and served as a static `systemd`-managed service (`buynder-web`)
- All external traffic routes through a Cloudflare Tunnel, so the origin server has no exposed ports
- Price history and card metadata are cached in MySQL to avoid re-fetching from JustTCG on every request
- Diagnosed and fixed a real production incident where rapid card additions caused Gunicorn worker timeouts — root cause was re-fetching full price history (up to 365 data points) on every add; mitigated with an increased worker timeout, with a caching fix planned to eliminate the redundant fetch entirely

## Running it locally

**Backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own DB credentials + JustTCG API key
python app.py
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

You'll also need a MySQL instance with the schema set up (see `products` and `price_history` tables referenced in `app.py`).

## Status

Actively developed. Recent/upcoming work includes foreign card translation, deck search integration (YouTube + Limitless TCG), and Discord/web push notifications for price alerts.

## Screenshots

*(add a screenshot or two of the Market page and Portfolio dashboard here — recruiters skim, and a picture goes a long way)*

---

Built by [Daevon Wing](https://github.com/2xxbc)
