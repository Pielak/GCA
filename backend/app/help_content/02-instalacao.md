# Instalação & primeiro setup

Guia do zero até o primeiro login do Admin.

## Pré-requisitos

- **Docker Engine** 24+ com Docker Compose v2.
- **Portas livres** no host:
  - `5173` — frontend web
  - `8000` — API backend
  - `5432` — PostgreSQL (se expor externamente)
  - `5555` — Flower (monitoramento Celery)
  - `5678` — n8n (opcional)
- **Hardware recomendado**: 4 CPU cores, 8 GB RAM, 40 GB de disco. Projetos com ingestão pesada de documentos ou Ollama local pedem 16 GB+.
- **Domínio próprio** (opcional): quem for expor publicamente configura reverse proxy próprio (nginx, Caddy, Cloudflare Tunnel). O GCA não resolve DNS nem TLS sozinho.

## Os 6 serviços da stack

| Serviço | Container | Função |
|---|---|---|
| Backend API | `gca-backend` | FastAPI: API REST, pipeline OCG, agentes de IA |
| Frontend | `gca-frontend` | Vite preview sobre build estático; UI em React + TypeScript |
| PostgreSQL | `gca-postgres` | Banco principal do produto |
| Redis | `gca-redis` | Broker da fila Celery + result backend |
| Celery worker | `gca-celery-worker` | Processa tarefas assíncronas (ingestão, propagação, geração) |
| Flower | `gca-celery-flower` | Painel em `http://host:5555` para monitorar a fila |

Serviços opcionais: **Ollama** (LLM local) e **n8n** (orquestração externa).

## Passo a passo

### 1. Clonar o repositório

```bash
git clone <url-do-repo>/gca.git
cd gca
```

### 2. Configurar o .env

Copie `.env.example` para `.env` e ajuste:

```bash
# Banco
POSTGRES_USER=gca
POSTGRES_PASSWORD=<senha-forte>
POSTGRES_DB=gca

# Autenticação (JWT)
JWT_SECRET=<secret-aleatório-64+-caracteres>
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Criptografia do Vault (obrigatório)
VAULT_MASTER_KEY=<chave-fernet>
# Gerar uma chave:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Provedor de IA padrão da instância
DEFAULT_AI_PROVIDER=anthropic   # anthropic | openai | deepseek | ollama
ANTHROPIC_API_KEY=<sua-chave>

# SMTP (opcional, recomendado para convites)
SMTP_HOST=<host>
SMTP_PORT=587
SMTP_USER=<user>
SMTP_PASSWORD=<senha>
SMTP_FROM_EMAIL=<email-from>
```

**Importante**: `JWT_SECRET` e `VAULT_MASTER_KEY` precisam ter entropia real. Não reutilize entre instâncias. A `VAULT_MASTER_KEY` protege todas as chaves de API e tokens Git do sistema — perdê-la significa perder acesso aos segredos.

### 3. Subir a stack

```bash
docker compose up -d
```

**Sem argumentos.** Isso sincroniza todos os serviços declarados. Se você alterar `docker-compose.yml` depois (adicionar serviço, mudar porta, env var, volume), rode `docker compose up -d` de novo — sem isso, as mudanças ficam declaradas mas não refletem nos containers rodando.

Aguarde ~1 minuto até todos ficarem `healthy`:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### 4. Migrações do banco

Executadas automaticamente quando o backend sobe. Se precisar rodar manualmente:

```bash
docker exec gca-backend alembic upgrade head
```

### 5. Wizard de setup inicial

Acesse `http://localhost:5173/setup` (ou a URL do seu domínio).

A rota `/setup` é **pública apenas enquanto não existir nenhum usuário** na instância. O wizard pede:

1. **Dados do primeiro Admin**: nome, email, senha (mínimo 12 caracteres com letras, números e símbolos).
2. **Organização inicial**: nome e slug (ex.: "Acme Ltda" → `acme`).
3. **Provedor de IA da instância** (opcional nesta tela): cole a chave; o wizard valida antes de salvar.

