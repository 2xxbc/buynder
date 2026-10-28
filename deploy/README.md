# deploy/: server config that lives outside the repo

| File | Installed to | What it is |
|---|---|---|
| `Caddyfile` | stays here (the unit points at it) | How Caddy serves `frontend/dist` on port 5180: React-route fallback, compression, cache and security headers |
| `buynder-web.service` | `/etc/systemd/system/buynder-web.service` | Runs Caddy as `youruser` (replaces `vite preview`) |
| `buynder-web.vite-preview.service` | only when switching back | Copy of the old `vite preview` unit |
| `switch-to-caddy.sh` | run once with sudo | Steps 3–6 below in one script, with automatic rollback |
| `backup/` (git-ignored) | | Timestamped copies of the live unit, made by `switch-to-caddy.sh` |

Because the unit reads `deploy/Caddyfile` straight from the repo, **switch over only after Phase 1 is merged into `master`**. Otherwise checking out `master` would remove the file Caddy needs.

## Switch to Caddy: the one-command way

After steps 1–2 below (install Caddy, disable the package's own `caddy` service):
```bash
sudo ~/pokemarket/deploy/switch-to-caddy.sh
```
It validates the Caddyfile, backs up the live unit to `deploy/backup/`, installs the new unit, restarts `buynder-web`, then checks port 5180, `https://buyndermarket.com/`, a `/card/` route and the security headers. If any check fails it restores the backup by itself and prints `ROLLED BACK: <reason>`; otherwise `SWITCH OK`.

## Switch to Caddy: step by step (each needs sudo except 3 and 6)

```bash
# 1. Install Caddy from Ubuntu's own repo (2.6.2, one ~40 MB program, no other services needed)
sudo apt update && sudo apt install -y caddy

# 2. The package also turns on its own "caddy" service, which wants port 80 (already taken here).
#    We don't use it: buynder-web runs Caddy with our config instead. Stop it and keep it off.
sudo systemctl disable --now caddy

# 3. Check our config for mistakes (no sudo; prints "Valid configuration")
caddy validate --config ~/pokemarket/deploy/Caddyfile --adapter caddyfile

# 4. Put the new unit in place (overwrites the vite preview one; a copy is in this folder)
sudo cp ~/pokemarket/deploy/buynder-web.service /etc/systemd/system/buynder-web.service

# 5. Tell systemd the unit file changed, then restart the site on Caddy (a second or two of downtime)
sudo systemctl daemon-reload && sudo systemctl restart buynder-web

# 6. Check (no sudo)
curl -sI http://localhost:5180/ | head -15                                    # 200, plus the security headers
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5180/card/anything   # 200: React handles the route
curl -sI http://localhost:5180/assets/ | grep -i cache                         # long cache only on /assets
```
Then open https://buyndermarket.com, click around, and watch the browser console for `Content-Security-Policy` report-only warnings.

`./scripts/deploy.sh` keeps working unchanged: it rebuilds `dist/` and restarts `buynder-web`.

## Switch back to vite preview

```bash
sudo cp ~/pokemarket/deploy/buynder-web.vite-preview.service /etc/systemd/system/buynder-web.service
sudo systemctl daemon-reload && sudo systemctl restart buynder-web
```

## Turning the CSP on for real
The `Content-Security-Policy-Report-Only` header only warns. After a few days with no console warnings, rename it to `Content-Security-Policy` in `Caddyfile`, commit, merge, and restart `buynder-web`. If a card image host is missing, add it to `img-src`.
