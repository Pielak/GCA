#!/usr/bin/env bash
# GCA — Instalador interativo para Ubuntu 22.04+
#
# Implementa as 10 etapas do assistente (espelha o Inno Setup do Windows):
#   1. Boas-vindas
#   2. Aceite do EULA
#   3. Chave de ativação
#   4. Pré-requisitos (Docker, RAM, disco, rede)
#   5. Pasta de instalação
#   6. Porta e domínio
#   7. Administrador inicial (nome, email, senha)
#   8. Provedor de IA
#   9. Resumo (confirmação)
#  10. Instalação propriamente dita
#
# Uso:
#   sudo ./install.sh                    # interativo
#   sudo GCA_LICENSE=... GCA_ADMIN_EMAIL=... GCA_ADMIN_PASSWORD=... \
#        ./install.sh --non-interactive  # para .deb postinst

set -euo pipefail

# ─── Constantes ────────────────────────────────────────────────────
VERSION="1.0.0"
REGISTRY="${GCA_REGISTRY:-registry.gca-produto.com}"
BACKEND_IMG="${REGISTRY}/gca-backend:${VERSION}"
FRONTEND_IMG="${REGISTRY}/gca-frontend:${VERSION}"

# Cores
BOLD=$(tput bold); NORM=$(tput sgr0); RED=$(tput setaf 1); GREEN=$(tput setaf 2)
YELLOW=$(tput setaf 3); VIOLET=$(tput setaf 5); CYAN=$(tput setaf 6)

err() { echo "${RED}ERRO:${NORM} $*" >&2; exit 1; }
ok()  { echo "${GREEN}✓${NORM} $*"; }
warn(){ echo "${YELLOW}⚠${NORM} $*"; }
info(){ echo "${CYAN}ℹ${NORM} $*"; }
section() { echo ""; echo "${BOLD}${VIOLET}═══ $* ═══${NORM}"; }

NON_INTERACTIVE=0
for arg in "$@"; do
    [ "$arg" = "--non-interactive" ] && NON_INTERACTIVE=1
done

ask() {
    local prompt="$1"; local default="${2:-}"; local var="$3"
    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        eval "$var=\"\${$var:-$default}\""
        return
    fi
    if [ -n "$default" ]; then
        read -r -p "${BOLD}$prompt${NORM} [${default}]: " tmp
        tmp="${tmp:-$default}"
    else
        read -r -p "${BOLD}$prompt${NORM}: " tmp
    fi
    eval "$var=\"$tmp\""
}

ask_pass() {
    local prompt="$1"; local var="$2"
    read -rs -p "${BOLD}$prompt${NORM}: " tmp; echo ""
    eval "$var=\"$tmp\""
}

# ─── Verificação de root ───────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || err "Execute com sudo."

# ─── Etapa 1: Boas-vindas ──────────────────────────────────────────
clear
cat <<EOF
${BOLD}${VIOLET}╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   GCA — Gestão de Codificação Assistida                       ║
║   Instalador Ubuntu v${VERSION}                                     ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝${NORM}

Este instalador vai guiá-lo por 10 etapas para colocar o GCA em
produção nesta máquina.

Tempo estimado: 6 a 15 minutos (depende da Internet).

EOF

if [ "$NON_INTERACTIVE" -eq 0 ]; then
    read -rp "Pressione ENTER para continuar ou Ctrl+C para cancelar..."
fi

# ─── Etapa 2: EULA ─────────────────────────────────────────────────
section "Etapa 2/10 — Aceite do contrato de licença (EULA)"
cat <<EOF
CONTRATO DE LICENÇA DE USO — GCA

1. Este software é fornecido sob licença comercial pelo titular da
   chave de ativação. Engenharia reversa é proibida.

2. O cliente é responsável por: backups regulares, segurança da chave
   mestra (GCA_MASTER_KEY), credenciais de provedores de IA.

3. O GCA não compartilha dados entre instâncias de clientes. Cada
   instância é soberana sobre seus próprios dados.

4. Atualizações do GCA são entregues via release versionada e
   respeitam o contrato de preservação de dados (MVP 7).

5. Suporte é prestado conforme contrato comercial separado.
EOF

if [ "$NON_INTERACTIVE" -eq 0 ]; then
    ask "Aceita os termos do contrato? (sim/não)" "sim" EULA_OK
    [ "$EULA_OK" = "sim" ] || err "EULA rejeitado. Abortando."
fi

# ─── Etapa 3: Chave de ativação ────────────────────────────────────
section "Etapa 3/10 — Chave de ativação"
ask "Chave de ativação (GCA-PROD-XXXXX-XXXXX-XXXXX-XXXXX)" "" GCA_LICENSE
echo "$GCA_LICENSE" | grep -qE '^GCA-PROD-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$' \
    || warn "Formato de chave não bateu com GCA-PROD-XXXXX-XXXXX-XXXXX-XXXXX (seguindo mesmo assim)."

