#!/bin/bash
# Dagelijkse backup van de Meal Planner.
#
# De SQLite database bevat alles waar de app om draait: de aankoopgeschiedenis,
# eigen recepten en planningen. Die zit in één bestand, dus zonder deze backup is
# één schijffout of een misgelopen migratie definitief verlies.
#
# Gebruikt de sqlite3 backup-API in plaats van cp: die maakt een consistente kopie
# terwijl de app gewoon doorschrijft. Een simpele cp kan een half geschreven
# transactie meenemen en levert dan een corrupte kopie op.
#
# Installatie: zie server_config/README.md

set -euo pipefail

APP_DIR="${APP_DIR:-/home/admin/meal-planner}"
BACKUP_DIR="${BACKUP_DIR:-/home/admin/meal-planner-backups}"
BEWAAR_DAGEN="${BEWAAR_DAGEN:-30}"

STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

# Database: consistente online kopie, daarna comprimeren.
python3 - "$APP_DIR/data/app.db" "$BACKUP_DIR/app.db.$STAMP" <<'PY'
import sqlite3, sys
bron, doel = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
dst = sqlite3.connect(doel)
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
gzip -f "$BACKUP_DIR/app.db.$STAMP"

# Config bevat de wachtwoord-hashes en groepsinstellingen; even klein als waardevol.
if [ -f "$APP_DIR/config/settings.json" ]; then
  cp "$APP_DIR/config/settings.json" "$BACKUP_DIR/settings.json.$STAMP"
fi

# Integriteit controleren: een backup die je niet kan lezen is geen backup.
if ! gzip -t "$BACKUP_DIR/app.db.$STAMP.gz"; then
  echo "FOUT: backup $STAMP is beschadigd" >&2
  exit 1
fi

# Opruimen.
find "$BACKUP_DIR" -name 'app.db.*.gz' -mtime "+$BEWAAR_DAGEN" -delete
find "$BACKUP_DIR" -name 'settings.json.*' -mtime "+$BEWAAR_DAGEN" -delete

AANTAL=$(find "$BACKUP_DIR" -name 'app.db.*.gz' | wc -l)
GROOTTE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "Backup $STAMP ok. $AANTAL databasebackups, $GROOTTE totaal."
