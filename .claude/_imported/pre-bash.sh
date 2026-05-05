#!/usr/bin/env bash
# Hook pre-bash do GCA — bloqueia pytest contra DB de produção
#
# Disparado em PreToolUse com matcher "Bash".
# Inspeciona o comando shell que o modelo quer rodar. Se for pytest e o
# DATABASE_URL efetivo apontar para o DB 'gca' (produção/dogfood) em vez
# de 'gca_test', bloqueia com exit 2.
#
# Implementa CLAUDE.md §3.6 e §6 (Banco e migrations):
#   - Pytest do GCA roda contra gca_test, nunca contra gca.
#   - Não criar dados no DB de produção (gca) sem autorização explícita.
#
# Estratégia: extrair o DATABASE_URL efetivo de:
#   1. variável de ambiente do shell (export ou comando inline)
#   2. arquivo .env ou .env.test do backend, se existir
#   3. default do config.py (postgresql+asyncpg://gca:...@.../gca)
# E checar se aponta para /gca em vez de /gca_test no path.

set -euo pipefail

INPUT="$(cat)"
COMMAND="$(echo "$INPUT" | jq -r '.tool_input.command // ""')"

# Só interessa pytest
if ! echo "$COMMAND" | grep -qE '\bpytest\b'; then
  exit 0
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-/home/luiz/GCA}"

# 1) DATABASE_URL inline no comando? (ex: DATABASE_URL=postgresql://... pytest)
INLINE_URL="$(echo "$COMMAND" | grep -oE 'DATABASE_URL=[^ ]+' | head -1 | cut -d= -f2- || true)"

# 2) DATABASE_URL no shell?
SHELL_URL="${DATABASE_URL:-}"

# 3) Procurar em .env do backend
ENV_URL=""
for env_file in "$REPO_ROOT/backend/.env" "$REPO_ROOT/.env"; do
  if [[ -f "$env_file" ]]; then
    ENV_URL="$(grep -E '^DATABASE_URL=' "$env_file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
    [[ -n "$ENV_URL" ]] && break
  fi
done

# 4) Default do config.py (CLAUDE.md fact-check: postgresql+asyncpg://gca:gca_secret@localhost:5432/gca)
DEFAULT_URL="postgresql+asyncpg://gca:gca_secret@localhost:5432/gca"

# Precedência: inline > shell > .env > default
EFFECTIVE_URL="${INLINE_URL:-${SHELL_URL:-${ENV_URL:-$DEFAULT_URL}}}"

# Extrair nome do DB (último segmento após /, antes de ? ou fim)
DB_NAME="$(echo "$EFFECTIVE_URL" | sed -E 's|.*/([^/?]+)([?].*)?$|\1|')"

# Se conftest.py do projeto força gca_test independentemente, isso é um
# segundo nível de defesa — mas o hook ainda verifica para o caso de
# alguém invocar pytest com flag/env que sobrescreva.
if [[ "$DB_NAME" != "gca_test" ]]; then
  {
    echo "🛑 BLOCK (pre-bash hook): tentativa de rodar pytest contra DB '$DB_NAME' — proibido por CLAUDE.md §3.6 e §6."
    echo ""
    echo "DATABASE_URL efetivo: $EFFECTIVE_URL"
    echo "DB extraído: $DB_NAME"
    echo "Esperado: gca_test"
    echo ""
    echo "Origens consultadas:"
    [[ -n "$INLINE_URL" ]] && echo "  - inline no comando: $INLINE_URL"
    [[ -n "$SHELL_URL"  ]] && echo "  - variável de shell: $SHELL_URL"
    [[ -n "$ENV_URL"    ]] && echo "  - .env do backend: $ENV_URL"
    [[ -z "$INLINE_URL$SHELL_URL$ENV_URL" ]] && echo "  - nenhuma origem explícita; default do config.py aponta para 'gca' (produção)"
    echo ""
    echo "Ação: definir DATABASE_URL=postgresql+asyncpg://gca:gca_secret@localhost:5432/gca_test antes de rodar pytest, ou usar conftest.py que já força isso."
  } >&2
  exit 2
fi

exit 0
