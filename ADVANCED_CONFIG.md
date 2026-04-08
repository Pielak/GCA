# ⚙️ Configuração Avançada — GCA Enterprise Setup

## Data: 4 de Abril de 2026

Esta documentação cobre as configurações avançadas e setup para ambiente de produção.

---

## 📋 Novas Configurações Adicionadas

### 1. **App Configuration**
```env
APP_ENV=development          # development, staging, production
APP_SECRET_KEY=e2bed0c...    # Secret geral da aplicação
FRONTEND_URL=http://localhost:5173
```

**Uso:**
- `APP_ENV` — Determina comportamento (logs, debug, etc)
- `APP_SECRET_KEY` — Usado para operações gerais (não é JWT)
- `FRONTEND_URL` — URL do frontend (CORS, redirects)

---

### 2. **Admin Seed (Primeiro Boot)**
```env
ADMIN_EMAIL=pielak.ctba@gmail.com
ADMIN_TEMP_PASSWORD=ChangeMe@123
```

**Função:**
- Criado automaticamente no primeiro boot
- Usuário deve trocar senha no login
- Ideal para setup sem SMTP

**Fluxo:**
1. Primeira execução → Admin criado com email/senha acima
2. Admin faz login
3. Sistema força change password
4. Novo admin configurado

---

### 3. **JWT RS256 (Assimétrico)**
```env
JWT_PRIVATE_KEY_PATH=/app/certs/private.pem
JWT_PUBLIC_KEY_PATH=/app/certs/public.pem
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
SESSION_INACTIVITY_HOURS=8
```

**Vantagens do RS256 vs HS256:**
- **HS256** (Simétrico): Uma chave secreta
  - ✅ Simples
  - ❌ Se comprometer, token falso pode ser criado
  
- **RS256** (Assimétrico): Chave privada + pública
  - ✅ Mais seguro
  - ✅ Pode distribuir chave pública (p.ex. microserviços)
  - ✅ Melhor para arquitetura distribuída

**Como gerar as chaves:**
```bash
# Gerar private key (2048 bits)
openssl genrsa -out private.pem 2048

# Extrair public key
openssl rsa -in private.pem -pubout -out public.pem

# Converter para base64 (se usar em variáveis de ambiente)
base64 -w 0 private.pem > private.pem.b64
base64 -w 0 public.pem > public.pem.b64
```

**Fluxo de geração de token:**
```
1. User faz login
2. Servidor gera JWT assinado com PRIVATE_KEY (RS256)
3. Cliente armazena token
4. Cliente envia token em Authorization header
5. Servidor valida com PUBLIC_KEY

Benefício: Outro servidor pode validar o token usando APENAS public.pem
```

---

### 4. **PostgreSQL Assíncrono**
```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=gca
POSTGRES_USER=gca
POSTGRES_PASSWORD=gca_secret
DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca
DATABASE_BACKUP_URL=postgresql+asyncpg://gca:gca_secret@postgres-backup:5432/gca
```

**Diferenças:**
- `postgresql://` — Síncrono (psycopg2)
- `postgresql+asyncpg://` — Assíncrono (melhor para FastAPI)

**Uso de DATABASE_BACKUP_URL:**
- Readiness para replicação/failover
- Setup de backup automático
- Sincronização de dados

---

### 5. **Redis com Separação de Componentes**
```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0
REDIS_DECODE_RESPONSES=True
```

**Uso:**
- Cache de dados
- Session storage
- Rate limiting
- Pub/Sub para eventos

---

### 6. **Kafka Topics para Event Streaming**
```env
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC_CODEGEN=gca.codegen.jobs
KAFKA_TOPIC_LEGACY=gca.legacy.analysis
KAFKA_TOPIC_ARTIFACT=gca.artifact.ingest
KAFKA_TOPIC_GATEKEEPER=gca.gatekeeper.evaluate
```

**Propósito de cada topic:**

| Topic | Fase | Propósito |
|-------|------|-----------|
| gca.codegen.jobs | M8 | Jobs de geração de código |
| gca.legacy.analysis | M2 | Análise de código legado |
| gca.artifact.ingest | M4 | Ingestão de artefatos |
| gca.gatekeeper.evaluate | M6 | Avaliações Gatekeeper |

