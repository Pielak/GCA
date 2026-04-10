# n8n Pipeline — STATUS ATUAL

**Status**: 🟡 **PARCIALMENTE IMPLEMENTADO (Pronto para ser ativado)**  
**Date**: 2026-04-06  
**Qwen AI Credential**: `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`

---

## 📊 ESTADO ATUAL DO PIPELINE

### ✅ Parte 1: Backend — Análise Inteligente (COMPLETA)

**Endpoint**: `POST /api/v1/webhooks/questionnaire`

```python
Request:
{
  "projectId": "proj-123",
  "gp_email": "gp@example.com",
  "responses": {
    "frontend_stack": ["React"],
    "backend_stack": ["FastAPI"],
    "database_stack": ["PostgreSQL"],
    "ai_automation": ["Anthropic"],
    "security_controls": ["Autenticação", "Autorização / RBAC"],
    ... (mais campos)
  }
}

Response:
{
  "projectId": "proj-123",
  "questionnaireStatus": "OK|Incompleto|Pendente",
  "adherenceScore": 85-100,
  "approved": true|false,
  "validations": {
    "logicConflicts": [...],  // 15+ regras implementadas
    "gaps": [...],             // 8+ regras implementadas
    "incompatibilities": [...]
  },
  "observations": "✅ Seu stack está bem alinhado...",
  "restrictions": "IA externa: Certifique-se de LGPD...",
  "highlightedFields": ["frontend_stack", ...]
}
```

### ✅ Regras de Análise Implementadas (15+ Conflitos)

```
1. ✅ React + Flutter = incompatível
2. ✅ Monólito + Microserviços = incompatível
3. ✅ Offline (sem sincronização) = warning
4. ✅ Electron + Python = incompatível
5. ✅ ... + mais 11 regras
```

### ✅ Gap Detection Implementado (8+ Gaps)

```
1. ✅ Web app sem frontend
2. ✅ API sem backend
3. ✅ App persistente sem banco de dados
4. ✅ Microserviço sem messaging
5. ✅ Sem IA (obrigatória em GCA)
6. ✅ Kafka sem testes de resiliência
7. ✅ Sem autenticação
8. ✅ Sem RBAC
9. ✅ ... + mais validações
```

### ✅ Score Calculation (COMPLETO)

```
Formula: 100 - (conflitos × 5) - (gaps × 10) - (incompatibilities × 5)

Exemplos:
• Score 100: ✅ Aprovado (tudo ok)
• Score 85-99: ✅ Aprovado (poucos problemas)
• Score 75-84: 🟡 Incompleto (precisa revisão)
• Score < 75: ❌ Rejeitado (muitos problemas)

Threshold: ≥85% para aprovação automática
```

### ✅ Email Templates (PRONTO)

```
1. ✅ Questionnaire Approved (score ≥85%)
   → Envia para GP
   → Próximos passos: Convite de equipe, credenciais

2. ✅ Questionnaire Revision Needed (score < 85%)
   → Envia para GP
   → Lista conflitos detectados
   → Link para re-submissão

3. ✅ Password Reset
4. ✅ Team Invitation
5. ✅ First Access
```

---

## 🟡 Parte 2: n8n Integration (DESIGN PRONTO, Aguardando Ativação)

### Fluxo Desejado com n8n

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend: Questionnaire Form                                 │
│ User fills form → Click "Enviar"                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend: Submit Questionnaire (POST /questionnaires)         │
│ 1. Save to DB                                                │
│ 2. Generate questionnaire_id                                 │
│ 3. Trigger n8n webhook (async)                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ n8n Workflow: Questionnaire Analysis Pipeline                │
│ 1. Receive payload from GCA webhook trigger                  │
│ 2. Parse questionnaire responses                              │
│ 3. Run Qwen AI analysis (optional enhanced validation)       │
│ 4. Generate insights & recommendations                       │
│ 5. Call GCA webhook: /webhooks/questionnaire                 │
│    (with analysis results)                                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend: Receive Analysis Results                            │
│ 1. Update Questionnaire.status with n8n results             │
│ 2. Store adherence_score + gaps + restrictions              │
│ 3. Determine if approved (≥85%) or needs revision           │
│ 4. Trigger appropriate email notification                    │
│ 5. Log audit trail                                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Email Service                                                 │
│ If approved (score ≥85%):                                    │
│   → Send approval email + next steps                         │
│ If revision needed (score < 85%):                            │
│   → Send revision email + conflicts found                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 O QUE ESTÁ PRONTO

### Backend
- [x] Webhook endpoint `/api/v1/webhooks/questionnaire` (FUNCIONANDO)
- [x] Análise inteligente (15+ regras, 8+ gaps)
- [x] Score calculation com threshold 85%
- [x] Email templates (4 tipos)
- [x] Database models (ResetToken + User columns)
- [x] Error handling e logging

