# 🌐 Cloudflare Tunnel Configuration — GCA

## Análise do config.yml

### ⚠️ Problemas Identificados

#### 1. **GCA apontando para porta 5174 (INCORRETO)**
```yaml
- hostname: gca.code-auditor.com.br
  service: http://localhost:5174  ❌ ERRADO
```

**Problema:**
- Porta 5174 é provavelmente frontend React (desenvolvimento)
- GCA backend FastAPI roda na porta **8000**
- Porta 5173 é padrão Vite (se usar Vite)

**Solução:**
```yaml
- hostname: gca.code-auditor.com.br
  service: http://localhost:5173  ✅ CORRETO (ou 3000 se usar React)
```

---

#### 2. **Duplicação de API Backend**
```yaml
- hostname: api.code-auditor.com.br
  service: http://localhost:8000
- hostname: gpd.code-auditor.com.br
  service: http://localhost:8000  # Mesmo serviço!
```

**Problema:**
- Ambos apontam para mesma porta
- Pode causar conflitos se ambas receberem requisições
- Confusão entre GPD (antigo) e GCA (novo)

**Solução (Recomendado):**
```yaml
# OPÇÃO 1: Manter apenas GCA (recomendado)
- hostname: api.code-auditor.com.br
  service: http://localhost:8000  ✅ GCA Backend
- hostname: gca.code-auditor.com.br
  service: http://localhost:5173  ✅ GCA Frontend

# OPÇÃO 2: Se ainda precisa de GPD
- hostname: api.code-auditor.com.br
  service: http://localhost:8000  # GCA API (porta 8000)
- hostname: gpd-api.code-auditor.com.br
  service: http://localhost:9000  # GPD API (porta diferente)
- hostname: gpd.code-auditor.com.br
  service: http://localhost:3001  # GPD Frontend (porta diferente)
```

---

#### 3. **CORS: Frontend e API em domínios diferentes**

Se frontend está em `gca.code-auditor.com.br` e API em `api.code-auditor.com.br`, precisa de CORS!

**Solução em FastAPI (app/main.py):**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",           # Dev
        "http://localhost:3000",           # Dev alt
        "https://gca.code-auditor.com.br", # Produção
        "https://api.code-auditor.com.br", # Produção alt
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## ✅ Config Recomendado (Opção 1: Somente GCA)

```yaml
tunnel: b917d29f-da3c-49ba-8940-efe5e937201c
credentials-file: /home/luiz/.cloudflared/b917d29f-da3c-49ba-8940-efe5e937201c.json

ingress:
  # GCA Frontend
  - hostname: gca.code-auditor.com.br
    service: http://localhost:5173

  # GCA Backend API
  - hostname: api.code-auditor.com.br
    service: http://localhost:8000

  # App (se for outra coisa)
  - hostname: app.code-auditor.com.br
    service: http://localhost:3000

  # n8n (workflow automation)
  - hostname: n8n.code-auditor.com.br
    service: http://localhost:5678

  # Catch-all (404 para outros)
  - service: http_status:404
```

---

## ✅ Config Recomendado (Opção 2: GCA + GPD Legacy)

Se precisa manter GPD rodando em paralelo:

```yaml
tunnel: b917d29f-da3c-49ba-8940-efe5e937201c
credentials-file: /home/luiz/.cloudflared/b917d29f-da3c-49ba-8940-efe5e937201c.json

ingress:
  # GCA Frontend (porta padrão React/Vite)
  - hostname: gca.code-auditor.com.br
    service: http://localhost:5173

  # GCA API (FastAPI)
  - hostname: api.code-auditor.com.br
    service: http://localhost:8000

  # GPD Frontend (outra porta)
  - hostname: gpd.code-auditor.com.br
    service: http://localhost:3001

  # GPD API (outra porta)
  - hostname: gpd-api.code-auditor.com.br
    service: http://localhost:9000

  # App
  - hostname: app.code-auditor.com.br
    service: http://localhost:3000

  # n8n
  - hostname: n8n.code-auditor.com.br
    service: http://localhost:5678

  # Catch-all 404
  - service: http_status:404
```

**IMPORTANTE:** GPD deve estar rodando em portas **diferentes** de GCA!

---

## 🔍 Como Verificar Portas em Uso

```bash
# Ver todas as portas em uso
lsof -i -P -n | grep LISTEN

# Ou com netstat
netstat -tuln | grep LISTEN

# Esperado:
# 3000 — App (ou GPD frontend)
# 5173 ou 5174 — GCA Frontend (Vite)
# 5678 — n8n
# 8000 — GCA Backend (FastAPI)
# Opcionalmente: 9000 — GPD Backend
```

---

## 📋 Checklist de Configuração

### 1. Verificar Portas
- [ ] `lsof -i -P -n | grep LISTEN` para ver o que está rodando
- [ ] Confirmar que GCA backend está em porta 8000
- [ ] Confirmar que GCA frontend está em 5173 ou 5174

