#!/bin/bash
# Nightly MySQL backup — keeps last 14 days
BACKUP_DIR="/path/to/buynder/backups"
DATE=$(date +%Y-%m-%d)
source /path/to/buynder/.env 2>/dev/null

mysqldump --no-tablespaces -u "$DB_USER" -p"$DB_PASSWORD" pokemarket 2>/dev/null | gzip > "$BACKUP_DIR/pokemarket-$DATE.sql.gz"

# Delete backups older than 14 days
find "$BACKUP_DIR" -name "pokemarket-*.sql.gz" -mtime +14 -delete

echo "$(date): backup done — $(ls -lh $BACKUP_DIR/pokemarket-$DATE.sql.gz 2>/dev/null | awk '{print $5}')"
