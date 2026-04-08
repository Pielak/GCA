# GCA Setup Guide

**Versão**: 0.1.0 | **Data**: 2026-04-05

---

## 📋 Pré-requisitos

- Docker & Docker Compose
- Git
- 5GB espaço em disco livre
- Portas livres: 8000 (backend), 5173 (frontend), 5432 (postgres), 6379 (redis)

---

## 🚀 Instalação Rápida

### 1. Clone e Configure

```bash
cd /home/luiz/GCA
git pull origin master
```

### 2. Inicie os Containers

```bash
docker-compose up -d
```

Aguarde ~30 segundos para os containers iniciarem.

### 3. Verifique o Status

```bash
docker-compose ps
```

Esperado:
```
NAME              STATUS
gca-backend       Up (healthy)
gca-postgres      Up (healthy)
gca-redis         Up (healthy)
gca-frontend      Up
```

### 4. Teste a Conexão

```bash
# Backend health check
curl http://localhost:8000/health

# Resposta esperada:
{"status":"ok","version":"0.1.0"}
```

---

## 👤 Admin Login

### Credenciais Padrão

```
Email: pielak.ctba@gmail.com
Senha: Topazio01#
```

### Acessar Admin Dashboard

1. Abra http://localhost:5173
2. Digite as credenciais acima
3. Clique em "Entrar"

---

## 🎯 Primeira Utilização

### 1. Navegação Admin

No sidebar esquerdo:
- **Dashboard** — Métricas do sistema
- **Parametrização** — SMTP, IA Providers, N8N
- **Projetos** — Criar/aprovar projetos
- **Usuários** — Gerenciar usuários
- **Segurança** — Suspicious access tracking
- **Tickets** — Support tickets
- **Integrações** — Webhook testing
- **Alertas** — System alerts

### 2. Configurar SMTP

Para enviar emails de credenciais:

1. Vá para **Parametrização** → **SMTP**
2. Configure:
   - **Servidor**: `smtp.gmail.com`
   - **Porta**: `587`
   - **Usuário**: seu email Gmail
   - **Senha**: app password (não senha normal!)
3. Clique em **Enviar Email de Teste**

### 3. Configurar IA Provider

Para análise de requisitos:

1. Vá para **Parametrização** → **IA Providers**
2. Selecione um provider (Claude, GPT-4, Grok, DeepSeek)
3. Cole sua API Key
4. Clique em **Testar Conexão**

### 4. Criar Primeiro Projeto

1. Vá para **Projetos**
2. Clique em **Novo Projeto**
3. Preencha:
   - Nome do Projeto
   - Slug (ex: `meu-projeto`)
   - Descrição
4. Clique em **Criar Projeto**

---

## 🔧 Desenvolvimento Local

### Backend

```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload
```

Backend estará em http://localhost:8000

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend estará em http://localhost:5173

### Testes

```bash
cd backend
poetry run pytest -v
```

---

## 🐛 Troubleshooting

### Containers não iniciam

```bash
# Ver logs
docker-compose logs -f gca-backend

# Reiniciar tudo
docker-compose down
docker-compose up -d
```

### Porta já em uso

```bash
# Liberar porta 8000
sudo lsof -i :8000
sudo kill -9 <PID>

# Ou mudar porta em docker-compose.yml
```

### Backend não conecta ao banco

```bash
# Verificar banco
docker-compose exec gca-postgres psql -U postgres -l

# Reset banco (⚠️ deleta dados)
docker-compose exec gca-postgres psql -U postgres -c "DROP DATABASE IF EXISTS gca; CREATE DATABASE gca;"
```

### Frontend não vê backend

1. Verificar CORS em `backend/app/main.py`
2. Verificar env var:
   ```bash
   # frontend/.env.local
   VITE_API_BASE_URL=http://localhost:8000/api/v1
   ```
3. Limpar cache:
   ```bash
   npm run dev -- --force
   ```

---

## 📊 Monitoramento

### Health Check

```bash
curl http://localhost:8000/health
```

### Logs

```bash
# Todos os serviços
docker-compose logs -f

# Apenas backend
docker-compose logs -f gca-backend

# Apenas frontend
docker-compose logs -f gca-frontend
```

### Database

```bash
# Conectar ao PostgreSQL
docker-compose exec gca-postgres psql -U postgres -d gca

# Ver tabelas
\dt

# Sair
\q
```

---

## 🔐 Segurança

### Mudança de Senha Admin

1. No admin dashboard, clique no avatar (canto superior direito)
2. Selecione **Configurações** → **Alterar Senha**
3. Digite nova senha

### Adicionar Novo Usuário Admin

No banco PostgreSQL:

```sql
INSERT INTO users (id, email, password_hash, full_name, is_admin, is_active, created_at)
VALUES (
  gen_random_uuid(),
  'novo-admin@example.com',
  crypt('senha123', gen_salt('bf')),
  'Novo Admin',
  true,
  true,
  now()
);
```

---

## 📦 Backup & Restore

### Backup do Banco

```bash
docker-compose exec gca-postgres pg_dump -U postgres gca > backup.sql
```

### Restore

```bash
docker-compose exec gca-postgres psql -U postgres gca < backup.sql
```

---

## ✅ Verificação Pós-Setup

- [ ] Backend respondendo http://localhost:8000/health
- [ ] Frontend carregando http://localhost:5173
- [ ] Login funcionando
- [ ] Navegação por todas as 8 páginas
- [ ] Envio de email de teste
- [ ] Teste de IA Provider

---

**Próximo**: Leia [API_DOCUMENTATION.md](API_DOCUMENTATION.md) para integrar com suas aplicações.