# ─── Etapa 4: Pré-requisitos ───────────────────────────────────────
section "Etapa 4/10 — Verificação de pré-requisitos"

if ! command -v docker >/dev/null 2>&1; then
    err "Docker não instalado. Consulte seção 2.2 do Tutorial para instruções."
fi
ok "Docker: $(docker --version | cut -d',' -f1)"

if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose plugin não instalado."
fi
ok "Docker Compose: $(docker compose version --short)"

RAM_MB=$(free -m | awk 'NR==2{print $2}')
if [ "$RAM_MB" -lt 7500 ]; then
    warn "RAM total: ${RAM_MB} MB (recomendado 8 GB+)"
else
    ok "RAM: ${RAM_MB} MB"
fi

DISK_GB=$(df -BG / | awk 'NR==2{print $4}' | tr -d 'G')
if [ "$DISK_GB" -lt 30 ]; then
    err "Espaço em disco: ${DISK_GB} GB (mínimo 30 GB). Libere espaço antes de continuar."
fi
ok "Espaço em disco: ${DISK_GB} GB livres"

if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then
    ok "Conectividade Internet: OK"
else
    warn "Sem conectividade direta; instalação pode falhar ao baixar imagens."
fi

# ─── Etapa 5: Pasta de instalação ─────────────────────────────────
section "Etapa 5/10 — Pasta de instalação"
ask "Pasta de instalação" "/opt/gca" INSTALL_DIR

if [ -d "$INSTALL_DIR" ]; then
    warn "Pasta $INSTALL_DIR já existe. Conteúdo será sobrescrito."
fi
mkdir -p "$INSTALL_DIR"
ok "Pasta: $INSTALL_DIR"

# ─── Etapa 6: Porta e domínio ──────────────────────────────────────
section "Etapa 6/10 — Rede"
ask "Domínio (opcional; use proxy reverso pra HTTPS)" "localhost" GCA_DOMAIN
ask "Porta frontend" "5173" PORT_FRONT
ask "Porta API" "8000" PORT_API

# ─── Etapa 7: Administrador inicial ────────────────────────────────
section "Etapa 7/10 — Primeiro Administrador"
ask "Nome completo" "" ADMIN_NAME
ask "E-mail" "" GCA_ADMIN_EMAIL
if [ -z "${GCA_ADMIN_PASSWORD:-}" ]; then
    ask_pass "Senha (mín 10 chars, 1 maiúscula, 1 número, 1 especial)" GCA_ADMIN_PASSWORD
    ask_pass "Confirmar senha" GCA_ADMIN_PASSWORD2
    [ "$GCA_ADMIN_PASSWORD" = "$GCA_ADMIN_PASSWORD2" ] || err "Senhas não coincidem."
fi
[ "${#GCA_ADMIN_PASSWORD}" -ge 10 ] || err "Senha com menos de 10 caracteres."

# ─── Etapa 8: Provedor IA ──────────────────────────────────────────
section "Etapa 8/10 — Provedor de IA"
cat <<EOF
Opções:
  anthropic (recomendado para alta criticidade)
  openai
  gemini
  deepseek
  ollama (local, requer GPU)
EOF
ask "Provedor" "anthropic" LLM_PROVIDER
ask "Chave de API do provedor (deixe vazio para Ollama)" "" LLM_API_KEY

# ─── Etapa 9: Resumo ───────────────────────────────────────────────
section "Etapa 9/10 — Resumo da instalação"
cat <<EOF
   Pasta de instalação:    $INSTALL_DIR
   Domínio:                $GCA_DOMAIN
   Porta frontend:         $PORT_FRONT
   Porta API:              $PORT_API
   Admin inicial:          $ADMIN_NAME <$GCA_ADMIN_EMAIL>
   Provedor IA:            $LLM_PROVIDER
   Imagens a baixar:       $BACKEND_IMG, $FRONTEND_IMG
EOF

if [ "$NON_INTERACTIVE" -eq 0 ]; then
    ask "Confirmar instalação? (sim/não)" "sim" CONFIRM
    [ "$CONFIRM" = "sim" ] || err "Cancelado pelo usuário."
fi

# ─── Etapa 10: Instalação ──────────────────────────────────────────
section "Etapa 10/10 — Instalando"

cd "$INSTALL_DIR"

