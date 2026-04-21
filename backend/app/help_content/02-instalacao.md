# Instalação & primeiro setup

O GCA roda como stack Docker Compose com 6 serviços canônicos. Este capítulo orienta do zero até o primeiro login do Admin.

## Pré-requisitos

- **Docker Engine** 24+ com Docker Compose v2.
- **Portas livres** no host: `5173` (frontend), `8000` (backend API), `5432` (Postgres externo), `5555` (Flower), `5678` (n8n opcional).
- **Hardware mínimo**: 4 CPU cores, 8 GB RAM, 40 GB de disco (produção em projeto pequeno pode ficar abaixo disso; instâncias com ingestão pesada e Ollama local pedem 16 GB+).
- **Domínio opcional**: clientes que queiram expor publicamente configuram reverse proxy próprio (nginx, Caddy, Cloudflare Tunnel). O GCA não resolve DNS/TLS sozinho.

## Stack canônica de serviços

| Serviço | Container | Papel |
|---|---|---|
| `gca-backend` | FastAPI + uvicorn | API, pipeline OCG, agentes IA |
| `gca-frontend` | Vite preview sobre build estático | UI em React + TypeScript |
| `gca-postgres` | PostgreSQL 16 | Banco principal do produto |
| `gca-redis` | Redis 7 | Broker Celery (DB 1) + result backend (DB 2) |
| `gca-celery-worker` | Celery worker | Tasks assíncronas (ingestão, propagação OCG, geração, etc) |
| `gca-celery-flower` | Flower UI | Monitoramento Celery em `http://host:5555` |

Serviços opcionais: `gca-ollama` (LLM local) e `n8n` (orquestração externa).

## Passo a passo da instalação

### 1. Clonar o repositório

```bash
git clone <url-do-repo-cliente>/gca.git
cd gca
```

### 2. Configurar variáveis de ambiente

Copie `.env.example` para `.env` e ajuste:

```bash
# Banco
POSTGRES_USER=gca
POSTGRES_PASSWORD=<SENHA-FORTE>
POSTGRES_DB=gca

# JWT
JWT_SECRET=<SECRET-RANDOM-64+>
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Criptografia do Vault
VAULT_MASTER_KEY=<FERNET-KEY-GERADA>   # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

# Provedor IA default da instância (admin)
DEFAULT_AI_PROVIDER=anthropic   # anthropic | openai | deepseek | ollama
ANTHROPIC_API_KEY=<chave-admin>

# SMTP (opcional, mas recomendado para convites)
SMTP_HOST=<host>
SMTP_PORT=587
SMTP_USER=<user>
SMTP_PASSWORD=<senha>
SMTP_FROM_EMAIL=<from>
```

Regra dura: `JWT_SECRET` e `VAULT_MASTER_KEY` precisam ter entropia real. Não reutilize entre instâncias.

### 3. Subir a stack

```bash
docker compose up -d
```

Roda sem argumentos — sincroniza **todos** os serviços declarados. Após qualquer mudança em `docker-compose.yml`, execute `docker compose up -d` novamente (regra dura em `CLAUDE.md §12`; sem isso serviços novos ficam declarados mas não rodando).

Aguarde ~1 min até todos ficarem `healthy`:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### 4. Migrações do banco

Executadas automaticamente no startup do `gca-backend` via Alembic. Se precisar rodar manualmente:

```bash
docker exec gca-backend alembic upgrade head
```

### 5. Wizard de setup inicial

Acesse `http://localhost:5173/setup` (ou a URL do seu domínio). A rota `/setup` é **pública apenas enquanto não existir nenhum usuário** na instância. O wizard pede:

1. **Dados do primeiro Admin**: nome, email, senha (mínimo 12 caracteres com mix de case/número/símbolo).
2. **Organização inicial**: nome e slug (ex: "Acme Ltda" → `acme`).
3. **Provedor de IA da instância (opcional)**: cola chave + valida via endpoint de teste.

Ao concluir, o wizard:

- Cria o registro `users` com `is_admin=true` + `is_active=true`.
- Cria a `organization` vinculada.
- Bloqueia a rota `/setup` (volta HTTP 403 em acessos subsequentes).
- Redireciona para `/login`.

### 6. Primeiro login

`http://localhost:5173/login` — entre com email + senha do Admin criado. Admin cai em `/admin` (dashboard). Veja [cap. 6](?section=06-admin) para o tour da área administrativa.

## Configuração do provedor de IA (pós-setup)

Em `/admin` → aba **"Provedores de IA"**:

- Adicionar provedor: Anthropic, OpenAI, DeepSeek, ou Ollama (local).
- Validação da chave antes de salvar (endpoint ping interno).
- Definir provedor padrão da instância.
- Chaves ficam criptografadas (AES-GCM via Fernet com `VAULT_MASTER_KEY`).

Cada projeto pode ter chaves **próprias** separadas das globais (compartimentalização §6.5 do contrato). Chave global é usada apenas por operações do pipeline Admin (geração inicial de OCG, reconsolidation pós-ingestão, etc).

## Healthchecks e verificação

| Verificação | Comando |
|---|---|
| Backend responde | `curl -fsS http://localhost:8000/api/v1/setup/status` |
| Banco ok | `docker exec gca-postgres pg_isready -U gca` |
| Redis ok | `docker exec gca-redis redis-cli ping` |
| Celery worker ativo | `docker exec gca-backend python -c "from app.celery_app import celery_app; print(celery_app.send_task('app.celery_app.ping').get(timeout=10))"` |
| Flower UI | `curl -fsS http://localhost:5555/` |

Detalhes em [cap. 9 — Observabilidade](?section=09-observabilidade).

## Upgrade do GCA

Cada release do GCA traz tag semântica + changelog. Rotina canônica:

```bash
git pull
docker compose pull        # se imagens vêm do registry
docker compose up -d       # sincroniza mudanças do compose
docker exec gca-backend alembic upgrade head   # migrations
```

Migrations destrutivas (drops, renames) disparam snapshot automático (MVP 7) — a release nota informa se aplica.

## Pontos de falha comuns (pós-install)

- `gca-celery-flower` não responde: serviço pode não ter subido. Rodar `docker compose up -d celery-flower`. Ver DT-077 em [cap. 10](?section=10-troubleshooting).
- `gca-celery-worker` aparece `unhealthy` mas worker responde ping: bug histórico já mitigado em MVP 17. Se persistir, conferir o `docker-compose.yml` está sincronizado com o último `docker compose up -d`.
- Backend reclama `DATABASE_URL` não definido: arquivo `.env` ausente ou não montado. Confirme com `docker exec gca-backend env | grep DATABASE_URL`.
- Convite por email não chega: SMTP não configurado ou credenciais inválidas. Em dev, a aba **Equipe** do projeto mostra o link de aceite mesmo sem email.

Glossário de termos técnicos deste capítulo em [cap. 1 — Glossário](?section=01-visao-geral).
