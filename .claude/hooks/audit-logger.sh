#!/usr/bin/env bash
# Hook audit-logger do GCA — registra todas as tool calls em .claude/audit.log
#
# Disparado em PostToolUse com matcher "Read|Edit|Write|Bash".
# Append-only, exit sempre 0 (nao bloqueia, so observa).
# Usa flock para serializar escritas concorrentes.
# Rotaciona quando audit.log passa de 10MB.
#
# Implementa Componente A da Rota E (auditor-analista, sessao 2026-05-02):
# trilha forense para reconstituir padroes de tentativa-e-erro sem analise previa.
#
# Formato:
#   [2026-05-02T12:34:56-03:00] tool=Read file=backend/app/services/personas/auditor.py
#   [2026-05-02T12:35:01-03:00] tool=Bash cmd="docker compose restart backend"
#
# Pre-requisitos: jq, flock (util-linux)

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-/home/luiz/GCA}"
AUDIT_LOG="$REPO_ROOT/.claude/audit.log"
MAX_BYTES=$((10 * 1024 * 1024))  # 10 MB

INPUT="$(cat)"

TOOL_NAME="$(echo "$INPUT" | jq -r '.tool_name // ""')"
[[ -z "$TOOL_NAME" ]] && exit 0

TS="$(date --iso-8601=seconds)"

case "$TOOL_NAME" in
  Read|Edit|Write)
    FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')"
    [[ -z "$FILE_PATH" ]] && exit 0
    REL="${FILE_PATH#$REPO_ROOT/}"
    LINE="[$TS] tool=$TOOL_NAME file=$REL"
    ;;
  Bash)
    CMD="$(echo "$INPUT" | jq -r '.tool_input.command // ""')"
    [[ -z "$CMD" ]] && exit 0
    # Truncar em 200 chars para nao poluir; remover quebras de linha
    CMD_TRIM="$(echo "$CMD" | tr '\n' ' ' | cut -c1-200)"
    LINE="[$TS] tool=Bash cmd=\"$CMD_TRIM\""
    ;;
  *)
    exit 0
    ;;
esac

# Rotacionar se passou do limite, antes de escrever
if [[ -f "$AUDIT_LOG" ]]; then
  SIZE="$(stat -c%s "$AUDIT_LOG" 2>/dev/null || echo 0)"
  if (( SIZE > MAX_BYTES )); then
    mv "$AUDIT_LOG" "$AUDIT_LOG.1" 2>/dev/null || true
  fi
fi

# Escrita serializada com flock
(
  flock -x 9
  echo "$LINE" >> "$AUDIT_LOG"
) 9>>"$AUDIT_LOG.lock"

exit 0