**Arquitetura:**
```
┌─────────────┐
│  Router     │ ─→ Publica evento em Kafka
└─────────────┘
        ↓
┌─────────────┐
│   Kafka     │ ─→ Tópico: gca.codegen.jobs
│ (Bus Evt)   │
└─────────────┘
        ↓
┌─────────────┐
│  Consumer   │ ─→ Processa em background
│  (Worker)   │
└─────────────┘
```

**Exemplo de uso:**
```python
# 1. Router (FastAPI)
@router.post("/generate-code")
async def generate_code(req: CodeRequest):
    # Publica na queue
    await kafka_producer.send_and_wait(
        "gca.codegen.jobs",
        json.dumps({
            "project_id": req.project_id,
            "requirements": req.requirements
        }).encode()
    )
    return {"status": "job queued"}

# 2. Consumer (Background Worker)
async def process_codegen_jobs():
    async for msg in consumer:
        job = json.loads(msg.value)
        code = await generate_with_claude(job)
        # Salva resultado no BD
        # Notifica usuário
```

---

## 🔐 Segurança para Produção

### Antes de Deploy

#### 1. Gerar Chaves RS256
```bash
cd /home/luiz/GCA/backend/certs
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem

# Verificar
ls -la
# private.pem (400 bytes)
# public.pem  (400 bytes)
```

#### 2. Atualizar Variáveis Críticas

**Em Vault ou AWS Secrets Manager:**
```
APP_SECRET_KEY           → Gerar novo (64 chars)
APP_ENV                  → "production"
ADMIN_EMAIL             → Email real do admin
ADMIN_TEMP_PASSWORD     → Senha temporária complexa (mín 20 chars)
JWT_PRIVATE_KEY_PATH    → /app/certs/private.pem
POSTGRES_PASSWORD       → Senha complexa
GROK_API_KEY            → Verificar quota
ANTHROPIC_API_KEY       → Verificar quota
```

#### 3. Audit Log
```
Manter histórico de:
- Quem gerou novas chaves RS256
- Quando foi rotação de credenciais
- Qual foi a versão anterior
```

---

## 📊 Fluxo de Autenticação RS256

```
┌─────────────────────────────────────────────────────┐
│                    Cliente (UI)                     │
│                                                     │
│  1. Login com email/password                        │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│                  Backend (FastAPI)                  │
│                                                     │
│  2. Validar credenciais no BD                       │
│  3. Gerar JWT assinado com PRIVATE_KEY (RS256)      │
│  4. Retornar {access_token, refresh_token}          │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│              Cliente armazena token                 │
│                                                     │
│  localStorage: {                                    │
│    access_token: "eyJhbGc...",                      │
│    refresh_token: "eyJhbGc...",                     │
│    expires_in: 3600                                 │
│  }                                                  │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│        Próximas requests (com Authorization)        │
│                                                     │
│  GET /api/v1/projects                               │
│  Authorization: Bearer eyJhbGc...                    │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│           Middleware (JWT Validation)               │
│                                                     │
│  1. Extract token do Authorization header           │
│  2. Validar assinatura com PUBLIC_KEY (RS256)       │
│  3. Se válido: prosseguir                           │
│  4. Se expirado: retornar 401 (client faz refresh)  │
└────────────────────┬────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────┐
│                  Route Handler                      │
│                                                     │
│  @router.get("/projects")                           │
│  async def list_projects(current_user = ...):       │
│    # current_user já foi validado                   │
│    return projects                                  │
└─────────────────────────────────────────────────────┘
```

---

## 📈 Escalabilidade com Kafka

Kafka permite escalabilidade horizontal:

```
Caso 1: Sem Kafka (Bloqueante)
┌──────────┐
│ FastAPI  │ ─→ Gera código (5 min) ─→ Bloqueia request
│ (1 inst) │
└──────────┘
Problema: Timeout se > 30s

Caso 2: Com Kafka (Assíncrono)
┌──────────┐  ┌───────┐  ┌──────────┐  ┌──────────┐
│ FastAPI  │─→│Kafka  │←─│ Worker 1 │  │ Worker 2 │
│ (N inst) │  │ Topic │  │ (CPU)    │  │ (CPU)    │
└──────────┘  └───────┘  └──────────┘  └──────────┘
Vantagem: 
  - Request retorna imediatamente
  - Workers processam em background
  - Pode escalar workers conforme necessário
```

---

## 🧪 Testar Configuração

```bash
# 1. Verificar arquivo .env
cd /home/luiz/GCA/backend
cat .env | grep APP_ENV

# 2. Iniciar FastAPI
poetry run uvicorn app.main:app --reload

# 3. Verificar logs
# Deve aparecer:
# INFO:     Application startup complete

# 4. Testar endpoint
curl http://localhost:8000/health
```

---

## 📋 Checklist para Produção

### Setup
- [ ] Gerar chaves RS256 (`openssl genrsa`)
- [ ] Gerar APP_SECRET_KEY (openssl rand -hex 32)
- [ ] Definir ADMIN_EMAIL e ADMIN_TEMP_PASSWORD
- [ ] Atualizar POSTGRES_PASSWORD
- [ ] Atualizar REDIS_HOST/PORT (servidor remoto)
- [ ] Atualizar KAFKA_BOOTSTRAP_SERVERS

### Segurança
- [ ] APP_ENV="production"
- [ ] Chaves RS256 em /app/certs/ (não em .env)
- [ ] Todos os secrets em Vault/AWS Secrets Manager
- [ ] JWT_ACCESS_TOKEN_EXPIRE_MINUTES reduzido (30-60)
- [ ] SESSION_INACTIVITY_HOURS configurado (8h)
- [ ] CORS_ORIGINS com domínios reais
- [ ] DEBUG=False

### Monitoramento
- [ ] Logs estruturados (LOG_FORMAT=json)
- [ ] LOG_LEVEL=INFO (não DEBUG)
- [ ] Alertas para token expiration
- [ ] Alertas para database backup falhar
- [ ] Metrics de Kafka lag

---

## 🚀 Docker Compose (Recomendado)

Para ambiente produção-like:

```yaml
version: "3.8"
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: gca
      POSTGRES_USER: gca
      POSTGRES_PASSWORD: gca_secret
    ports:
      - "5432:5432"
  
  postgres-backup:
    image: postgres:15
    environment:
      POSTGRES_DB: gca
      POSTGRES_USER: gca
      POSTGRES_PASSWORD: gca_secret
    ports:
      - "5433:5432"
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    ports:
      - "9092:9092"
  
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
```

---

## 📚 Documentação Relacionada

- `CREDENTIALS_SUMMARY.md` — Gerenciamento de credenciais
- `GITHUB_INTEGRATION.md` — Setup GitHub
- `EMAIL_NOTIFICATION.md` — Setup SMTP
- `AI_PROVIDERS.md` — IA providers
- `.env` — Valores atuais
- `.env.example` — Template

---

## 🔗 Próximas Implementações

### Phase 4: OCG Wizard
- Usar admin seed para bootstrap
- JWT RS256 em todos os endpoints

### Phase 8: Code Generator
- Publicar jobs em KAFKA_TOPIC_CODEGEN
- Workers processam async

### Monitoramento & Observability
- Logs JSON estruturados
- Métricas de token expiration
- Alerts de database/redis

---

## 📞 Suporte

**Erro: "Cannot read private key"**
- Verificar caminho JWT_PRIVATE_KEY_PATH
- Permissões de arquivo (chmod 400)

**Erro: "Token signature invalid"**
- Chaves foram regeneradas?
- Clientes tem token antigo?
- Fazer logout/login

**Erro: "Kafka broker not found"**
- Verificar KAFKA_BOOTSTRAP_SERVERS
- Kafka está rodando?
- Porta 9092 aberta?

---

**Data**: 4 de Abril de 2026  
**Status**: ✅ Configuração completa  
**Próximo**: Deploy em docker-compose ou kubernetes  

🚀 **GCA está pronto para ambiente enterprise!**
