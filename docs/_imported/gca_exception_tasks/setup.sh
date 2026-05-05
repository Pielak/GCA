#!/usr/bin/env bash
# setup.sh — Instala o pacote de tasks de tratamento de exceções no GCA
#
# Pré-condições:
#   - Arquivos TASK_EH_*.md baixados em /home/luiz/Downloads/gca_exception_tasks/
#   - Repo GCA em /home/luiz/GCA com working tree limpa
#   - git, claude code instalados
#
# Uso:
#   bash /home/luiz/Downloads/gca_exception_tasks/setup.sh

set -euo pipefail

# ─── Configuração ────────────────────────────────────────────────────────────
DOWNLOADS_DIR="/home/luiz/Downloads/gca_exception_tasks"
GCA_DIR="/home/luiz/GCA"
TASKS_DIR_REL="docs/tasks/exception-handling"
TASKS_DIR_ABS="${GCA_DIR}/${TASKS_DIR_REL}"
BRANCH="feat/exception-handling-canonical"

# ─── Cores para legibilidade ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[setup]${NC} $1"; }
ok()    { echo -e "${GREEN}[ ok ]${NC} $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $1"; }
err()   { echo -e "${RED}[err ]${NC} $1" >&2; }

# ─── Validação 1 — diretórios existem ───────────────────────────────────────
log "Validando ambiente..."

if [[ ! -d "$DOWNLOADS_DIR" ]]; then
    err "Diretório de tasks não encontrado: $DOWNLOADS_DIR"
    err "Confirme que os arquivos TASK_EH_*.md estão em $DOWNLOADS_DIR"
    exit 1
fi

if [[ ! -d "$GCA_DIR" ]]; then
    err "Repositório GCA não encontrado em: $GCA_DIR"
    exit 1
fi

if [[ ! -d "$GCA_DIR/.git" ]]; then
    err "$GCA_DIR não parece ser um repositório git"
    exit 1
fi

ok "Diretórios validados"

# ─── Validação 2 — todos os arquivos de task presentes ─────────────────────
log "Verificando arquivos de task..."

EXPECTED_FILES=(
    "README.md"
    "TASK_EH_00_SETUP.md"
    "TASK_EH_01_SERVICES.md"
    "TASK_EH_02_API.md"
    "TASK_EH_03_MODELS.md"
    "TASK_EH_04_INTEGRATIONS.md"
    "TASK_EH_05_CODEGEN.md"
)

MISSING=0
for f in "${EXPECTED_FILES[@]}"; do
    if [[ ! -f "$DOWNLOADS_DIR/$f" ]]; then
        err "Arquivo ausente: $DOWNLOADS_DIR/$f"
        MISSING=1
    fi
done

if [[ $MISSING -eq 1 ]]; then
    err "Baixe novamente os arquivos antes de executar."
    exit 1
fi

ok "Todos os 7 arquivos presentes"

# ─── Validação 3 — working tree limpa ──────────────────────────────────────
log "Verificando estado do git..."

cd "$GCA_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
    warn "Working tree NÃO está limpa em $GCA_DIR:"
    git status --short
    echo ""
    read -rp "Continuar mesmo assim? [s/N] " resp
    if [[ ! "$resp" =~ ^[sSyY]$ ]]; then
        err "Abortado pelo usuário."
        exit 1
    fi
else
    ok "Working tree limpa"
fi

# ─── Validação 4 — branch ──────────────────────────────────────────────────
log "Verificando branch..."

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [[ "$CURRENT_BRANCH" == "$BRANCH" ]]; then
    ok "Já está em $BRANCH"
elif git rev-parse --verify "$BRANCH" &>/dev/null; then
    log "Branch $BRANCH existe — fazendo checkout"
    git checkout "$BRANCH"
    ok "Em $BRANCH"
else
    log "Criando branch $BRANCH a partir de $CURRENT_BRANCH"

    # Confirmar se a base é apropriada
    if [[ "$CURRENT_BRANCH" != "master" && "$CURRENT_BRANCH" != "main" ]]; then
        warn "Você não está em master/main (está em: $CURRENT_BRANCH)"
        read -rp "Criar $BRANCH a partir de $CURRENT_BRANCH? [s/N] " resp
        if [[ ! "$resp" =~ ^[sSyY]$ ]]; then
            err "Abortado. Faça checkout em master e rode novamente."
            exit 1
        fi
    fi

    git checkout -b "$BRANCH"
    ok "Branch $BRANCH criada"
fi

# ─── Validação 5 — diretório alvo ──────────────────────────────────────────
log "Preparando diretório de tasks..."

if [[ -d "$TASKS_DIR_ABS" ]] && [[ -n "$(ls -A "$TASKS_DIR_ABS" 2>/dev/null)" ]]; then
    warn "$TASKS_DIR_ABS já existe e contém arquivos:"
    ls -1 "$TASKS_DIR_ABS"
    echo ""
    read -rp "Sobrescrever? [s/N] " resp
    if [[ ! "$resp" =~ ^[sSyY]$ ]]; then
        err "Abortado pelo usuário."
        exit 1
    fi
fi

mkdir -p "$TASKS_DIR_ABS"
ok "Diretório $TASKS_DIR_REL pronto"

# ─── Cópia dos arquivos ─────────────────────────────────────────────────────
log "Copiando arquivos de task..."

for f in "${EXPECTED_FILES[@]}"; do
    cp "$DOWNLOADS_DIR/$f" "$TASKS_DIR_ABS/$f"
    ok "  $f"
done

# ─── Commit inicial das tasks ───────────────────────────────────────────────
log "Criando commit inicial das tasks..."

cd "$GCA_DIR"
git add "$TASKS_DIR_REL/"

if git diff --cached --quiet; then
    warn "Nenhuma mudança para commit (arquivos já estavam idênticos?)"
else
    git commit -m "docs(tasks): adicionar pacote de tasks de tratamento de exceções

Pacote de 6 tasks para refatoração canônica de tratamento de exceções
em todo o backend, mais propagação para o CodeGen.

Ordem de execução:
- TASK_EH_00 — setup da infraestrutura (exceptions, handlers, ruff, check AST)
- TASK_EH_01 — refatoração de services
- TASK_EH_02 — refatoração de api
- TASK_EH_03 — refatoração de models e repositories
- TASK_EH_04 — refatoração de integrations (LLMs, HTTP, crypto)
- TASK_EH_05 — refatoração de codegen + propagação para código gerado

Ver docs/tasks/exception-handling/README.md para uso."
    ok "Commit criado"
fi

# ─── Resumo final ───────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
ok "Setup concluído com sucesso"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "Branch ativa:   $BRANCH"
echo "Tasks em:       $TASKS_DIR_ABS"
echo ""
echo "Próximo passo — abra o Claude Code e execute a primeira task:"
echo ""
echo "    cd $GCA_DIR"
echo "    claude"
echo ""
echo "Dentro da sessão:"
echo ""
echo "    Leia docs/tasks/exception-handling/TASK_EH_00_SETUP.md e execute"
echo "    exatamente como descrito. Pare ao final, antes do commit, e me"
echo "    apresente o relatório."
echo ""
echo "Após cada task: revise, teste manualmente e faça commit. Só então passe"
echo "para a próxima."
echo ""
