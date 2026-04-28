# Smoke Test & Regressão — GCA Post-Compartimentalização

**Data:** 2026-04-28  
**Escopo:** Validar que compartimentalização por project_id não quebrou funcionalidades existentes  
**Resultado Esperado:** ✅ PASS — Todas as features funcionam, sem vazamento de dados

---

## Parte 1: Testes Automatizados

### 1.1 Teste Unitário de Compartimentalização

```bash
# Backend — rodar testes adversariais
cd /home/luiz/GCA/backend
pytest app/tests/test_compartimentalization_adversarial.py -v

# Esperado: 12 testes PASS
# - 5 testes de acesso negado (User A → Project B)
# - 2 testes de vazamento de dados
# - 1 teste de query com project_id filter
# Total: 8+ PASS
```

**Validação:**
- [ ] Nenhum teste falha
- [ ] Nenhum dado de Project B vaza em Project A
- [ ] Respostas HTTP são 401/403/404, não 200 com dados

### 1.2 Teste de Regressão Completo

```bash
# Backend — rodar suite completa
cd /home/luiz/GCA/backend
pytest app/tests/ -v --tb=short

# Esperado: X testes PASS, 0 FAIL
# (referência anterior: 1535 passed)
```

**Validação:**
- [ ] Número de PASS ≥ 1500 (baseline anterior)
- [ ] Número de FAIL = 0
- [ ] Número de SKIP ≤ 30 (esperado)
- [ ] Sem erros de import ou sintaxe

### 1.3 Teste de Testes Técnicos Questionários (Nova Feature)

```bash
pytest app/tests/test_technical_questionnaire.py -v

# Esperado: 10+ testes PASS (serviço + router)
```

**Validação:**
- [ ] Hook de visibilidade dinâmica funciona
- [ ] Validação cruzada detecta conflitos
- [ ] Auto-save com debounce implementado
- [ ] Endpoints GET/PATCH/POST respondendo

---

## Parte 2: Smoke Test Manual — Fluxo Completo

### 2.1 Setup

```bash
# Terminal 1: Backend
cd /home/luiz/GCA/backend
docker compose up -d
sleep 5
python -m pytest --co -q  # verificar cobertura de testes

# Terminal 2: Frontend  
cd /home/luiz/GCA/frontend
npm install
npm run dev  # http://localhost:5173

# Terminal 3: Browser (devtools abertos)
# http://localhost:5173
```

### 2.2 Fluxo de Novo Projeto Limpo

**Cenário:** User cria projeto novo e executa fluxo básico

#### Passo 1: Login
- [ ] Acessar `/login`
- [ ] Login com credenciais válidas
- [ ] Redirecionado para `/projects` (dashboard)
- [ ] Sem erros no console (devtools)
- [ ] Sem erros 401/403

#### Passo 2: Criar Novo Projeto
- [ ] Click "Novo Projeto"
- [ ] Form carrega corretamente
- [ ] Input nome do projeto: "Smoke Test Project"
- [ ] Click "Criar"
- [ ] Redirecionado para `/projects/{projectId}`
- [ ] Projeto aparece na sidebar com status "draft" ou "provisioning"

#### Passo 3: Setup Wizard (Initial Questionnaire)
- [ ] Sidebar → "Questionário"
- [ ] Form com 20 perguntas carrega
- [ ] Responder Q1-Q5 (contexto básico)
- [ ] Digitar → auto-save após 2s
- [ ] Barra de progresso sobe (deve chegar ~20-30%)
- [ ] Click "Submeter Questionário"
- [ ] Status muda para "submitted"
- [ ] Sem erros HTTP 5xx

#### Passo 4: Questionários Técnicos (Nova Feature)
- [ ] Sidebar → "Questionários Técnicos"
- [ ] Página carrega com seções A, B, C, D
- [ ] Responder Q1 "Novo sistema"
- [ ] Q2 aparece dinamicamente
- [ ] Responder Q3 "Sim, modesto"
- [ ] Q7, Q8 aparecem
- [ ] Responder Q3 "Não"
- [ ] Q7-Q10 desaparecem
- [ ] Barra de progresso atualiza
- [ ] Click "Validar Escopo" (se progress >= 80%)
- [ ] Validação retorna status OK/erro
- [ ] Submeter questionário

#### Passo 5: Ingestão de Documentos
- [ ] Sidebar → "Ingestão"
- [ ] Upload mock document (ou skip se não houver S3)
- [ ] Documento lista
- [ ] Status "processando" ou "completo"

#### Passo 6: OCG (Consolidated Orchestration Graph)
- [ ] Sidebar → "OCG"
- [ ] OCG carrega (pode estar vazio em novo projeto)
- [ ] Sem erros 5xx
- [ ] Metadata visível (project_id, status, etc)

#### Passo 7: Gatekeeper
- [ ] Sidebar → "Gatekeeper"
- [ ] Personas gatekeeping visível (se questionnaire foi submetido)
- [ ] Sem dados de outro projeto

#### Passo 8: Logout + Verificação de Isolamento
- [ ] Logout user A
- [ ] Login user B (criar se necessário)
- [ ] User B não vê projeto de User A
- [ ] Tentar acessar `/projects/{projectA_id}` diretamente
  - [ ] Redirecionado para `/projects`
  - [ ] Ou retorna 403 Forbidden
  - [ ] Nunca retorna dados de Project A

---

## Parte 3: Verificação de Regressão — Features Existentes

### 3.1 Endpoints Críticos P0

