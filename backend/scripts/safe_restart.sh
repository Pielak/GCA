#!/bin/bash
# safe_restart.sh — reinicia backend/db com pré-check obrigatório
#
# Uso:
#   ./safe_restart.sh [backend|db|all] [--wait SECONDS] [--force]
#
# Exemplos:
#   ./safe_restart.sh backend --wait 120     # aguarda 120s, depois reinicia backend
#   ./safe_restart.sh all --force             # força restart sem aguardar
#   ./safe_restart.sh db                      # reinicia apenas DB (sem check, é sempre seguro)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.."

SERVICE="${1:-backend}"
WAIT_SECS=0
FORCE=0

# Parse args
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --wait)
            WAIT_SECS="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        *)
            echo "Argumento desconhecido: $1"
            exit 1
            ;;
    esac
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 Safe Restart Script — $SERVICE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check pré-restart (apenas se backend ou all)
if [[ "$SERVICE" == "backend" ]] || [[ "$SERVICE" == "all" ]]; then
    echo ""
    echo "📋 Pré-restart check: documentos em processamento?"
    echo ""

    # Rodar check
    CHECK_CMD="python3 backend/scripts/check_before_restart.py --wait $WAIT_SECS"
    if [[ $FORCE -eq 1 ]]; then
        CHECK_CMD="$CHECK_CMD --force"
    fi

    if ! $CHECK_CMD; then
        echo ""
        echo "❌ Pré-check falhou. Abortando restart."
        exit 1
    fi

    echo ""
    echo "✓ Pré-check OK. Prosseguindo com restart..."
fi

# Reiniciar
echo ""
case "$SERVICE" in
    backend)
        echo "🐋 Reiniciando container backend..."
        docker compose restart backend
        ;;
    db)
        echo "🐘 Reiniciando container postgres..."
        docker compose restart postgres
        ;;
    all)
        echo "🐋 Reiniciando backend + postgres..."
        docker compose restart backend postgres
        ;;
    *)
        echo "❌ Serviço desconhecido: $SERVICE"
        exit 1
        ;;
esac

echo ""
echo "⏳ Aguardando containers ficarem prontos..."
sleep 3
docker compose logs --tail 5 $SERVICE | grep -iE "ready|started|listening|error" || true

echo ""
echo "✅ Restart concluído!"
echo ""
