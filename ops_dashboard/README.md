# ops_dashboard/: the TV board for the ops agents

A separate, **read-only** Flask app on **port 5190**. It is not part of `app.py` and is not behind the Cloudflare tunnel.

- `GET /`: the dark showroom board. One card per agent (status light, last run, how long it took, key numbers, next run, 7-day sparkline), a health strip (site, API, public API, disk, newest backup), and a scrolling log line. It refreshes every 10 s. A red **STALE** banner appears if the board hasn't got fresh data for 35 s, and a **STALE**/"Late" badge appears on an agent that missed its daily run.
- `GET /api/status`: the same data as JSON, plus `overall` (ok/warn/error), `urgent`, and `spoken_summary`: 1-2 plain sentences, no emoji, for text-to-speech. Counts only: no usernames or emails.

It only reads `data/agent_status/*.json`, `data/agent_runs.jsonl`, `agents.log`, the newest backup's date and size, and disk usage. Health checks are cached for 60 s, so the TV can't hammer the site.

## Who can open it
Only `10.0.0.0/24` (your LAN), `100.64.0.0/10` (Tailscale) and the server itself. Everyone else gets **403**, and so does anything that arrives through Cloudflare (requests carrying a `CF-Connecting-IP` header), even though the tunnel connects from `127.0.0.1`.

## Try it
```bash
cd ~/pokemarket
venv/bin/python ops_dashboard/dashboard.py --sample     # made-up data; open http://<server-ip>:5190
```
(Flask's built-in server, fine for trying. For the always-on version use the systemd unit below.)

## Run it all the time (you run these; sudo)
```bash
sudo cp ~/pokemarket/deploy/buynder-ops.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now buynder-ops
curl -s http://<server-ip>:5190/api/status | head -c 300; echo
```
If `ufw` is on: `sudo ufw allow from 10.0.0.0/24 to any port 5190` (and the same for `100.64.0.0/10` for Tailscale).

## The voice assistant (LazyAssistant on the Pi)
Its Flask server can simply call `http://<server-ip>:5190/api/status` and read `spoken_summary` aloud. Server-to-server calls don't need CORS. A browser page on the Pi may also call it directly: `http://localhost:8080` and `http://127.0.0.1:8080` are allowed in `dashboard.py` (`LOCAL_ORIGINS`). For a page on another machine, such as the Pi's, list its origin in `OPS_CORS_ORIGINS` in a systemd drop-in (`sudo systemctl edit buynder-ops`, then `[Service]` and `Environment=OPS_CORS_ORIGINS=http://<pi-ip>:8080`).

```python
# in LazyAssistant
import requests
def ops_status():
    s = requests.get("http://<server-ip>:5190/api/status", timeout=5).json()
    return s["spoken_summary"]          # e.g. "Everything is running normally. No new broken card images last night."
```

## Raspberry Pi kiosk (TV)
On Raspberry Pi OS (desktop), open the board full screen at login:
```bash
# 1. Don't let the screen blank
sudo raspi-config nonint do_blanking 1
# 2. Autostart Chromium in kiosk mode (Wayland / labwc, Pi OS Bookworm and later)
mkdir -p ~/.config/labwc
echo 'chromium-browser --kiosk --noerrdialogs --disable-infobars --incognito --check-for-update-interval=31536000 http://<server-ip>:5190 &' >> ~/.config/labwc/autostart
# 3. Reboot to test
sudo reboot
```
On older X11 Pi OS, put the same `chromium-browser ...` line in `~/.config/lxsession/LXDE-pi/autostart` with an `@` in front. The page scales its text to the screen width, so a 1080p TV across the room is readable. With "reduce motion" turned on, the log line stops scrolling.
