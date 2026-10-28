# Buynder — Pokémon Card Market Tracker

**Live at [buyndermarket.com](https://buyndermarket.com)**

A full-stack web app for tracking Pokémon card prices, managing a collection, and watching portfolio profit/loss. I built it from scratch and self-host it on a home server, and it has real users.

## What it does

- **Market search.** Search by card name, set words ("absol ex magma") or card number ("173/167"), with paging past the first 20 results.
- **Honest prices by condition.** Near Mint through Damaged, from TCGplayer and eBay sales. A price only counts if there was a real sale in the last 30 days. Thin data gets a "Low data" label instead of a made-up number, and every price shows its sale count.
- **Graded prices.** PSA, CGC, BGS and more, from eBay sales, with the same low-data rules.
- **Recent sales and price history** charts on every card page.
- **Collection, sold history and portfolio.** Log what you own with condition, quantity and price paid, record sales, and see realized and unrealized P&L valued by each card's actual condition.
- **Quick add.** Search, pick, set condition/quantity/price and add several cards in a row without leaving the Collection page.
- **Watchlist, trades and sharing.** Share a collection or watchlist with other users.
- **Trending.** Biggest movers and the most-sold cards of the last 30 days, plus a featured set on the home page.
- **Card scanner.** Point your camera at a card (or upload a photo); the server reads it with Tesseract OCR and finds the card.

Behind the scenes:
- **Nightly market sweep.** A 3 AM job refreshes ~43,000 cards across every tracked English set, within the API's daily request budget.
- **Ops agents and status board.** Small Python jobs run after the sweep. The Image Doctor finds card images that stopped loading. The Price Doctor finds played conditions priced above Near Mint and works out why (stale or thin data). A daily ops report goes to a private Discord channel; it collects its numbers with plain code and uses the Claude API only to write a short summary. A read-only status board (LAN only) shows each job's last run on a TV.

## Tech stack

**Frontend:** React 19, Vite, Tailwind CSS v4, React Router, Chart.js
**Backend:** Python 3.12, Flask, Gunicorn, Flask-Login, Flask-Limiter
**Database:** MySQL 8 (schema in `db/schema.sql`, changes in `db/migrations/`)
**Data:** PokeTrace API (cards, prices, sales, images)
**Infrastructure:** Self-hosted Ubuntu server. Caddy serves the built frontend with security headers, systemd runs the services, and a Cloudflare Tunnel exposes it to the internet without opening any ports. Nightly database backups.

## Architecture notes

- The API runs under Gunicorn as a systemd service. Caddy serves the static build and passes `/api/*` to it, so the login cookie stays first-party.
- The login cookie is HTTPS-only for public visitors (through the tunnel) and plain for LAN testing, decided per request.
- A second API copy on port 5051 auto-reloads for development, so the live site is never touched while testing.
- Deploys are one script (`scripts/deploy.sh`): it refuses unless the tree is clean on `master`, tags the release, builds, restarts and health-checks, and prints the rollback command.
- Card prices are cached in MySQL by the nightly sweep, so pages don't hit the pricing API on every view.

## Running it locally

You need Python 3.12, Node 20+, MySQL 8, Tesseract (`sudo apt install tesseract-ocr`, for the scanner) and a [PokeTrace](https://poketrace.com) API key.

**Database**
```bash
mysql -u root -p -e "CREATE DATABASE pokemarket; CREATE USER 'buynder'@'localhost' IDENTIFIED BY 'change-me'; GRANT ALL ON pokemarket.* TO 'buynder'@'localhost';"
mysql -u buynder -p pokemarket < db/schema.sql
```

**Backend**
```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in your DB login, a SECRET_KEY and your PokeTrace key
./scripts/dev-api.sh          # the API on http://localhost:5051, reloads when app.py changes
```

**Cards and prices**
```bash
venv/bin/python load_all_sets.py --apply --add scripts/approved_sets.txt   # which sets to track
venv/bin/python sync_market.py                                             # first sweep (uses PokeTrace requests)
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

To open the dev site from another device on your network, add its address to `DEV_HOSTS` in `.env` (for example `DEV_HOSTS=192.168.1.20`) and restart both servers.

## Screenshots

<img width="1444" height="815" alt="image" src="https://github.com/user-attachments/assets/f855664c-da6e-4b59-8252-a6b7ce6bada2" />

<img width="1890" height="741" alt="image" src="https://github.com/user-attachments/assets/571e8812-862a-43aa-af95-38938b48cd7f" />

<img width="1274" height="768" alt="image" src="https://github.com/user-attachments/assets/b9c0e570-a705-4ef1-a03d-6f9303bd4ce4" />

---

Built by [Daevon Wing](https://github.com/2xxbc)
