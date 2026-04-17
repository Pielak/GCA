#!/usr/bin/env bash
# Bootstrap + execução do capturador de telas do GCA.
#
# 1. Cria venv local (se não existir) em .venv-screenshots/
# 2. Instala playwright + chromium (~170MB)
# 3. Roda o capturador
#
# Uso:
#   bash scripts/capturar_telas_gca.sh
#   bash scripts/capturar_telas_gca.sh --headed              # ver o browser
#   bash scripts/capturar_telas_gca.sh --base-url https://gca.code-auditor.com.br
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv-screenshots"

cd "$ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "→ Criando venv em $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "→ Atualizando pip"
pip install --upgrade pip --quiet

if ! python -c "import playwright" 2>/dev/null; then
    echo "→ Instalando playwright (~30s)"
    pip install playwright --quiet
fi

# Instala o browser Chromium se ainda não estiver no cache
if [[ ! -d "$HOME/.cache/ms-playwright" ]] || [[ -z "$(find "$HOME/.cache/ms-playwright" -maxdepth 1 -name 'chromium*' 2>/dev/null)" ]]; then
    echo "→ Baixando Chromium (~170MB, primeira vez apenas)"
    python -m playwright install chromium
    echo "→ Instalando dependências do sistema (pode pedir senha)"
    python -m playwright install-deps chromium 2>&1 | tail -5 || \
        echo "  (se faltarem libs, rode: sudo $VENV_DIR/bin/python -m playwright install-deps chromium)"
fi

echo
echo "→ Capturando telas do GCA"
python scripts/capturar_telas_gca.py "$@"
