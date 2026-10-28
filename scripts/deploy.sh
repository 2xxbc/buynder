#!/usr/bin/env bash
# deploy.sh — make whatever is on master live on buyndermarket.com.
# Run it yourself from anywhere:  ./scripts/deploy.sh
# It asks for your sudo password once (to restart the services).

# -e: stop at the first command that fails
# -u: treat a typo'd variable name as an error instead of an empty string
# -o pipefail: a pipeline fails if ANY command in it fails, not just the last one
set -euo pipefail

# Find the repo folder from where this script lives (scripts/ is one level down),
# so the script works no matter which folder you run it from.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"                                         # do everything from the repo root

# ---- 1. Safety checks: only deploy a clean master ----

BRANCH="$(git branch --show-current)"              # name of the branch you're on
if [ "$BRANCH" != "master" ]; then                 # anything but master → stop
  echo "Refusing to deploy: you're on '$BRANCH'. Run: git checkout master"
  exit 1                                           # exit code 1 = "failed"
fi

if [ -n "$(git status --porcelain)" ]; then        # --porcelain prints one line per changed/untracked file
  echo "Refusing to deploy: you have uncommitted changes:"
  git status --short                               # show them so you know what to commit or stash
  exit 1
fi

# ---- 2. Bookmark this exact version with a tag ----

TAG="deploy-$(date +%Y%m%d-%H%M)"                  # e.g. deploy-20261023-2140 (year month day - hour minute)
git tag "$TAG"                                     # tag = a permanent name for this commit (fails if you deploy twice in one minute)
echo "Tagged this deploy as $TAG"

# ---- 3. Build the frontend ----

cd frontend                                        # the React app lives here
npm ci                                             # clean install: wipes node_modules and installs the exact versions in package-lock.json
npm run build                                      # Vite compiles src/ into frontend/dist/, the files the live site serves
cd "$REPO"                                         # back to the repo root

# ---- 4. Restart the live services ----

sudo systemctl restart buynder-api buynder-web     # api = Flask/gunicorn (picks up app.py changes); web = serves frontend/dist
echo "Services restarted. Waiting 3 seconds for them to start..."
sleep 3                                            # give gunicorn and the web server a moment to start listening

# ---- 5. Health checks ----

# check NAME URL: fetch URL and print OK if it answers with HTTP 200, FAIL otherwise.
check() {
  local code                                       # 'local' keeps the variable inside this function
  # -s silent, -o /dev/null throw away the page, -w print only the status code, --max-time give up after 10s
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$2" || true)"   # '|| true' so a timeout doesn't stop the script (set -e)
  if [ "$code" = "200" ]; then
    echo "  OK    $1  ($2)"
  else
    echo "  FAIL  $1  ($2) answered: ${code:-nothing}"
    FAILED=1                                       # remember that something failed
  fi
}

FAILED=0
echo "Health checks:"
check "API (local)"   "http://localhost:5050/"           # the Flask root route answers "PokeMarket backend is running!"
check "API (public)"  "https://api.buyndermarket.com/"   # same API, through the Cloudflare tunnel
check "Site (public)" "https://buyndermarket.com/"       # the React site, through the tunnel

# ---- 6. How to undo ----

# The rollback target: the newest deploy tag that points to a DIFFERENT commit than this deploy.
# Sorted by NAME: deploy-YYYYMMDD-HHMM names sort in time order. (Not by "creatordate": for these
# simple tags that's the commit's date, so two deploys of the same commit tied and the order broke.)
# Skipping same-commit tags means re-deploying the same code never offers "roll back to itself".
HEAD_COMMIT="$(git rev-parse HEAD)"                # the commit we just deployed
PREV=""
for t in $(git tag -l 'deploy-*' --sort=-refname); do     # newest name first
  if [ "$(git rev-list -n 1 "$t")" != "$HEAD_COMMIT" ]; then   # rev-list -n 1 = the commit a tag points to
    PREV="$t"
    break                                          # first different one = the newest older version
  fi
done
PREV="${PREV:-pre-redesign}"                       # first deploy ever? fall back to the pre-redesign tag

echo
echo "Deployed $TAG."
echo "To roll back to $PREV:"
echo "  git checkout $PREV                       # put the old files in place (detached HEAD, that's fine)"
echo "  (cd frontend && npm ci && npm run build) # rebuild the old frontend"
echo "  sudo systemctl restart buynder-api buynder-web"
echo "  git checkout master                      # come back to master (dist/ keeps the old build until the next deploy)"

if [ "$FAILED" = "1" ]; then                       # make the whole script report failure if any check failed
  echo
  echo "Something FAILED. Look at: journalctl -u buynder-api -n 50   (and buynder-web)"
  exit 1
fi
