#!/bin/bash
# DT-061 — Restore de backup do GCA.
#
# Restaura:
#   1. Database `gca` a partir de db_gca.sql.gz
#   2. Volume `gca_gca-uploads-storage` a partir de uploads.tar.gz
#   3. Database `gca_test` (opcional, se presente no backup)
#
# OPERAÇÃO DESTRUTIVA — apaga dados atuais e substitui pelos do backup.
# Exige confirmação dupla via prompt + flag --i-know-what-im-doing.
#
# Uso:
#   ./scripts/restore.sh ~/gca-backups/gca_backup_20260418_193000 --i-know-what-im-doing
#
# Pre-checks:
#   - Manifest existe e valida hashes
#   - Containers gca-postgres está rodando
#   - Caller confirma com prompt

set -euo pipefail

BACKUP_PATH="${1:-}"
SHOULD_PROCEED=0

shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --i-know-what-im-doing) SHOULD_PROCEED=1; shift;;
    *) echo "Argumento desconhecido: $1"; exit 1;;
  esac
done

if [[ -z "$BACKUP_PATH" ]]; then
  echo "Uso: $0 <path_do_backup> --i-know-what-im-doing"
  echo "Exemplo: $0 ~/gca-backups/gca_backup_20260418_193000 --i-know-what-im-doing"
  exit 1
fi

if [[ ! -d "$BACKUP_PATH" ]]; then
  echo "[restore] ERRO: $BACKUP_PATH não existe"
  exit 1
fi

if [[ ! -f "$BACKUP_PATH/manifest.json" ]]; then
  echo "[restore] ERRO: manifest.json ausente — backup incompleto/corrompido"
  exit 1
fi

if [[ ! -f "$BACKUP_PATH/db_gca.sql.gz" ]]; then
  echo "[restore] ERRO: db_gca.sql.gz ausente"
  exit 1
fi

# --- Validação de hashes ---
echo "[restore] validando hashes do manifest..."
EXPECTED_GCA_HASH=$(python3 -c "import json; print(json.load(open('$BACKUP_PATH/manifest.json'))['files']['db_gca.sql.gz']['sha256'])")
ACTUAL_GCA_HASH=$(sha256sum "$BACKUP_PATH/db_gca.sql.gz" | awk '{print $1}')
if [[ "$EXPECTED_GCA_HASH" != "$ACTUAL_GCA_HASH" ]]; then
  echo "[restore] ERRO: hash de db_gca.sql.gz não confere — backup corrompido"
  echo "  esperado: $EXPECTED_GCA_HASH"
  echo "  atual:    $ACTUAL_GCA_HASH"
  exit 1
fi

EXPECTED_UP_HASH=$(python3 -c "import json; print(json.load(open('$BACKUP_PATH/manifest.json'))['files']['uploads.tar.gz']['sha256'])")
ACTUAL_UP_HASH=$(sha256sum "$BACKUP_PATH/uploads.tar.gz" | awk '{print $1}')
if [[ "$EXPECTED_UP_HASH" != "$ACTUAL_UP_HASH" ]]; then
  echo "[restore] ERRO: hash de uploads.tar.gz não confere"
  exit 1
fi

echo "[restore] hashes OK"

# --- Confirmação dupla ---
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ATENÇÃO: OPERAÇÃO DESTRUTIVA"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Vou apagar:"
echo "    - Database 'gca' atual (TODOS os dados)"
echo "    - Volume gca_gca-uploads-storage (TODOS os arquivos uploadados)"
echo ""
echo "  E restaurar do backup:"
echo "    $BACKUP_PATH"
echo "    Criado em: $(python3 -c "import json; print(json.load(open('$BACKUP_PATH/manifest.json'))['created_at'])")"
echo ""

if [[ $SHOULD_PROCEED -ne 1 ]]; then
  echo "[restore] Falta flag --i-know-what-im-doing. Abortando."
  exit 1
fi

read -r -p "Digite o path do backup novamente para confirmar: " CONFIRM
if [[ "$CONFIRM" != "$BACKUP_PATH" ]]; then
  echo "[restore] Confirmação não bate. Abortando."
  exit 1
fi

# --- Restauração ---
echo ""
echo "[restore] iniciando restore..."

# 1. Backend down (evita escritas durante restore)
echo "[restore] parando backend..."
docker stop gca-backend > /dev/null 2>&1 || true

# 2. DB gca
echo "[restore] dropping + recriando gca..."
docker exec gca-postgres psql -U gca -d postgres -c "DROP DATABASE IF EXISTS gca;" > /dev/null
docker exec gca-postgres psql -U gca -d postgres -c "CREATE DATABASE gca OWNER gca;" > /dev/null

echo "[restore] restaurando dump gca..."
gunzip -c "$BACKUP_PATH/db_gca.sql.gz" | docker exec -i gca-postgres psql -U gca -d gca > /dev/null

# 3. DB gca_test (se presente)
if [[ -s "$BACKUP_PATH/db_gca_test.sql.gz" ]]; then
  echo "[restore] dropping + recriando gca_test..."
  docker exec gca-postgres psql -U gca -d postgres -c "DROP DATABASE IF EXISTS gca_test;" > /dev/null
  docker exec gca-postgres psql -U gca -d postgres -c "CREATE DATABASE gca_test OWNER gca;" > /dev/null
  gunzip -c "$BACKUP_PATH/db_gca_test.sql.gz" | docker exec -i gca-postgres psql -U gca -d gca_test > /dev/null
  echo "[restore] gca_test restaurado"
fi

# 4. Uploads volume — tem que apagar conteúdo do volume e reextrair
if [[ -s "$BACKUP_PATH/uploads.tar.gz" ]]; then
  echo "[restore] restaurando uploads..."
  docker run --rm \
    -v gca_gca-uploads-storage:/uploads \
    -v "$BACKUP_PATH":/in:ro \
    alpine:3.20 \
    sh -c "rm -rf /uploads/* /uploads/.[!.]* 2>/dev/null; tar xzf /in/uploads.tar.gz -C /uploads"
fi

# 5. Backend up
echo "[restore] subindo backend..."
docker start gca-backend > /dev/null

# 6. Healthcheck
sleep 5
HC=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/metrics/health 2>/dev/null || echo "000")
if [[ "$HC" == "200" ]]; then
  echo ""
  echo "[restore] OK — backend respondeu 200 no health check"
else
  echo ""
  echo "[restore] AVISO — backend não respondeu 200 (status=$HC). Verifique logs:"
  echo "  docker logs gca-backend --tail 50"
fi
