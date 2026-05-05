#!/usr/bin/env bash
# Hook pre-edit do GCA — bloqueia duplicação de símbolos canônicos
#
# Disparado em PreToolUse com matcher "Edit|Write".
# Lê o tool input via stdin (JSON), inspeciona se o conteúdo a ser escrito
# tenta criar um símbolo canônico que já existe no repo. Se sim, sai com
# exit code 2 e mensagem citando onde o original mora.
#
# Exit codes:
#   0  -> ok, prossegue
#   2  -> bloqueia ação, mensagem em stderr vai pro contexto do modelo
#
# Manutenção: a tabela de símbolos canônicos abaixo deve refletir
# CLAUDE.md §1.2. Atualizar quando novo símbolo canônico for declarado.

set -euo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-/home/luiz/GCA}"
INPUT="$(cat)"

# Extrai conteúdo a ser escrito (Edit usa new_string, Write usa content)
CONTENT="$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // ""')"
FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')"

# Se conteúdo vazio (delete-only edit), nada a checar
[[ -z "$CONTENT" ]] && exit 0

# Símbolos canônicos: padrão de criação => mensagem de orientação
declare -A CANONICAL=(
  ["class AIKeyResolver"]="AIKeyResolver já é canônico. Use AIKeyResolver.resolve_project_provider_chain(db, project_id). Ver skill gca-llm-resolver e CLAUDE.md §3.1."
  ["class VaultService"]="VaultService já é canônico para secrets. Use VaultService.store_secret() / VaultService.get_secret(). Ver CLAUDE.md §1.2 e gotcha §6 (commit interno)."
  ["def is_active_integrated_member"]="is_active_integrated_member já existe. Use o helper canônico em vez de filtrar por is_active/joined_at na mão. Ver CLAUDE.md §6 (Membros e RBAC)."
  ["def generate_temporary_password"]="generate_temporary_password já existe em app.core.security. NÃO use secrets.token_urlsafe(12) — não é senha canônica. Ver CLAUDE.md §6 (Vault e secrets)."
)

VIOLATIONS=()
for pattern in "${!CANONICAL[@]}"; do
  if echo "$CONTENT" | grep -qE "^[[:space:]]*${pattern}\b"; then
    # Confirma que o símbolo já existe no repo (evita falso positivo
    # quando o arquivo editado É o canônico original)
    EXISTING="$(grep -rln "${pattern}" "$REPO_ROOT/backend/" 2>/dev/null | grep -v "$FILE_PATH" || true)"
    if [[ -n "$EXISTING" ]]; then
      VIOLATIONS+=("❌ Duplicação de símbolo canônico detectada: '$pattern'
   Já existe em: $EXISTING
   ${CANONICAL[$pattern]}")
    fi
  fi
done

if (( ${#VIOLATIONS[@]} > 0 )); then
  {
    echo "🛑 BLOCK (pre-edit hook): violação de §0 do CLAUDE.md — proibido criar lógica paralela ao que já existe."
    echo ""
    for v in "${VIOLATIONS[@]}"; do echo "$v"; echo ""; done
    echo "Ação: ler o símbolo canônico existente, decidir se reusa ou se há justificativa para divergência. Se reusa, edite o existente. Se diverge, abrir turno explicando antes."
  } >&2
  exit 2
fi

exit 0