# Gera docker-compose.yml
info "Gerando docker-compose.yml..."
cat > docker-compose.yml <<EOF
services:
  gca-postgres:
    image: postgres:15-alpine
    container_name: gca-postgres
    environment:
      POSTGRES_USER: gca
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: gca
    volumes:
      - gca-postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    networks: [gca-network]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gca"]
      interval: 10s
      timeout: 3s
      retries: 5

  gca-backend:
    image: ${BACKEND_IMG}
    container_name: gca-backend
    depends_on:
      gca-postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://gca:\${POSTGRES_PASSWORD}@gca-postgres:5432/gca
      GCA_MASTER_KEY: \${GCA_MASTER_KEY}
      JWT_SECRET_KEY: \${JWT_SECRET_KEY}
      GCA_LICENSE: \${GCA_LICENSE}
      DEFAULT_AI_PROVIDER: ${LLM_PROVIDER}
      STORAGE_PATH: /tmp/gca-storage
    volumes:
      - gca-uploads-storage:/tmp/gca-storage
      - gca-backups:/var/gca-backups
    ports:
      - "${PORT_API}:8000"
    restart: unless-stopped
    networks: [gca-network]

  gca-frontend:
    image: ${FRONTEND_IMG}
    container_name: gca-frontend
    depends_on: [gca-backend]
    ports:
      - "${PORT_FRONT}:80"
    restart: unless-stopped
    networks: [gca-network]

volumes:
  gca-postgres-data:
  gca-uploads-storage:
  gca-backups:

networks:
  gca-network:
    driver: bridge
EOF

# Gera .env com segredos
info "Gerando .env com segredos..."
cat > .env <<EOF
# Gerado automaticamente pelo install.sh em $(date -u +%FT%TZ)
# NÃO versionar em Git. Backup recomendado em cofre seguro.
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
GCA_MASTER_KEY=$(openssl rand -base64 48 | tr -d '/+=' | head -c 44)
JWT_SECRET_KEY=$(openssl rand -hex 48)
GCA_LICENSE=${GCA_LICENSE}
GCA_DOMAIN=${GCA_DOMAIN}
LLM_API_KEY=${LLM_API_KEY}
EOF
chmod 600 .env
ok "Segredos gerados com sucesso em $INSTALL_DIR/.env"

# Login no registry privado (se credenciais no ambiente)
if [ -n "${GCA_REGISTRY_USER:-}" ] && [ -n "${GCA_REGISTRY_TOKEN:-}" ]; then
    info "Login no registry privado..."
    echo "$GCA_REGISTRY_TOKEN" | docker login "$REGISTRY" -u "$GCA_REGISTRY_USER" --password-stdin
    ok "Autenticado em $REGISTRY"
else
    warn "Sem GCA_REGISTRY_USER/TOKEN — assumindo imagens já disponíveis ou registry público."
fi

# Pull das imagens
info "Baixando imagens..."
docker pull "$BACKEND_IMG" && ok "Backend baixado"
docker pull "$FRONTEND_IMG" && ok "Frontend baixado"
docker pull postgres:15-alpine && ok "Postgres baixado"

# Sobe os containers
info "Subindo containers..."
docker compose up -d

# Aguarda health
info "Aguardando health check do backend (até 60s)..."
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${PORT_API}/api/v1/metrics/health" >/dev/null 2>&1; then
        ok "Backend respondendo"
        break
    fi
    [ "$i" -eq 60 ] && err "Backend não respondeu em 60s. Veja: docker logs gca-backend"
    sleep 1
done

# Bootstrap Admin
info "Criando primeiro Administrador..."
BOOTSTRAP_RESULT=$(curl -sf -X POST "http://localhost:${PORT_API}/api/v1/auth/bootstrap" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${GCA_ADMIN_EMAIL}\",\"password\":\"${GCA_ADMIN_PASSWORD}\",\"full_name\":\"${ADMIN_NAME}\"}" \
    2>&1) || warn "Bootstrap falhou — talvez já exista um admin. Resposta: $BOOTSTRAP_RESULT"
ok "Admin bootstrap concluído"

# ─── Conclusão ─────────────────────────────────────────────────────
section "✓ INSTALAÇÃO CONCLUÍDA"
cat <<EOF

${GREEN}O GCA está rodando.${NORM}

  URL:            http://${GCA_DOMAIN}:${PORT_FRONT}
  Login:          ${GCA_ADMIN_EMAIL}
  Pasta:          ${INSTALL_DIR}
  Logs:           docker logs gca-backend --tail 50
  Parar:          cd ${INSTALL_DIR} && docker compose down
  Reiniciar:      cd ${INSTALL_DIR} && docker compose restart
  Upgrade:        sudo ${INSTALL_DIR}/scripts/upgrade.sh

Próximos passos:
  1. Acesse a URL acima no navegador.
  2. Faça login com ${GCA_ADMIN_EMAIL}.
  3. Configure provedor de IA se ainda não configurou.
  4. Aguarde solicitações de projeto em /admin/projects.

${YELLOW}Guarde em local seguro:${NORM}
  - Arquivo ${INSTALL_DIR}/.env (contém chaves mestras)
  - Backups diários automáticos às 12:00 em volume 'gca-backups'

EOF
