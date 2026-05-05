#!/usr/bin/env bash
# Hook on-stop do GCA — alerta sobre mudanças não commitadas
#
# Disparado em Stop. Lista mudanças não commitadas. Se houver, retorna
# exit 1 (warning) com a lista. Não bloqueia o stop — apenas chama atenção
# para não perder trabalho.
#
# Foco: arquivos canônicos sensíveis (CLAUDE.md, GCA_CANONICAL_CONTRACT.md,
# GCA_MVP_PROGRESS.md, alembic/versions/). Mudanças nesses sem commit
# são bandeira vermelha — política de sessão recomenda commit por unidade
# lógica, não acumular.

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-/home/luiz/GCA}"
cd "$REPO_ROOT" || exit 0

# Não há git? Sai silencioso
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Mudanças unstaged + staged não commitadas
DIRTY="$(git status --porcelain)"
[[ -z "$DIRTY" ]] && exit 0

# Filtrar arquivos críticos
CRITICAL=$(echo "$DIRTY" | grep -E '(CLAUDE\.md|GCA_CANONICAL_CONTRACT\.md|GCA_MVP_PROGRESS\.md|backend/migrations/versions/|backend/app/core/(security|config)\.py)' || true)

if [[ -n "$CRITICAL" ]]; then
  {
    echo "⚠ on-stop: mudanças NÃO commitadas em arquivos críticos:"
    echo ""
    echo "$CRITICAL"
    echo ""
    echo "Recomendação: commit antes de encerrar sessão. Política de sessão (CLAUDE.md §0): commit por unidade lógica, não acumular."
  } >&2
  exit 1
fi

# Mudanças menores — só lista, exit 0
TOTAL=$(echo "$DIRTY" | wc -l)
echo "ℹ on-stop: $TOTAL arquivo(s) modificado(s) não commitado(s) (não-críticos). Considere commit." >&2
exit 0