Ao concluir:

- O primeiro Admin fica ativo com permissão total.
- A rota `/setup` passa a retornar 403 em acessos subsequentes.
- Você é redirecionado para `/login`.

### 6. Primeiro login

Em `http://localhost:5173/login` entre com o email + senha do Admin criado.

Admin cai em `/admin` (dashboard). Veja [cap. 6 — Admin](?section=06-admin) para o tour.

## Configuração do provedor de IA (pós-setup)

Em `/admin` → aba **"Provedores de IA"** você pode:

- **Adicionar provedor**: Anthropic, OpenAI, DeepSeek ou Ollama (local).
- **Validar a chave** com o botão "Testar" antes de salvar — o sistema faz um ping autenticado.
- **Definir o padrão da instância** (usado pelo pipeline administrativo).
- **Remover** ou **substituir** uma chave já existente.

As chaves são armazenadas criptografadas no Vault.

### Separação: chaves da instância vs chaves do projeto

Cada projeto pode ter **chaves próprias** configuradas pelo GP em `/projects/:id/settings` → aba IA.

- **Chaves globais (Admin)**: usadas por operações do pipeline administrativo (geração inicial do OCG, reconsolidação, análise de qualidade). Custo fica com a instância.
- **Chaves do projeto (GP)**: usadas por operações diárias do projeto (Arguidor, ingestão, CodeGen). Custo fica com o projeto.

Essa separação permite que o Admin opere a instância com chaves próprias enquanto cada projeto arca com o próprio consumo de IA.

## Healthchecks e verificação pós-instalação

| Verificação | Comando |
|---|---|
| Backend responde | `curl -fsS http://localhost:8000/api/v1/setup/status` |
| Banco ok | `docker exec gca-postgres pg_isready -U gca` |
| Redis ok | `docker exec gca-redis redis-cli ping` |
| Celery worker ativo | `docker exec gca-backend python -c "from app.celery_app import celery_app; print(celery_app.send_task('app.celery_app.ping').get(timeout=10))"` |
| Flower UI | `curl -fsS http://localhost:5555/` |

Detalhes em [cap. 9 — Observabilidade](?section=09-observabilidade).

## Upgrade do GCA

Cada release traz tag semântica + changelog. Rotina padrão:

```bash
git pull
docker compose pull        # se as imagens vêm do registry
docker compose up -d       # sincroniza mudanças do compose
docker exec gca-backend alembic upgrade head   # migrações
```

Migrações destrutivas (drop, rename) disparam snapshot automático antes de rodar. O changelog da release informa se o upgrade é destrutivo.

## Problemas comuns na instalação

- **`gca-celery-flower` não responde**: rode `docker compose up -d celery-flower`. Comum quando o compose foi atualizado mas `up -d` não foi re-executado.
- **`gca-celery-worker` aparece `unhealthy`**: veja os logs com `docker logs gca-celery-worker --tail 50`. Se o worker responde a `ping` mas o healthcheck falha, provavelmente o compose não foi sincronizado.
- **Backend reclama `DATABASE_URL` não definido**: `.env` ausente ou não montado. Confirme com `docker exec gca-backend env | grep DATABASE_URL`.
- **Convite por email não chega**: SMTP não configurado ou credenciais inválidas. Em ambiente de dev, a aba **Equipe** do projeto mostra o link de aceite mesmo sem email — copie e cole no destinatário.
- **Wizard `/setup` retorna 403**: já existe usuário na instância. Se precisa recomeçar, apague a tabela `users` via `docker exec gca-postgres psql -U gca -d gca -c "DELETE FROM users"` (isto apaga todos os usuários; só faça em ambiente descartável).

Mais diagnósticos em [cap. 10 — Solução de problemas](?section=10-troubleshooting).