### Frontend
- [x] Questionnaire form component (já existe)
- [x] Status display (integrado com routes)
- [x] API calls via axios

### n8n
- [x] Credential: Qwen AI (fornecida)
- [ ] Workflow: Não criada ainda (requer manual setup)
- [ ] Webhook trigger: Precisa ser configurada

---

## ⚠️ O QUE PRECISA SER FEITO

### 1. Criar Workflow no n8n (Responsabilidade: Você)

**Passo 1: Criar Webhook Trigger**
```
Node: Webhook
- Method: POST
- URL: https://your-n8n.com/webhook/gca-questionnaire
- Authentication: None (or API key if preferred)
```

**Passo 2: Parse Payload**
```
Node: Set (Extract fields from payload)
- Extract: projectId, gp_email, responses
```

**Passo 3: Qwen AI Analysis (Optional)**
```
Node: Qwen Model
- Model: Use provided credential
- Prompt: Analyze this stack: {{ responses }}
- Output: Enhanced insights (optional)
```

**Passo 4: Call GCA Backend**
```
Node: HTTP Request
- Method: POST
- URL: https://your-gca-api.com/webhooks/questionnaire
- Body: {
    projectId,
    gp_email,
    responses,
    n8n_analysis (if from Qwen)
  }
```

**Passo 5: Log/Store Results**
```
Node: Set
- Save n8n execution ID
- Log timestamp
- Archive payload
```

### 2. Configurar n8n Webhook URL no Backend

```bash
# Em GCA/backend/.env:
N8N_WEBHOOK_URL=https://your-n8n.com/webhook/gca-questionnaire
N8N_API_URL=https://your-n8n.com/api
N8N_API_KEY=your-n8n-api-key (optional)
```

### 3. Implementar Chamada ao n8n (No Backend)

**Arquivo**: `GCA/backend/app/services/questionnaire_service.py`

```python
# TODO item 3 (linhas 63-68) precisa ser preenchido:

async def trigger_n8n_webhook(questionnaire_id, project_id, gp_email, responses):
    """Trigger n8n workflow asynchronously"""
    import aiohttp
    
    payload = {
        "projectId": str(project_id),
        "gp_email": gp_email,
        "responses": responses,
        "questionnaire_id": questionnaire_id
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                settings.N8N_WEBHOOK_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                logger.info("n8n.webhook_triggered", status=response.status)
                return True
        except Exception as e:
            logger.error("n8n.webhook_failed", error=str(e))
            return False
```

### 4. Armazenar Resultado do n8n no DB

**Implementar**: Questionnaire model para persistir resultados

```python
class Questionnaire(Base):
    __tablename__ = "questionnaires"
    
    id: UUID = Column(UUID, primary_key=True)
    project_id: UUID = Column(UUID, ForeignKey("projects.id"))
    gp_email: str = Column(String)
    responses: dict = Column(JSON)
    
    # n8n Analysis Results
    adherence_score: int = Column(Integer, nullable=True)
    status: str = Column(String)  # Pendente, Incompleto, OK
    validations: dict = Column(JSON, nullable=True)  # Conflicts + gaps
    observations: str = Column(Text, nullable=True)
    restrictions: str = Column(Text, nullable=True)
    highlighted_fields: list = Column(JSON, nullable=True)
    
    # Metadata
    submitted_at: datetime = Column(DateTime)
    analyzed_at: datetime = Column(DateTime, nullable=True)
    approved: bool = Column(Boolean, default=False)
```

---

## 🚀 OPÇÕES DE IMPLEMENTAÇÃO

### Opção A: Usar Análise Built-in (RECOMENDADO para MVP)
✅ **Vantagem**: Funciona imediatamente, sem depender de n8n  
✅ **Uso**: Backend já tem análise inteligente implementada  
⚠️ **Limitação**: Sem análise com Qwen AI  

**Como Ativar**:
```python
# No questionnaire_service.py, chamar diretamente:
from app.routers.webhooks import analyze_questionnaire

result = analyze_questionnaire(responses)
# Salvar direto no DB, enviar email
```

### Opção B: Integrar com n8n (RECOMENDADO para Produção)
✅ **Vantagem**: n8n como orquestrador, Qwen AI para insights avançados  
✅ **Uso**: Escalável, reutilizável  
⚠️ **Limitação**: Requer setup manual no n8n  

**Como Ativar**:
1. Criar workflow no n8n
2. Implementar `trigger_n8n_webhook()` no backend
3. Configurar Questionnaire model no DB
4. Testar fluxo end-to-end

### Opção C: Híbrida (MELHOR CENÁRIO)
✅ **Vantagem**: Ambas análises rodando  
✅ **Uso**: Backend faz análise rápida + n8n faz análise profunda  

