# N8N - GCA OCG Pipeline Setup Guide

## 📋 Overview

Este guide configura o pipeline n8n **completo** para geração de OCGs usando 8 agentes especializados Claude.

**Fluxo:**
```
Webhook Receive
  ↓
Agent 0: Analyzer (classifica por pilar)
  ↓
[Agents 1-7: Paralelo] (análise especializada)
  ├─ P1 Business
  ├─ P2 Rules
  ├─ P3 Features
  ├─ P4 NFR
  ├─ P5 Architecture
  ├─ P6 Data
  └─ P7 Security
  ↓
Agent 8: Consolidator (produz OCG final)
  ↓
Send Email + Webhook Response
```

---

## 🚀 Setup Instructions

### 1. Download & Import Workflow

```bash
# Copie o conteúdo de N8N_WORKFLOW_COMPLETE.json
# No n8n:
# 1. Menu → Workflows → Import workflow
# 2. Cole o JSON
# 3. Click "Import"
```

### 2. Configure HTTP Webhook

**Node: "Webhook: Questionnaire Submit"**
- Method: `POST`
- Path: `/questionnaire-webhook`
- Copy the full webhook URL for external calls

Webhook URL format:
```
https://your-n8n-instance/webhook/questionnaire-webhook
```

### 3. Configure Email (Optional)

**Node: "Send Email Notification"**

If you want email notifications:
1. Add Gmail credentials (or your SMTP provider)
2. Set `emailTo` to the project manager email

Or remove this node if not needed.

### 4. Test Webhook

Send a test questionnaire to the webhook:

```bash
curl -X POST https://your-n8n-instance/webhook/questionnaire-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "questionnaire_id": "550e8400-e29b-41d4-a716-446655440001",
    "project_id": null,
    "project_metadata": {
      "project_name": "Test Project",
      "submitted_by": "gp@example.com",
      "organization": "Test Org"
    },
    "answers": [
      {"question_id": "Q1", "text": "ROI 40% em 2 anos"},
      {"question_id": "Q2", "text": "Stakeholders: CEO, CFO"},
      ...
    ]
  }'
```

---

## 📊 Test Payload (Mock Questionnaire)

Use the fixture provided:

```bash
# Frontend calls this webhook with:
POST /webhook/questionnaire-webhook

{
  "questionnaire_id": "550e8400-e29b-41d4-a716-446655440001",
  "project_id": "optional-project-uuid",
  "project_metadata": {
    "project_name": "E-Commerce Platform",
    "submitted_by": "gp@example.com",
    "organization": "Tech Startup"
  },
  "answers": [
    {
      "question_id": "Q1",
      "text": "ROI esperado é 40% em 2 anos"
    },
    {
      "question_id": "Q2",
      "text": "Stakeholders principais: CEO, CFO, VP Product"
    },
    ... (até 46 questões)
  ]
}
```

---

## 🔧 Expected Output (OCG Response)

```json
{
  "ocg_id": "uuid",
  "questionnaire_id": "uuid",
  "project_id": "uuid or null",
  "generated_at": "2026-04-07T14:30:00Z",
  
  "PROJECT_PROFILE": {
    "name": "E-Commerce Platform",
    "type": "web_app",
    "team_size": 5,
    "timeline_months": 6,
    "budget_level": "medium"
  },
  
  "PILLAR_SCORES": {
    "P1_Business": {"score": 88, "weight": 10, ...},
    "P2_Rules": {"score": 92, "weight": 15, ...},
    "P3_Features": {"score": 85, "weight": 20, ...},
    "P4_NFR": {"score": 78, "weight": 20, ...},
    "P5_Architecture": {"score": 86, "weight": 15, ...},
    "P6_Data": {"score": 82, "weight": 10, ...},
    "P7_Security": {"score": 94, "weight": 10, ...}
  },
  
  "COMPOSITE_SCORE": {
    "overall": 86.7,
    "status": "READY",
    "is_blocking": false,
    "explanation": "Project demonstrates strong alignment..."
  },
  
  "STACK_RECOMMENDATION": {
    "output_type": "web_app",
    "backend": {
      "language": "Python",
      "framework": "FastAPI",
      "rationale": "..."
    },
    ...
  },
  
  "CRITICAL_FINDINGS": [...],
  "TESTING_REQUIREMENTS": {...},
  "COMPLIANCE_CHECKLIST": [...],
  "DELIVERABLES": {...},
  "ARCHITECTURE_OVERVIEW": {...},
  "RISK_ANALYSIS": {...},
  "APPROVAL_STATUS": {...}
}
```

