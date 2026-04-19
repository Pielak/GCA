#!/bin/bash
# DT-061 — Backup completo do GCA.
#
# Faz backup de:
#   1. Database `gca` (Postgres) via pg_dump comprimido
#   2. Volume `gca_gca-uploads-storage` (uploads de Ingestão) via tar
#   3. Database `gca_test` (opcional, --include-test) — útil pra debug
#
# Saída: $GCA_BACKUP_DIR (default: ~/gca-backups/) com 1 subdiretório
# por execução: gca_backup_YYYYMMDD_HHMMSS/
#   ├── db_gca.sql.gz
#   ├── db_gca_test.sql.gz   (se --include-test)
#   ├── uploads.tar.gz
#   └── manifest.json        (versão, hash, tamanhos, contadores)
#
# Uso:
#   ./scripts/backup.sh                  # backup gca + uploads
#   ./scripts/backup.sh --include-test   # também backup gca_test
#   ./scripts/backup.sh --retention 7    # mantém só últimos 7 dias
#
# Sem sudo, sem privilégios. Tudo dentro de $HOME.
# Retenção default: 30 dias.

set -euo pipefail

BACKUP_DIR="${GCA_BACKUP_DIR:-$HOME/gca-backups}"
RETENTION_DAYS=30
INCLUDE_TEST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-test) INCLUDE_TEST=1; shift;;
    --retention) RETENTION_DAYS="$2"; shift 2;;
    --dir) BACKUP_DIR="$2"; shift 2;;
    -h|--help)
      echo "Uso: $0 [--include-test] [--retention N] [--dir PATH]"
      echo "Defaults: dir=~/gca-backups, retention=30 dias"
      exit 0;;
    *) echo "Argumento desconhecido: $1"; exit 1;;
  esac
done

TS=$(date +%Y%m%d_%H%M%S)
TARGET="$BACKUP_DIR/gca_backup_$TS"
mkdir -p "$TARGET"

echo "[backup] alvo: $TARGET"

# --- 1. DB gca ---
echo "[backup] dump gca..."
docker exec gca-postgres pg_dump -U gca -d gca --no-owner --no-privileges \
  | gzip -9 > "$TARGET/db_gca.sql.gz"

GCA_SIZE=$(stat -c%s "$TARGET/db_gca.sql.gz" 2>/dev/null || stat -f%z "$TARGET/db_gca.sql.gz")
GCA_HASH=$(sha256sum "$TARGET/db_gca.sql.gz" | awk '{print $1}')

# --- 2. DB gca_test (opcional) ---
GCA_TEST_SIZE=0
GCA_TEST_HASH=""
if [[ $INCLUDE_TEST -eq 1 ]]; then
  echo "[backup] dump gca_test..."
  docker exec gca-postgres pg_dump -U gca -d gca_test --no-owner --no-privileges \
    | gzip -9 > "$TARGET/db_gca_test.sql.gz"
  GCA_TEST_SIZE=$(stat -c%s "$TARGET/db_gca_test.sql.gz" 2>/dev/null || stat -f%z "$TARGET/db_gca_test.sql.gz")
  GCA_TEST_HASH=$(sha256sum "$TARGET/db_gca_test.sql.gz" | awk '{print $1}')
fi

# --- 3. Uploads volume ---
echo "[backup] tar uploads..."
# tar dentro de container alpine montando o volume — evita precisar de
# permissão pra ler /var/lib/docker/volumes/.
docker run --rm \
  -v gca_gca-uploads-storage:/uploads:ro \
  -v "$TARGET":/out \
  alpine:3.20 \
  sh -c "cd /uploads && tar czf /out/uploads.tar.gz . && chmod 644 /out/uploads.tar.gz" \
  > /dev/null 2>&1 || {
    echo "[backup] AVISO: falha ao backupar uploads (volume vazio?)"
    touch "$TARGET/uploads.tar.gz"
}

UPLOAD_SIZE=$(stat -c%s "$TARGET/uploads.tar.gz" 2>/dev/null || stat -f%z "$TARGET/uploads.tar.gz")
UPLOAD_HASH=$(sha256sum "$TARGET/uploads.tar.gz" | awk '{print $1}')

# --- 4. Manifest ---
GCA_VERSION=$(cd "$(dirname "$0")/.." && git rev-parse --short HEAD 2>/dev/null || echo "unknown")

cat > "$TARGET/manifest.json" <<EOF
{
  "backup_id": "gca_backup_$TS",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "gca_git_sha": "$GCA_VERSION",
  "include_test": $INCLUDE_TEST,
  "files": {
    "db_gca.sql.gz": {"size_bytes": $GCA_SIZE, "sha256": "$GCA_HASH"},
    "db_gca_test.sql.gz": {"size_bytes": $GCA_TEST_SIZE, "sha256": "$GCA_TEST_HASH"},
    "uploads.tar.gz": {"size_bytes": $UPLOAD_SIZE, "sha256": "$UPLOAD_HASH"}
  }
}
EOF

# --- 5. Cleanup retenção ---
echo "[backup] limpando backups > $RETENTION_DAYS dias em $BACKUP_DIR..."
find "$BACKUP_DIR" -maxdepth 1 -type d -name "gca_backup_*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

# --- Resumo ---
TOTAL_BYTES=$((GCA_SIZE + GCA_TEST_SIZE + UPLOAD_SIZE))
echo ""
echo "[backup] OK"
echo "  Diretório: $TARGET"
echo "  Total: $(numfmt --to=iec --suffix=B $TOTAL_BYTES 2>/dev/null || echo "$TOTAL_BYTES bytes")"
echo "  Manifest: $TARGET/manifest.json"
