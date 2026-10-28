#!/usr/bin/env bash
# migrate.sh: back up the database, check the backup, then apply ONE migration file.
# Usage (you run it, no sudo):   ~/pokemarket/db/migrate.sh db/migrations/001_condition_prices.sql
# Run this by hand only: it changes the live database.

set -euo pipefail                                     # stop at the first error, unset variables are errors

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root (this script lives in db/)
cd "$REPO"

FILE="${1:-}"                                         # the migration to apply, e.g. db/migrations/001_condition_prices.sql
[ -n "$FILE" ] && [ -f "$FILE" ] || { echo "Usage: db/migrate.sh db/migrations/<file>.sql"; exit 1; }
NAME="$(basename "$FILE" .sql)"                       # 001_condition_prices
BACKUP="$REPO/backups/pre-$NAME-$(date +%Y%m%d-%H%M).sql.gz"

# Read DB_USER / DB_PASSWORD / DB_NAME from .env without printing them.
set -a; source "$REPO/.env"; set +a                   # set -a: every variable defined while sourcing gets exported
DB="${DB_NAME:-pokemarket}"

# Give mysql/mysqldump the password through a private temp file instead of the command line
# (anything on the command line is visible to every user via `ps`).
CNF="$(mktemp)"                                       # e.g. /tmp/tmp.Ab12Cd
trap 'rm -f "$CNF"' EXIT                              # delete it when the script ends, however it ends
chmod 600 "$CNF"                                      # only you can read it
printf '[client]\nuser=%s\npassword=%s\nhost=%s\n' "$DB_USER" "$DB_PASSWORD" "${DB_HOST:-localhost}" > "$CNF"

# 1. Backup. --single-transaction = a consistent snapshot without locking the site's tables.
# --no-tablespaces: skip tablespace info, which needs the PROCESS privilege our DB user doesn't have
# (MySQL 8 warns without it). A plain InnoDB database like ours has no tablespaces to lose.
echo "Backing up $DB to $BACKUP ..."
mysqldump --defaults-extra-file="$CNF" --single-transaction --routines --no-tablespaces "$DB" | gzip > "$BACKUP"

# 2. Check the backup: a valid gzip, and mysqldump's last line says it finished.
gzip -t "$BACKUP" || { echo "Backup is not a valid gzip file. Stopping; nothing was changed."; exit 1; }
if ! zcat "$BACKUP" | tail -1 | grep -q 'Dump completed'; then
  echo "Backup looks incomplete (no 'Dump completed' line). Stopping; nothing was changed."; exit 1
fi
echo "  Backup OK: $(du -h "$BACKUP" | cut -f1)"

# 3. Apply the migration. mysql stops at the first failing statement.
echo "Applying $FILE ..."
mysql --defaults-extra-file="$CNF" "$DB" < "$FILE"
echo "  Applied."

echo
echo "Done. To undo: see the 'Undo' lines at the bottom of $FILE,"
echo "or restore everything:  zcat $BACKUP | mysql -u <user> -p $DB"
echo "Then restart the API so it notices the new tables:  sudo systemctl restart buynder-api"
