#!/usr/bin/env bash
# switch-to-caddy.sh: move the live site (buynder-web, port 5180) from `vite preview` to Caddy.
# Run it ONCE, with sudo:   sudo ~/pokemarket/deploy/switch-to-caddy.sh
# If any check fails afterwards, it puts the old unit back by itself and says "ROLLED BACK".
# Ends with exactly one of:  SWITCH OK  /  ROLLED BACK: <reason>

set -Eeuo pipefail                                   # -E: error trap also works inside functions; -e stop at the first error; -u unset variables are errors; pipefail: pipes fail if any part fails

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root, found from this script's own folder (deploy/)
UNIT=/etc/systemd/system/buynder-web.service             # where systemd reads the live site's service definition
NEW_UNIT="$REPO/deploy/buynder-web.service"              # our Caddy version of that file
CADDYFILE="$REPO/deploy/Caddyfile"                       # Caddy's config, read straight from the repo
OWNER="${SUDO_USER:-youruser}"                             # the real user behind sudo, so backups end up owned by you, not root
STAMP="$(date +%Y%m%d-%H%M%S)"                           # timestamp for the backup name, e.g. 20261023-173012
BACKUP="$REPO/deploy/backup/buynder-web.service.$STAMP"  # backup path (deploy/backup/ is in .gitignore)
SITE=https://buyndermarket.com                           # the public site, through Cloudflare
INSTALLED=0                                              # becomes 1 once the new unit is in place; tells the error handler to roll back

# ---- helpers ----

# rollback REASON: put the backup unit back, restart, re-check, print ROLLED BACK, exit with failure.
rollback() {
  set +e                                             # from here on, keep going even if a command fails: getting the old site back matters most
  trap - ERR                                         # don't let the error handler call rollback again while we're rolling back
  echo
  echo "Problem: $1"
  echo "Restoring the previous unit from $BACKUP ..."
  cp "$BACKUP" "$UNIT"                               # old vite preview unit back in place
  systemctl daemon-reload                            # make systemd re-read the restored file
  systemctl restart buynder-web                      # start the old server again
  if wait_for_port && [ "$(status "$SITE/")" = "200" ]; then   # is the site back?
    echo "Old setup is running again and $SITE answers 200."
  else
    echo "WARNING: the site still isn't answering after the rollback."
    echo "Look at: journalctl -u buynder-web -n 50"
  fi
  echo
  echo "ROLLED BACK: $1"
  exit 1                                             # report failure to whoever ran the script
}

# If any command fails unexpectedly after the new unit is installed, roll back instead of leaving the site half-switched.
on_error() {
  if [ "$INSTALLED" = "1" ]; then rollback "a command failed on line $1"; fi
  echo "Stopped on line $1 before anything was changed. The live site is untouched."
}
trap 'on_error $LINENO' ERR                          # run on_error with the failing line number whenever a command fails

# status URL: print only the HTTP status code (000 if no answer within 10 seconds).
status() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" || true   # '|| true' so a timeout is a value, not a script-stopping error
}

# wait_for_port: wait up to 15 seconds for something to answer on port 5180.
wait_for_port() {
  for _ in $(seq 1 15); do                           # try 15 times...
    [ "$(status http://localhost:5180/)" = "200" ] && return 0   # ...answered 200: done
    sleep 1                                          # ...not yet: wait a second
  done
  return 1                                           # never answered
}

# ---- 1. Pre-flight: change nothing until all of these pass ----

if [ "$(id -u)" -ne 0 ]; then                        # id -u is 0 only for root
  echo "Run this with sudo: sudo $0"; exit 1
fi
[ -f "$UNIT" ]                 || { echo "No $UNIT found. Nothing to switch."; exit 1; }
[ -f "$NEW_UNIT" ]             || { echo "Missing $NEW_UNIT"; exit 1; }
[ -f "$REPO/frontend/dist/index.html" ] || { echo "No build in frontend/dist. Run ./scripts/deploy.sh first."; exit 1; }
command -v caddy >/dev/null    || { echo "Caddy isn't installed: sudo apt install -y caddy"; exit 1; }
if grep -q 'caddy run' "$UNIT"; then                 # the live unit already runs Caddy?
  echo "buynder-web already runs Caddy. Nothing to do."; exit 0
fi

echo "Checking the Caddyfile..."
if ! caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then   # parse the config without starting anything
  echo "The Caddyfile is invalid. Nothing was changed. See: caddy validate --config $CADDYFILE --adapter caddyfile"
  exit 1
fi
echo "  Valid."

# ---- 2. Back up the current unit ----

mkdir -p "$REPO/deploy/backup"                       # -p: no error if the folder already exists
cp -p "$UNIT" "$BACKUP"                              # -p keeps the original file's date and permissions
chown "$OWNER:$OWNER" "$REPO/deploy/backup" "$BACKUP"   # hand both back to you (sudo made them root's)
echo "Backed up the current unit to $BACKUP"

# ---- 3. Install the new unit and restart ----

INSTALLED=1                                          # from now on, any failure means "roll back"
install -m 644 "$NEW_UNIT" "$UNIT"                   # copy it in; mode 644 = everyone may read, only root may change
systemctl daemon-reload                              # systemd caches unit files; this makes it re-read them
systemctl restart buynder-web                        # stop vite preview, start Caddy (a second or two of downtime)
echo "Restarted buynder-web on Caddy. Checking..."

# ---- 4. Checks ----

wait_for_port || rollback "nothing answered on port 5180 within 15 seconds"
systemctl is-active --quiet buynder-web || rollback "buynder-web isn't running"   # --quiet: no output, just success/failure
echo "  OK  port 5180 answers"

code="$(status "$SITE/")"
[ "$code" = "200" ] || rollback "$SITE/ answered $code instead of 200"
echo "  OK  $SITE/ returns 200"

code="$(status "$SITE/card/caddy-switch-check")"     # a React route: no such file, so Caddy must fall back to index.html
[ "$code" = "200" ] || rollback "$SITE/card/... answered $code instead of 200 (React-route fallback)"
echo "  OK  $SITE/card/... returns 200"

# -D - prints the response headers, -o /dev/null throws the page away; tr strips the \r that HTTP lines end with
headers="$(curl -s -D - -o /dev/null --max-time 10 "$SITE/" | tr -d '\r' || true)"
for h in X-Content-Type-Options X-Frame-Options Referrer-Policy Permissions-Policy Content-Security-Policy-Report-Only; do
  echo "$headers" | grep -qi "^$h:" || rollback "the public site is missing the $h header"   # -q quiet, -i ignore upper/lower case
done
echo "  OK  security headers present"

# ---- 5. Done ----

trap - ERR                                           # switch finished; turn off the automatic rollback
echo
echo "Backup of the old unit: $BACKUP"
echo "To switch back by hand: see deploy/README.md (\"Switch back to vite preview\")"
echo "SWITCH OK"
