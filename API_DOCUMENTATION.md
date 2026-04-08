# GCA API Documentation

**Versão**: 0.1.0 | **Base URL**: `http://localhost:8000/api/v1`

Documentação completa interativa: http://localhost:8000/docs (Swagger UI)

---

## 🔐 Autenticação

### Login

```bash
POST /auth/login
Content-Type: application/json

{
  "email": "pielak.ctba@gmail.com",
  "password": "Topazio01#"
}
```

**Resposta**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

### Usar Token

Adicione ao header de todas as requisições:
```
Authorization: Bearer <seu_token>
```

---

## 👥 User Management (4 endpoints)

### GET /admin/users
Listar todos os usuários

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/users
```

**Resposta**:
```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "full_name": "User Name",
      "is_admin": false,
      "is_active": true,
      "created_at": "2026-04-05T..."
    }
  ],
  "count": 5
}
```

### POST /admin/users/{id}/lock
Bloquear usuário

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/users/{id}/lock
```

### POST /admin/users/{id}/unlock
Desbloquear usuário

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/users/{id}/unlock
```

### POST /admin/users/{id}/reset-password
Resetar senha e enviar token

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/users/{id}/reset-password
```

---

## 🚨 Security (2 endpoints)

### GET /admin/suspicious-access
Acessos suspeitos (5+ tentativas falhadas)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/suspicious-access
```

### POST /admin/suspicious-access/{id}/unblock
Desbloquear acesso suspeito

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/suspicious-access/{id}/unblock
```

---

## 🎫 Support Tickets (3 endpoints)

### GET /admin/tickets
Listar tickets com filtros

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/tickets?status=ABERTO&severity=ALTO"
```

**Query Params**:
- `status`: ABERTO, FECHADO, all
- `severity`: BAIXO, MÉDIO, ALTO, CRÍTICO, all
- `limit`: 1-100 (padrão 25)

### GET /admin/tickets/{id}
Detalhes do ticket com respostas

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/tickets/{id}
```

### POST /admin/tickets/{id}/respond
Responder ticket

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Resposta aqui",
    "is_resolution": false
  }' \
  http://localhost:8000/api/v1/admin/tickets/{id}/respond
```

---

## 🔗 Integrations (1 endpoint)

### POST /admin/integrations/webhook-test
Testar webhook

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://hooks.slack.com/services/...",
    "integration_type": "slack"
  }' \
  http://localhost:8000/api/v1/admin/integrations/webhook-test
```

**integration_type**: teams, slack, discord

---

## 🔔 Alerts (2 endpoints)

### GET /admin/alerts/history
Histórico de alertas

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/alerts/history?severity=warning&limit=50"
```

**Query Params**:
- `severity`: critical, warning, info, all
- `status`: pending, acknowledged, all
- `limit`: 1-100

### POST /admin/alerts/{id}/acknowledge
Reconhecer alerta

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/alerts/{id}/acknowledge
```

---

## 📊 Dashboard (1 endpoint)

### GET /admin/dashboard/metrics
Métricas do sistema

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/dashboard/metrics
```

**Resposta**:
```json
{
  "total_users": 5,
  "active_sessions": 2,
  "open_tickets": 3,
  "critical_alerts": 1,
  "system_uptime_percent": 99.9,
  "avg_response_time_ms": 145
}
```

---

## 🌐 Projetos (3 endpoints)

### GET /api/v1/projects
Listar todos os projetos

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/projects
```

### POST /admin/projects
Criar novo projeto

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Meu Projeto",
    "project_slug": "meu-projeto",
    "description": "Descrição"
  }' \
  http://localhost:8000/api/v1/admin/projects
```

### POST /admin/projects/{id}/approve
Aprovar projeto

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/projects/{id}/approve
```

---

## 📋 Status Codes

| Código | Significado |
|--------|-------------|
| **200** | OK — Request bem-sucedido |
| **201** | Created — Recurso criado |
| **400** | Bad Request — Dados inválidos |
| **401** | Unauthorized — Token ausente/inválido |
| **403** | Forbidden — Sem permissão (não-admin) |
| **404** | Not Found — Recurso não existe |
| **500** | Server Error — Erro interno |

---

## 🔄 Exemplos Práticos

### 1. Autenticar e Listar Usuários

```bash
#!/bin/bash

# 1. Login
TOKEN=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' \
  http://localhost:8000/api/v1/auth/login | jq -r '.access_token')

# 2. Usar token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/users | jq
```

### 2. Criar e Aprovar Projeto

```bash
# Criar
PROJECT_ID=$(curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_name":"Novo Projeto",
    "project_slug":"novo-proj",
    "description":"Test"
  }' \
  http://localhost:8000/api/v1/admin/projects | jq -r '.id')

# Aprovar
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/admin/projects/$PROJECT_ID/approve
```

---

## 🔌 Postman / Insomnia

Importar coleção de APIs:

1. Acesse http://localhost:8000/docs
2. Copie URL do OpenAPI: `http://localhost:8000/openapi.json`
3. No Postman: **File** → **Import** → **Link**
4. Cole URL

---

**Próximo**: Leia [DEPLOYMENT.md](DEPLOYMENT.md) para deploy em produção.
