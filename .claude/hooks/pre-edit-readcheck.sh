#!/usr/bin/env bash
# Hook pre-edit-readcheck do GCA — exige Read previo nos hot-paths
#
# Disparado em PreToolUse com matcher "Edit|Write".
# Bloqueia (exit 2) se o file_path estiver em hot-path do GCA e nao houver
# entrada "tool=Read file=<path>" em .claude/audit.log nos ultimos 3600s.
#
# Implementa Componente B parcial da Rota E (auditor-analista, sessao 2026-05-02):
# forca o ciclo "ler antes de editar" nos diretorios mais quentes do projeto.
#
# Hot-paths cobertos:
#   - backend/app/services/personas/
#   - backend/app/routers/
#   - n8n/
#
# Bypass: definir env var GCA_SKIP_READCHECK=1 libera com warning loggado.
# Use para casos legitimos (correcao trivial obvia, tipo cosmetico).
#
# Janela de 3600s (1h) cobre fluxo normal: Read -> analise -> Edit dentro do mesmo
# topico de trabalho. Sessao nova = audit.log sem Reads recentes = bloqueia ate
# voce fazer Read explicito. Comportamento desejado.
#
# Pre-requisitos: jq, audit-logger.sh ja registrado em PostToolUse para Read.

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-/home/luiz/GCA}"
AUDIT_LOG="$REPO_ROOT/.claude/audit.log"
WINDOW_SECONDS=3600

INPUT="$(cat)"
FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')"
[[ -z "$FILE_PATH" ]] && exit 0

# Normalizar para path relativo ao REPO_ROOT (mesmo formato do audit.log)
REL="${FILE_PATH#$REPO_ROOT/}"

# Hot-paths (prefixo relativo ao REPO_ROOT)
HOT_PATHS=(
  "backend/app/services/personas/"
  "backend/app/routers/"
  "n8n/"
)

IS_HOT=0
for prefix in "${HOT_PATHS[@]}"; do
  if [[ "$REL" == "$prefix"* ]]; then
    IS_HOT=1
    break
  fi
done

# Fora de hot-path: passa direto
[[ "$IS_HOT" -eq 0 ]] && exit 0

# Bypass explicito
if [[ "${GCA_SKIP_READCHECK:-0}" == "1" ]]; then
  TS="$(date --iso-8601=seconds)"
  echo "[$TS] BYPASS GCA_SKIP_READCHECK=1 file=$REL" >> "$AUDIT_LOG" 2>/dev/null || true
  echo "WARN (pre-edit-readcheck): bypass via GCA_SKIP_READCHECK=1 em hot-path $REL" >&2
  exit 0
fi

# Buscar Read recente no audit.log
NOW="$(date +%s)"
THRESHOLD=$((NOW - WINDOW_SECONDS))

FOUND=0
if [[ -f "$AUDIT_LOG" ]]; then
  # Iterar do fim pro inicio (Reads recentes provavelmente sao recentes no log)
  while IFS= read -r line; do
    PARSED_FILE="$(echo "$line" | sed -nE 's/.*tool=Read file=(.*)$/\1/p')"
    [[ "$PARSED_FILE" != "$REL" ]] && continue
    TS_RAW="$(echo "$line" | sed -E 's/^\[([^]]+)\].*/\1/')"
    TS_EPOCH="$(date -d "$TS_RAW" +%s 2>/dev/null || echo 0)"
    if (( TS_EPOCH >= THRESHOLD )); then
      FOUND=1
      break
    fi
  done < <(tac "$AUDIT_LOG" 2>/dev/null || cat "$AUDIT_LOG")
fi

if [[ "$FOUND" -eq 1 ]]; then
  exit 0
fi

# Bloqueio
{
  echo "BLOCK (pre-edit-readcheck): tentativa de editar arquivo em hot-path do GCA sem Read previo na janela de ${WINDOW_SECONDS}s."
  echo ""
  echo "  Arquivo: $REL"
  echo "  Hot-path: ${HOT_PATHS[*]}"
  echo ""
  echo "Acao: rodar Read no arquivo antes de Edit/Write. Auditor-analista (CLAUDE.md global): leia antes de escrever."
  echo "Bypass legitimo (correcao trivial obvia): GCA_SKIP_READCHECK=1 antes do Edit. Sera registrado no audit.log."
} >&2

exit 2
