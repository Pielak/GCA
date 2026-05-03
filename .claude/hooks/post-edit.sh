#!/usr/bin/env bash
# Hook post-edit do GCA — roda pytest do arquivo correspondente, warning se vermelho
#
# Disparado em PostToolUse com matcher "Edit|Write".
# Identifica o arquivo tocado, mapeia para o test_<nome>.py correspondente,
# roda pytest. Se vermelho, retorna exit 1 (warning não-bloqueante) e a saída
# vai para o contexto do modelo no próximo turno.
#
# Decisão (Pielak 2026-05-01): granularidade (a) — só do arquivo tocado,
# warning não-bloqueante.
#
# Pré-requisitos:
#   - venv ativo OU backend/.venv com dependências
#   - DATABASE_URL apontando para gca_test (hook db-protect já garante)
#   - schema de gca_test sincronizado com gca

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-/home/luiz/GCA}"
INPUT="$(cat)"
FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')"

# Só interessa arquivo Python no backend
[[ "$FILE_PATH" != *"/backend/"*.py ]] && exit 0
[[ "$FILE_PATH" == *"/tests/"* ]] && exit 0  # editou teste — não é o foco
[[ "$FILE_PATH" == *"/__pycache__/"* ]] && exit 0
[[ "$FILE_PATH" == *"/migrations/"* ]] && exit 0

# Mapear arquivo -> teste correspondente
# Ex: backend/app/services/personas/auditor.py -> backend/app/tests/services/personas/test_auditor.py
REL_PATH="${FILE_PATH#$REPO_ROOT/backend/app/}"
BASE_NAME="$(basename "$REL_PATH" .py)"
DIR_PATH="$(dirname "$REL_PATH")"
TEST_FILE="$REPO_ROOT/backend/app/tests/$DIR_PATH/test_${BASE_NAME}.py"

# Fallbacks: tests/ na raiz do módulo, ou test_<nome>.py em qualquer profundidade
if [[ ! -f "$TEST_FILE" ]]; then
  TEST_FILE="$(find "$REPO_ROOT/backend/app/tests" -name "test_${BASE_NAME}.py" -type f 2>/dev/null | head -1)"
fi

if [[ -z "$TEST_FILE" ]] || [[ ! -f "$TEST_FILE" ]]; then
  # Sem teste correspondente — apenas avisa, não bloqueia
  echo "⚠ post-edit: nenhum test_${BASE_NAME}.py encontrado para $FILE_PATH. Considerar criar teste." >&2
  exit 0
fi

# Resolver pytest: prefere venv do backend, depois venv da raiz, depois sistema
PYTEST=""
for candidate in \
  "$REPO_ROOT/backend/.venv/bin/pytest" \
  "$REPO_ROOT/.venv/bin/pytest" \
  "$REPO_ROOT/venv/bin/pytest" \
  "$(command -v pytest)"; do
  if [[ -x "$candidate" ]]; then PYTEST="$candidate"; break; fi
done

if [[ -z "$PYTEST" ]]; then
  echo "⚠ post-edit: pytest não encontrado em venv nem no PATH. Pulando." >&2
  exit 0
fi

# Rodar com timeout de 60s para evitar trava em hook
cd "$REPO_ROOT/backend"
PYTEST_OUTPUT="$(timeout 60 "$PYTEST" "$TEST_FILE" -x --tb=short -q 2>&1)" || PYTEST_EXIT=$?
PYTEST_EXIT="${PYTEST_EXIT:-0}"

if (( PYTEST_EXIT != 0 )); then
  {
    echo "⚠ WARN (post-edit hook): pytest vermelho em $TEST_FILE após edição de $FILE_PATH"
    echo "Exit code: $PYTEST_EXIT"
    echo ""
    echo "--- saída do pytest ---"
    echo "$PYTEST_OUTPUT" | tail -50
    echo "--- fim ---"
    echo ""
    echo "§0 do CLAUDE.md: proibido afirmar 'funciona' sem ter passado nos testes. Investigar antes de prosseguir."
  } >&2
  exit 1  # warning, não bloqueia
fi

exit 0
