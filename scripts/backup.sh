#!/bin/bash
set -e

BACKUP_DIR="/backups/gca"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/gca_$BACKUP_DATE.sql"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Backup iniciado..."
docker-compose exec -T gca-postgres pg_dump -U postgres gca > "$BACKUP_FILE"
gzip "$BACKUP_FILE"

echo "[$(date)] Backup: $BACKUP_FILE.gz"
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
echo "[$(date)] Concluído"
