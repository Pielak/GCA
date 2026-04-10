# 🚀 GCA Backend — Quick Start (Desenvolvimento)

## 1️⃣ Pré-requisitos

```bash
# Python 3.11+
python3 --version

# PostgreSQL
psql --version

# Git
git --version
```

---

## 2️⃣ Setup Inicial

```bash
# Navegue até o backend
cd /home/luiz/GCA/backend

# Instale Poetry (gerenciador de dependências)
pip install poetry

# Instale as dependências do projeto
poetry install
```

---

## 3️⃣ Configure o Banco de Dados

```bash
# Crie o banco de dados
createdb gca_dev

# Importe o schema
psql gca_dev < ../BD_SCHEMA.sql

# Verifique se foi criado
psql gca_dev -c "\dt"  # Lista tabelas
```

---

## 4️⃣ Configure Variáveis de Ambiente

O arquivo `.env` já foi criado com:
- ✅ `GITHUB_TOKEN` — Token GitHub Classic
- ✅ `GITHUB_REPO_URL` — https://github.com/Pielak/GCA.git
- ✅ Credenciais de banco de dados

**Se tiver que ajustar:**
```bash
# Edite .env conforme necessário
nano .env

# Variáveis importantes:
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/gca_dev"
GITHUB_TOKEN="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"
SECRET_KEY="dev-secret-key-change-in-production"
```

---

## 5️⃣ Rode o Backend

```bash
# Ative o ambiente Poetry
poetry shell

# Ou rode um comando direto com Poetry
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Esperado:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process
```

---

## 6️⃣ Teste a API

### Health Check
```bash
curl http://localhost:8000/health
# Retorna: {"status": "ok", "version": "0.1.0"}
```

### Root Endpoint
```bash
curl http://localhost:8000/
# Retorna: {"app": "GCA - Gerenciador Central de Arquiteturas", ...}
```

### Documentação Interativa
Abra no navegador:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🧪 Testar Endpoints de Auth

### 1. Bootstrap Admin (Criar primeiro usuário)

```bash
curl -X POST http://localhost:8000/api/v1/auth/bootstrap-admin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "full_name": "Admin User",
    "password": "SecurePassword123!@#"
  }'
```

**Resposta esperada:**
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 2. Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "SecurePassword123!@#"
  }'
```

### 3. Get Current User (requer token)

```bash
# Substitua YOUR_TOKEN pelo access_token recebido
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4. Refresh Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "YOUR_REFRESH_TOKEN"}'
```

### 5. Change Password (requer token)

```bash
curl -X POST http://localhost:8000/api/v1/auth/change-password \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "SecurePassword123!@#",
    "new_password": "NewSecurePassword456!@#"
  }'
```

---

## 📊 Verificar Banco de Dados

```bash
# Conecte ao banco
psql gca_dev

# Listar usuários criados
SELECT id, email, full_name, is_admin FROM users;

# Listar tabelas
\dt public.*

# Ver estrutura de uma tabela
\d users

# Sair
\q
```

---

## 🐛 Troubleshooting

### Erro: "could not connect to database"
```bash
# Verifique se PostgreSQL está rodando
sudo systemctl status postgresql

# Inicie se necessário
sudo systemctl start postgresql

# Verifique DATABASE_URL no .env
```

### Erro: "Table 'users' does not exist"
```bash
# Re-importe o schema
psql gca_dev < ../BD_SCHEMA.sql
```

### Erro: "ModuleNotFoundError: No module named 'fastapi'"
```bash
# Reinstale as dependências
poetry install
```

### Erro: "ENCRYPTION_KEY has invalid length"
```bash
# Gere uma chave válida (base64 encoded 32 bytes)
python3 -c "
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
"
# Copie o resultado para ENCRYPTION_KEY no .env
```

---

## 📝 Logs & Debug

### Ver logs estruturados
O backend usa `structlog` para JSON logging:
```
{"event": "gca.startup", "version": "0.1.0"}
{"event": "gca.database_ready"}
{"event": "auth.login_success", "user_id": "xxx", "email": "admin@example.com"}
```

### Ativar DEBUG mode
No `.env`:
```
DEBUG=True
LOG_LEVEL="DEBUG"
```

---

## 📚 Documentação

- **ARQUITETURA.md** — Visão geral da arquitetura
- **GITHUB_INTEGRATION.md** — Setup do token GitHub
- **PHASE3_IMPLEMENTATION.md** — Detalhes técnicos do Phase 3
- **README.md** — Guia completo do projeto

---

## ✅ Checklist de Setup

- [x] Python 3.11+ instalado
- [x] PostgreSQL instalado e rodando
- [x] Poetry instalado
- [x] Dependências instaladas (`poetry install`)
- [x] Banco de dados criado e schema importado
- [x] `.env` configurado
- [x] Backend rodando (`poetry run uvicorn app.main:app --reload`)
- [x] API respondendo em http://localhost:8000/health

---

## 🚀 Próximas Ações

1. **Explore a API**
   - Abra http://localhost:8000/docs
   - Teste os endpoints no Swagger UI

2. **Crie o primeiro usuário**
   - Rode o endpoint `/api/v1/auth/bootstrap-admin`

3. **Teste autenticação**
   - Login com as credenciais criadas
   - Obtenha access token
   - Acesse `/api/v1/auth/me`

4. **Implemente Phase 4**
   - User management (CRUD)
   - Organizations CRUD
   - OCG Wizard 4 steps

---

**Última atualização**: 2026-04-04  
**Backend Version**: 0.1.0  
**Status**: ✅ Pronto para desenvolvimento