```python
# 1. Backend calcula score imediatamente
result = analyze_questionnaire(responses)

# 2. Salva no DB com status "Pendente"
save_to_db(result)

# 3. Dispara n8n async para análise aprofundada com Qwen
trigger_n8n_webhook(questionnaire_id, responses)

# 4. n8n retorna análise enriquecida → Backend atualiza DB
```

---

## 🔧 PRÓXIMOS PASSOS RECOMENDADOS

### Imediato (Esta semana)
1. **Ativar Opção A** (análise built-in)
   - Implementar `trigger_email_notification()` no questionnaire_service
   - Criar Questionnaire model mínima
   - Testar fluxo completo

2. **Testar localmente**
   ```bash
   # Terminal 1
   python -m uvicorn app.main:app --reload
   
   # Terminal 2
   curl -X POST http://localhost:8000/api/v1/webhooks/questionnaire \
     -H "Content-Type: application/json" \
     -d '{
       "projectId": "proj-123",
       "gp_email": "gp@example.com",
       "responses": {
         "frontend_stack": ["React"],
         "backend_stack": ["FastAPI"],
         "ai_automation": ["Anthropic"]
       }
     }'
   ```

### Curto prazo (Próximas 2 semanas)
3. **Criar workflow n8n** (se desejar usar Qwen)
   - Setup webhook trigger
   - Integrar Qwen AI
   - Conectar de volta ao GCA

4. **Implementar Questionnaire model**
   - Persistir respostas
   - Armazenar resultados da análise
   - Histórico de submissões

### Médio prazo (1 mês)
5. **Dashboard de análise**
   - Visualizar scores por projeto
   - Trends de adherência
   - Insights de stack mais usado

---

## 🧪 TESTE RÁPIDO (5 MINUTOS)

```bash
# 1. Start backend
cd GCA/backend && python -m uvicorn app.main:app --reload

# 2. Call webhook endpoint
curl -X POST http://localhost:8000/api/v1/webhooks/questionnaire \
  -H "Content-Type: application/json" \
  -d '{
    "projectId": "proj-test",
    "gp_email": "pielak.ctba@gmail.com",
    "responses": {
      "frontend_stack": ["React", "Flutter"],
      "backend_stack": ["FastAPI"],
      "database_stack": ["PostgreSQL"],
      "ai_automation": ["Anthropic"],
      "security_controls": ["Autenticação"],
      "deliverables": ["Aplicação web"],
      "execution_mode": ["Cloud"],
      "architecture_target": ["Microserviços"],
      "infra_support": ["Kafka"],
      "test_types": ["Unitários"]
    }
  }'

# 3. Expected response:
# {
#   "projectId": "proj-test",
#   "questionnaireStatus": "Incompleto",
#   "adherenceScore": 70,
#   "approved": false,
#   "validations": {
#     "logicConflicts": [
#       {
#         "field": "frontend_stack",
#         "conflict": "React + Flutter são incompatíveis",
#         "severity": "blocker",
#         "suggestion": "Escolha UM framework"
#       }
#     ],
#     "gaps": [
#       {
#         "field": "security_controls",
#         "gap": "RBAC (Role-Based Access Control) é obrigatório",
#         "severity": "blocker",
#         "suggestion": "Selecione: Autorização / RBAC"
#       }
#     ]
#   },
#   "observations": "⚠️ Detectados 1 conflito(s) e 1 gap(s)",
#   "restrictions": "IA externa: Certifique-se de manter dados...",
#   "highlightedFields": ["frontend_stack", "security_controls"]
# }
```

---

## 📊 RESUMO DO STATUS

| Componente | Status | Pronto? |
|-----------|--------|---------|
| Webhook Endpoint | ✅ Implementado | Sim |
| Análise Inteligente | ✅ Implementado | Sim |
| Score Calculation | ✅ Implementado | Sim |
| Email Templates | ✅ Implementado | Sim |
| Database Models | 🟡 Parcial | Falta Questionnaire |
| n8n Integration | 🟡 Desenhado | Aguarda implementação |
| Qwen AI | ✅ Credential pronta | Sim |
| Email Envio | ✅ SMTP pronto | Sim |

---

## 🎯 RECOMENDAÇÃO FINAL

**Para MVP imediato**: Use **Opção A** (análise built-in no backend)
- ✅ Funciona sem dependências externas
- ✅ Análise inteligente já implementada
- ✅ Emails funcionando com Gmail
- ⏱️ Tempo para ativar: 30 minutos

**Para Produção**: Use **Opção C** (Híbrida)
- ✅ Backend faz análise rápida
- ✅ n8n faz análise aprofundada com Qwen
- ✅ Escalável e reutilizável
- ⏱️ Tempo para ativar: 1-2 dias (incluindo setup n8n)

---

**Pipeline Status**: 🟡 **Pronto para ser ativado (análise completa, n8n design pronto)**  
**Recomendação**: Ativar Opção A hoje, migrar para Opção C quando tiver n8n configurado  
**Próximo**: Implementar `trigger_email_notification()` no questionnaire_service