```bash
# Todos esses devem retornar 200 (ou 404 legítimo, não 500)

# Projects
GET /api/projects                    # 200
POST /api/projects                   # 201
GET /api/projects/{id}               # 200
PATCH /api/projects/{id}             # 200

# Questionnaire (Initial)
GET /api/projects/{id}/initial-questionnaire       # 200
PATCH /api/projects/{id}/initial-questionnaire     # 200

# Questionário Técnico (Nova)
GET /api/projects/{id}/technical-questionnaire     # 200
PATCH /api/projects/{id}/technical-questionnaire   # 200
POST /api/projects/{id}/technical-questionnaire/validate  # 200

# OCG
GET /api/projects/{id}/ocg           # 200
POST /api/projects/{id}/ocg/validate # 200

# Ingestion
GET /api/projects/{id}/ingestion/documents         # 200
POST /api/projects/{id}/ingestion/upload           # 201 ou skip se sem S3

# Arguider
GET /api/projects/{id}/arguider/analyses           # 200

# Backlog
GET /api/projects/{id}/backlog       # 200

# Testes
GET /api/projects/{id}/qa            # 200
```

**Validação:** Rodar com curl ou Postman

```bash
#!/bin/bash
TOKEN="..."
PROJECT_ID="..."

for endpoint in \
  "/api/projects" \
  "/api/projects/$PROJECT_ID" \
  "/api/projects/$PROJECT_ID/initial-questionnaire" \
  "/api/projects/$PROJECT_ID/technical-questionnaire" \
  "/api/projects/$PROJECT_ID/ocg" \
  "/api/projects/$PROJECT_ID/ingestion/documents" \
; do
  echo "Testing: $endpoint"
  curl -s -H "Authorization: Bearer $TOKEN" \
    http://localhost:8000$endpoint | jq '.errors // .status' || echo "ERROR"
done
```

### 3.2 Dados Esperados vs Realidade

| Feature | Esperado | Verificação |
|---------|----------|-------------|
| Questionário Inicial | 20 campos | PATCH return status change ✓ |
| Questionário Técnico | 15 perguntas dinâmicas | GET return visible_questions[] ✓ |
| OCG | Pilar/decision consolidado | GET return consolidated_ocg ✓ |
| Arguider | Análises por persona | GET return analyses[] com project_id ✓ |
| Ingestion | Documentos com URLs | GET return documents[] com project_id ✓ |

---

## Parte 4: Verificação de Compartimentalização

### 4.1 Teste Manual: Dois Usuários, Dois Projetos

```bash
# User A
TOKEN_A="<jwt_user_a>"
PROJECT_A="<id_project_a>"

# User B
TOKEN_B="<jwt_user_b>"
PROJECT_B="<id_project_b>"

# ✓ Esperado: User A vê Project A
curl -H "Authorization: Bearer $TOKEN_A" \
  http://localhost:8000/api/projects/$PROJECT_A
# Response: 200 + project data

# ✗ Esperado: User A NÃO vê Project B
curl -H "Authorization: Bearer $TOKEN_A" \
  http://localhost:8000/api/projects/$PROJECT_B
# Response: 403 ou 404, NUNCA 200 + project data

# ✓ Esperado: User B vê Project B
curl -H "Authorization: Bearer $TOKEN_B" \
  http://localhost:8000/api/projects/$PROJECT_B
# Response: 200 + project data
```

### 4.2 Teste de Vazamento de Dados

```bash
# Criar OCG em Project A com conteúdo único
curl -X POST -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"content": "SECRET_DATA_PROJECT_A"}' \
  http://localhost:8000/api/projects/$PROJECT_A/ocg

# Verificar que User B NÃO pode ver "SECRET_DATA_PROJECT_A"
curl -H "Authorization: Bearer $TOKEN_B" \
  http://localhost:8000/api/projects/$PROJECT_B/ocg \
  | grep -q "SECRET_DATA_PROJECT_A"

# ✓ Esperado: grep não encontra (exit 1)
# ✗ Problema: grep encontra (exit 0) — VAZAMENTO!
```

---

## Parte 5: Checklist de Deploy

- [ ] **Migrations:** `055_technical_questionnaire.sql` executada (novos testes só funcionam com a tabela)
- [ ] **Tests Pass:** `pytest app/tests/ -q` → 0 FAIL
- [ ] **Adversarial Tests Pass:** `pytest app/tests/test_compartimentalization_adversarial.py -q` → 0 FAIL
- [ ] **Frontend Build:** `npm run build` → sem erros
- [ ] **Dev Server:** `npm run dev` → localhost:5173 acessível
- [ ] **Smoke Test Manual:** Fluxo completo em Passo 2.2 executado sem erros
- [ ] **Compartimentalização:** Teste em Passo 4 validado (sem vazamento)
- [ ] **Regressão:** Todas features existentes funcionam (Passo 3.2)
- [ ] **Logs:** Sem erros 500 no backend, sem erros no console do frontend
- [ ] **Performance:** Endpoints respondem < 1s (sem timeouts)

---

## Resultado Final

### ✅ PASS Criteria
- 0 erros HTTP 5xx
- 0 vazamentos de dados cross-project
- 1500+ testes automatizados passando
- Fluxo manual completo 2.2 executado com sucesso
- Questionário Técnico (nova feature) funcionando

### ❌ FAIL Criteria
- Qualquer endpoint retorna 500
- User A consegue acessar dados de Project B
- Teste automatizado falha
- Fluxo manual trava ou retorna erro
- Feature nova não funciona

---

**Versão:** 1.0  
**Data:** 2026-04-28  
**Responsável:** QA/Dev  
**Status:** PRONTO PARA EXECUTAR ✅