### 2. Atualizar config.yml
```bash
# Backup
cp ~/.cloudflared/config.yml ~/.cloudflared/config.yml.bak

# Editar com porta correta
nano ~/.cloudflared/config.yml
```

### 3. Atualizar Frontend .env
Se frontend está em `gca.code-auditor.com.br`, atualizar:

**frontend/.env:**
```env
VITE_API_URL=https://api.code-auditor.com.br/api/v1
VITE_APP_URL=https://gca.code-auditor.com.br
```

### 4. Testar Cloudflare
```bash
# Validar config
cloudflared tunnel ingress validate

# Rodar tunnel
cloudflared tunnel run

# Em outro terminal, testar:
curl -H "Host: gca.code-auditor.com.br" http://localhost:8000
curl -H "Host: api.code-auditor.com.br" http://localhost:8000
```

### 5. Verificar DNS no Cloudflare
- [ ] Dashboard Cloudflare → DNS
- [ ] `gca.code-auditor.com.br` → CNAME para tunnel
- [ ] `api.code-auditor.com.br` → CNAME para tunnel
- [ ] Status: "Proxied" (laranja) ou "DNS only" (cinza)?

---

## 🔐 CORS Configuration

Se frontend e API em domínios diferentes, **OBRIGATÓRIO** configurar CORS:

**app/core/config.py:**
```python
# Adicionar ao CORS_ORIGINS
CORS_ORIGINS: list = [
    "http://localhost:5173",            # Dev
    "https://gca.code-auditor.com.br",  # Produção
    "https://app.code-auditor.com.br",  # Alt
]
```

**Teste:**
```bash
curl -i -X OPTIONS https://api.code-auditor.com.br/api/v1/auth/me \
  -H "Origin: https://gca.code-auditor.com.br" \
  -H "Access-Control-Request-Method: GET"
```

Resposta esperada:
```
Access-Control-Allow-Origin: https://gca.code-auditor.com.br
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: authorization, content-type
```

---

## 🚀 Fluxo Completo com Cloudflare

```
┌─────────────────────────────────────────────────┐
│        Browser: gca.code-auditor.com.br        │
└──────────────────────┬──────────────────────────┘
                       │
                       ↓
┌──────────────────────────────────────────────────┐
│      Cloudflare Tunnel (Seu PC)                 │
│  (b917d29f-da3c-49ba-8940-efe5e937201c)        │
└──────────────────────┬───────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ↓              ↓              ↓
    5173 (React)   8000 (API)    5678 (n8n)
    Frontend       FastAPI       Workflow
```

---

## ❓ Dúvidas Comuns

### P: Preciso de "gca-api.code-auditor.com.br"?
**R:** Não necessariamente. Recomendo:
- Frontend: `gca.code-auditor.com.br`
- API: `api.code-auditor.com.br` (compartilhado)

### P: E se quiser API separada para GCA?
**R:** Use:
```yaml
- hostname: gca.code-auditor.com.br
  service: http://localhost:5173
- hostname: gca-api.code-auditor.com.br
  service: http://localhost:8000
```

E configure no frontend:
```env
VITE_API_URL=https://gca-api.code-auditor.com.br/api/v1
```

### P: Devo usar "gpd.code-auditor.com.br"?
**R:** Se foi o nome anterior do projeto, considere:
- ✅ Manter para backward compatibility (redirecionar para gca)
- ❌ Remover se não precisa mais (simplifica)

---

## 📝 Resumo de Correções

| Item | Status | Ação |
|------|--------|------|
| `gca.code-auditor.com.br` porta | ❌ 5174 | ✅ Trocar para 5173 |
| `api.code-auditor.com.br` | ✅ 8000 | ✅ Manter (GCA API) |
| `gpd.code-auditor.com.br` | ⚠️ Duplicado | ✅ Remover ou renomear |
| CORS config | ❌ Faltando | ✅ Adicionar em app/core/config.py |
| Frontend .env | ❌ Faltando | ✅ Criar com VITE_API_URL |

---

## 🔗 Próximas Ações

1. **Decidir**: Manter GPD ou remover?
   - Se remover: usar config Opção 1
   - Se manter: usar config Opção 2 com portas diferentes

2. **Atualizar config.yml**
   ```bash
   nano ~/.cloudflared/config.yml
   ```

3. **Validar**
   ```bash
   cloudflared tunnel ingress validate
   ```

4. **Testar**
   ```bash
   cloudflared tunnel run
   # Em outro terminal:
   curl https://gca.code-auditor.com.br
   curl https://api.code-auditor.com.br/api/v1/health
   ```

5. **Configurar DNS** no Cloudflare Dashboard

---

## 📚 Referências

- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Ingress Rules](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/local-management/ingress/)
- [CORS FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)

---

**Recomendação Final**: Use a **Opção 1** (somente GCA) e remova as referências a GPD. Se precisar de GPD, execute em portas diferentes e crie config separado.

🔐 **Não esqueça**: Validar e restartar tunnel após qualquer mudança!
