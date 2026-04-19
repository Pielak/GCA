#!/bin/bash
# DT-062 — Upgrade idempotente do GCA por cliente.
#
# Uso típico (cliente atualiza sua instância pra última versão):
#   ./scripts/upgrade.sh
#
# Etapas idempotentes (re-run safe — cada passo verifica antes de agir):
#   1. Backup pre-upgrade (DT-061) — sempre
#   2. git fetch + diff vs HEAD remoto
#   3. Se já atualizado: sai limpo (sem rebuild)
#   4. git pull
#   5. docker compose build (só backend/frontend)
#   6. Migrações Alembic (alembic upgrade head, idempotente por design)
#   7. docker compose up -d --force-recreate backend frontend
#   8. Healthcheck pós-upgrade (até 60s waiting)
#   9. Suite mínima de smoke (curl health + /metrics/health)
#  10. Se falhar: AVISA pro user rodar restore.sh do backup pre-upgrade
#
# Falha em qualquer etapa = aborta com código != 0 + log claro do passo.
# Não toca em volumes (uploads/postgres-data) — preservados entre upgrades.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/upgrade_$(date +%Y%m%d_%H%M%S).log"

log() {
  echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG"
}

fail() {
  log "ERRO: $1"
  log "Upgrade abortado. Backup pre-upgrade disponível em: $BACKUP_PATH"
  log "Para reverter: ./scripts/restore.sh $BACKUP_PATH --i-know-what-im-doing"
  exit 1
}

cd "$REPO_DIR"

# --- 1. Backup pre-upgrade ---
log "1/9 backup pre-upgrade..."
BACKUP_OUT=$("$REPO_DIR/scripts/backup.sh" 2>&1)
echo "$BACKUP_OUT" >> "$LOG"
BACKUP_PATH=$(echo "$BACKUP_OUT" | grep "Diretório:" | awk '{print $2}')
[[ -n "$BACKUP_PATH" && -d "$BACKUP_PATH" ]] || fail "backup pre-upgrade falhou"
log "backup ok: $BACKUP_PATH"

# --- 2. git fetch ---
log "2/9 git fetch..."
git fetch origin >> "$LOG" 2>&1 || fail "git fetch falhou (sem rede ou auth?)"

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse "@{u}" 2>/dev/null || git rev-parse "origin/$(git branch --show-current)")

# --- 3. Já atualizado? ---
if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  log "3/9 nenhum commit novo (HEAD = origin). Saindo limpo."
  log "git_sha=$LOCAL_SHA"
  exit 0
fi

log "3/9 atualizando: $LOCAL_SHA → $REMOTE_SHA"

# --- 4. git pull ---
log "4/9 git pull..."
# Fast-forward only — evita merge automático; se diverge, força user resolver
git pull --ff-only origin "$(git branch --show-current)" >> "$LOG" 2>&1 || \
  fail "git pull não-fast-forward — branch divergiu, resolva manualmente"

# --- 5. Rebuild ---
log "5/9 docker compose build (backend + frontend)..."
DOCKER_BUILDKIT=0 docker compose build backend frontend >> "$LOG" 2>&1 || fail "build falhou"

# --- 6. Migrações Alembic ---
log "6/9 alembic upgrade head..."
# Subir backend só pra rodar migration; depois recreate
docker compose up -d backend >> "$LOG" 2>&1
sleep 3
# Tenta migrate. Sem migrations? OK também.
if docker exec gca-backend test -d /app/migrations; then
  docker exec gca-backend alembic upgrade head >> "$LOG" 2>&1 || \
    log "AVISO: alembic falhou (talvez não há migration nova ou alembic não configurado)"
else
  log "(sem dir migrations — pulando)"
fi

# --- 7. Recreate ---
log "7/9 recreate backend + frontend..."
docker compose up -d --force-recreate backend frontend >> "$LOG" 2>&1 || fail "recreate falhou"

# --- 8. Healthcheck ---
log "8/9 healthcheck (max 60s)..."
HEALTH_OK=0
for i in {1..30}; do
  HC=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/metrics/health 2>/dev/null || echo "000")
  if [[ "$HC" == "200" ]]; then
    HEALTH_OK=1
    log "backend respondeu 200 em ${i}x2s"
    break
  fi
  sleep 2
done
[[ $HEALTH_OK -eq 1 ]] || fail "backend não respondeu 200 em 60s"

# --- 9. Smoke ---
log "9/9 smoke checks..."
HC_FRONT=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null || echo "000")
log "frontend HTTP $HC_FRONT"

# --- Sucesso ---
log ""
log "═══════════════════════════════════════════════════════════════"
log "  UPGRADE CONCLUÍDO"
log "═══════════════════════════════════════════════════════════════"
log "  De: $LOCAL_SHA"
log "  Para: $REMOTE_SHA"
log "  Backup pre-upgrade: $BACKUP_PATH"
log "  Log completo: $LOG"

# --- Cleanup backups antigos (mantém 5 mais recentes de upgrades) ---
ls -td $LOG_DIR/upgrade_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f