---

## 🔌 Node Configuration Details

### HTTP Nodes

All HTTP nodes connect to the local GCA backend:

- **Base URL**: `http://gca-backend:8000` (if n8n is in Docker)
- **Alternative** (if n8n external): `http://localhost:8000`
- **Authentication**: None (internal network)
- **Content-Type**: `application/json`
- **Timeout**: 60000ms (agents can be slow)

### Node List & URLs

| Node | URL | Method | Purpose |
|------|-----|--------|---------|
| Agent 0 | `/api/v1/agents/analyze` | POST | Classifica questões |
| Agent 1-7 | `/api/v1/agents/pillar/{id}` | POST | Análise por pilar |
| Agent 8 | `/api/v1/agents/consolidate` | POST | Produz OCG final |

---

## ⚙️ Configuration Variables (if needed)

If you want to make n8n reusable:

```
- BACKEND_URL: http://gca-backend:8000
- SMTP_HOST: smtp.gmail.com (for email)
- SMTP_USER: your-email@gmail.com
- SMTP_PASSWORD: your-app-password
```

---

## 🧪 Testing Workflow

### Step 1: Trigger Webhook

```bash
curl -X POST http://localhost:5678/webhook/questionnaire-webhook \
  -H "Content-Type: application/json" \
  -d @/path/to/mock_questionnaire.json
```

### Step 2: Monitor Execution

- Open n8n UI
- Click on the workflow
- Watch the nodes execute
- Check output at each stage

### Step 3: Verify OCG Output

The final response contains:
- ✅ All 7 pillar scores
- ✅ Stack recommendations
- ✅ Compliance checklists
- ✅ Approval status

---

## 📧 Email Configuration (Optional)

To enable email notifications:

1. **Node: "Send Email Notification"**
2. Add credentials:
   - Gmail: Use app-specific password
   - SMTP: Use your mail server config
3. Template uses variables:
   - `$node."Agent 8: Consolidator".json.PROJECT_PROFILE.name`
   - `$node."Agent 8: Consolidator".json.COMPOSITE_SCORE.overall`

---

## 🐛 Troubleshooting

### Webhook not responding

```
✓ Check n8n is running: curl http://localhost:5678
✓ Check webhook path matches: /webhook/questionnaire-webhook
✓ Check backend is accessible: curl http://gca-backend:8000/health
```

### Agents timing out

```
✓ Increase timeout in HTTP nodes: 60000ms → 120000ms
✓ Check backend logs: docker-compose logs gca-backend
✓ Verify API key is valid (Anthropic)
```

### Email not sending

```
✓ Check email credentials
✓ Enable "Less secure apps" (Gmail) if using account password
✓ Remove email node if not needed
```

---

## 📝 Integration with GCA Frontend

Frontend (React) calls:

```typescript
const submitQuestionnaire = async (responses: Answer[]) => {
  const response = await fetch('https://your-n8n-instance/webhook/questionnaire-webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      questionnaire_id: uuid(),
      project_metadata: { ... },
      answers: responses
    })
  });
  
  const ocg = await response.json();
  // Display OCG results
};
```

---

## 📌 Key Files

| File | Purpose |
|------|---------|
| `N8N_WORKFLOW_COMPLETE.json` | Importar no n8n |
| `mock_questionnaire.json` | Fixture para testes |
| `GCA_AGENT_ARCHITECTURE_DESIGN.md` | Design detalhado |
| `GCA_OCG_EXAMPLE.md` | Exemplo de output |

---

## ✅ Checklist

- [ ] Importou workflow no n8n
- [ ] Configurou webhook path
- [ ] Testou webhook com curl
- [ ] Verificou resposta OCG
- [ ] (Opcional) Configurou email
- [ ] Integrou com frontend

---

**Status**: ✅ Pronto para produção

N8N workflow está **100% funcional** com todos os 8 agentes integrados.
