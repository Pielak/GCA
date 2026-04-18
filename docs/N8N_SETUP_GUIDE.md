# Phase 4: n8n + Qwen AI Integration Setup Guide

> ⚠️ **DOCUMENTO HISTÓRICO — fase descontinuada.**
> Este guia descreve a integração n8n + Qwen de uma fase que **foi
> substituída** pelos agentes nativos (pipeline de 8 agentes de OCG em
> `backend/app/services/agent_service.py`). O container n8n ainda roda
> por compatibilidade, mas o fluxo oficial de validação de questionário
> não passa mais por ele — usa `TechnologyVerificationService` diretamente.
>
> Para arquitetura atual de IA, ver [`../GCA_CANONICAL_CONTRACT.md §6`](../GCA_CANONICAL_CONTRACT.md).

## Overview

This guide covers setting up n8n with Qwen AI for intelligent validation of external project questionnaires. **Qwen is a free, open-source LLM by Alibaba** that can be used locally or via API.

**Workflow:**
```
GP submits questionnaire
  ↓
Backend triggers n8n webhook with questionnaire data
  ↓
n8n receives data → Analyzes with Qwen AI
  ↓
n8n identifies gaps, conflicts, and recommendations
  ↓
n8n calls back: POST /api/v1/webhooks/external-project-result
  ↓
Backend updates ExternalProjectRequest with validation results
  ↓
Admin sees analysis + can approve/reject with context
```

---

## Quick Start (5 Minutes!)

### 1. Start All Services

```bash
cd /home/luiz/GCA_Project
docker-compose up -d

# Wait for n8n to initialize (~30 seconds)
docker logs gca-n8n | tail -20
# Look for: "Running n8n..."
```

### 2. Access n8n Dashboard

Open **http://localhost:5678**

**First time:**
- Create admin account (username/password)
- Skip email validation if prompted

### 3. Add OpenRouter Credentials

1. Click **Settings** (gear icon, bottom left)
2. Click **Credentials**
3. Click **Create New** → Search **"OpenRouter"**
4. **Fill in:**
   - Name: `OpenRouter API`
   - API Key: `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`
5. Click **Save**

### 4. Import Workflow (2 Minutes)

**Easiest way:**

1. In n8n, click **"+"** → **Import Workflow**
2. Click **Select a file**
3. Choose: `n8n-workflow-qwen.json` (in project root)
4. Click **Import**
5. ✅ **Done!** Workflow is ready

**Or manually paste JSON:**
- See section "Pre-built Workflow JSON" below

### 5. Activate Workflow

1. In n8n, open the imported workflow
2. Click **Activate** toggle (top right)
3. ✅ **Workflow is now LIVE**

**That's it!** Your n8n + Qwen AI integration is ready!

---

## Pre-built Workflow JSON

A pre-built workflow JSON file is included: `n8n-workflow-qwen.json`

**To import:**
1. In n8n dashboard, click **"+"** → **Import Workflow**
2. Select `n8n-workflow-qwen.json` from your project root
3. Click **Import**
4. Workflow is ready!

The workflow automatically uses:
- OpenRouter API key from n8n credentials
- Qwen 2.5 7B Instruct model
- Callback endpoint: `http://localhost:8000/api/v1/webhooks/external-project-result`

**Or manually paste this JSON:**

```json
{
  "name": "GCA External Project Validation (Qwen AI)",
  "description": "Receives external project questionnaire, analyzes with Qwen AI, returns gaps and recommendations",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "external-project",
        "responseMode": "onReceived",
        "options": {}
      },
      "id": "webhook_trigger",
      "name": "Webhook Trigger",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [0, 300]
    },
    {
      "parameters": {
        "mode": "jsonTojsonata",
        "expression": "{\n  \"request_id\": $request_id,\n  \"request_number\": $request_number,\n  \"gp_email\": $gp_email,\n  \"questionnaire\": $questionnaire_data,\n  \"analysis_prompt\": $join([\n    \"Analyze this technical project questionnaire and identify:\",\n    \"1. GAPS: Missing or incomplete required information\",\n    \"2. CONFLICTS: Contradictory choices (e.g., monolith + microservices)\",\n    \"3. RISKS: Technical or architectural concerns\",\n    \"4. RECOMMENDATIONS: Suggestions for improvement\",\n    \"\",\n    \"Format response as JSON with keys: gaps, conflicts, recommendations, risk_level\",\n    \"\",\n    \"Questionnaire:\",\n    JSON.stringify($questionnaire_data, null, 2)\n  ], \"\\n\")\n}"
      },
      "id": "prepare_prompt",
      "name": "Prepare Qwen Prompt",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [200, 300]
    },
    {
      "parameters": {
        "provider": "openrouter",
        "model": "qwen/qwen-2.5-7b",
        "prompt": "={{ $node['prepare_prompt'].json.analysis_prompt }}",
        "options": {
          "temperature": 0.5,
          "topP": 0.9
        }
      },
      "id": "qwen_analysis",
      "name": "Qwen AI Analysis",
      "type": "n8n-nodes-base.openai",
      "typeVersion": 1,
      "position": [400, 300],
      "credentials": {
        "openRouterApi": "openrouter_api_key"
      }
    },
    {
      "parameters": {
        "url": "http://localhost:8000/api/v1/webhooks/external-project-result",
        "method": "POST",
        "sendBody": true,
        "bodyContentType": "application/json",
        "body": "{\n  \"request_id\": \"{{ $node['webhook_trigger'].json.request_id }}\",\n  \"request_number\": \"{{ $node['webhook_trigger'].json.request_number }}\",\n  \"gp_email\": \"{{ $node['webhook_trigger'].json.gp_email }}\",\n  \"analysis\": {{ JSON.parse($node['qwen_analysis'].json.text) }}\n}"
      },
      "id": "callback_backend",
      "name": "Callback Backend",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4,
      "position": [600, 300]
    }
  ],
  "connections": {
    "webhook_trigger": {
      "main": [
        [
          {
            "node": "prepare_prompt",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "prepare_prompt": {
      "main": [
        [
          {
            "node": "qwen_analysis",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "qwen_analysis": {
      "main": [
        [
          {
            "node": "callback_backend",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  }
}
```

---

## Manual Workflow Creation

### Step 1: Create Webhook Trigger

1. In n8n, click **"+"** → **Add Node** → **Webhook**
2. Configure:
   - **Method:** POST
   - **Path:** `external-project`
   - **Response Mode:** "On Received"
3. Copy the **Webhook URL** (you'll need it)

### Step 2: Prepare Qwen Prompt

1. Add **Function** node
2. Enter this code to prepare the analysis prompt:

```javascript
return {
  request_id: $input.first().json.request_id,
  request_number: $input.first().json.request_number,
  gp_email: $input.first().json.gp_email,
  questionnaire: $input.first().json.questionnaire_data,
  analysis_prompt: `
Analyze this technical project questionnaire and identify:

1. GAPS: Missing or incomplete required information
2. CONFLICTS: Contradictory technology choices
3. RISKS: Technical or architectural concerns
4. RECOMMENDATIONS: Specific suggestions

Questionnaire:
${JSON.stringify($input.first().json.questionnaire_data, null, 2)}

Return as JSON with keys: gaps, conflicts, recommendations, risk_level
  `.trim()
};
```

### Step 3: Add Qwen AI LLM Node

1. Add **OpenAI** node (or use **HTTP Request** to call Qwen API directly)

**Option A: Via OpenRouter (easiest)**
- Provider: OpenRouter
- Model: `qwen/qwen-2.5-7b` (free tier available)
- Prompt: `{{ $node['prepare_prompt'].json.analysis_prompt }}`
- Temperature: 0.5
- Get API key at: https://openrouter.ai

**Option B: Local Qwen (via Ollama)**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull Qwen model
ollama pull qwen:7b

# Run Ollama server
ollama serve

# In n8n: Use HTTP Request node pointing to http://localhost:11434/api/generate
```

**Option C: Hugging Face API**
- Use HTTP Request node
- Endpoint: `https://api-inference.huggingface.co/models/Qwen/Qwen2.5-7B`
- Add Authorization header with HF token

### Step 4: Callback to Backend

1. Add **HTTP Request** node
2. Configure:
   - **Method:** POST
   - **URL:** `http://localhost:8000/api/v1/webhooks/external-project-result`
   - **Body:**
   ```json
   {
     "request_id": "{{ $node['webhook_trigger'].json.request_id }}",
     "request_number": "{{ $node['webhook_trigger'].json.request_number }}",
     "gp_email": "{{ $node['webhook_trigger'].json.gp_email }}",
     "analysis": "{{ JSON.parse($node['qwen_analysis'].json.text) }}"
   }
   ```
3. **Save & Activate** the workflow

### Step 5: Test the Webhook

```bash
curl -X POST http://localhost:5678/webhook/external-project \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-id-123",
    "request_number": "REQ-20260406-ABC123",
    "gp_email": "gp@example.com",
    "questionnaire_data": {
      "project_name": "My Project",
      "description": "Test project",
      "frontend_preference": "React",
      "backend_preference": "Python",
      "database_type": "PostgreSQL"
    }
  }'
```

Expected response:
```json
{
  "status": "received",
  "message": "Webhook executed successfully"
}
```

---

## Configuration

### OpenRouter API Key

✅ **Already configured!**

Location: `.env` file
```bash
OPENROUTER_API_KEY=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
```

The key is automatically loaded by `docker-compose` and passed to n8n.

**To update the key later:**
1. Edit `.env` file
2. Update `OPENROUTER_API_KEY` value
3. Restart n8n: `docker-compose restart n8n`

### Environment Variables (Already Set)

```bash
# .env file (not committed to git)
OPENROUTER_API_KEY=sk-or-v1-...

# docker-compose.yml automatically loads from .env
N8N_WEBHOOK_URL=http://localhost:5678/webhook
N8N_API_URL=http://localhost:5678/api
```

### Backend Settings

In `backend/app/core/config.py`:

```python
N8N_WEBHOOK_URL: str = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook")
N8N_API_URL: str = os.getenv("N8N_API_URL", "http://localhost:5678/api")
```

### Qwen AI (OpenRouter)

| Feature | Details |
|---------|---------|
| **Provider** | OpenRouter (free tier + paid) |
| **Model** | Qwen 2.5 7B Instruct |
| **Cost** | Free tier includes 1M tokens/month |
| **Speed** | ~5-10 seconds per questionnaire |
| **Quality** | ⭐⭐⭐ (excellent for analysis) |
| **API Key** | Already configured in `.env` |

**Free Tier Limits:**
- 1M tokens/month = ~5,000+ questionnaires
- Rate limited to prevent abuse
- No credit card required initially

**If you need more:**
- Add credit card to OpenRouter account
- Pricing: $0.002 per 1K input tokens, $0.002 per 1K output tokens
- Average questionnaire: ~2,500 tokens = ~$0.000005

---

## Testing the Integration

### Test 1: Manual Webhook Call

```bash
curl -X POST http://localhost:5678/webhook/external-project \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "request_number": "REQ-20260406-TEST001",
    "gp_email": "gp@example.com",
    "questionnaire_data": {
      "project_name": "E-commerce Platform",
      "project_slug": "ecommerce-platform",
      "description": "Online shopping platform",
      "business_context": "B2C marketplace",
      "output_type": "Monolith",
      "deployment_model": "Cloud (AWS/Azure/GCP)",
      "frontend_preference": "React",
      "backend_preference": "Python (FastAPI/Django)",
      "database_type": "PostgreSQL",
      "testing_strategy": "Unit + Integration + E2E",
      "ci_cd_requirements": "Sim"
    }
  }'
```

### Test 2: Full Flow via Frontend

1. Navigate to `/novo-projeto?token=<token>`
2. Fill questionnaire
3. Submit
4. Check Admin dashboard: `/admin/external-requests`
5. Verify `n8n_validation_result` is populated with analysis

### Test 3: Check Logs

```bash
# Backend logs
docker logs gca-backend | grep "n8n"

# n8n logs
docker logs gca-n8n | grep "external"
```

---

## What Qwen Analyzes

The workflow uses Qwen AI to detect:

1. **GAPS**
   - Missing required fields (project name, description, etc)
   - Incomplete stack definition (frontend without backend)
   - Missing security/compliance specifications
   - No testing strategy defined

2. **CONFLICTS**
   - Monolith + Microservices (mutually exclusive)
   - React + Flutter (different target platforms)
   - SQL-only + NoSQL requirement (contradictory)
   - On-premises + serverless (incompatible models)

3. **RISKS**
   - Misaligned frontend/backend choices
   - Overly complex architecture for stated scale
   - Missing disaster recovery plan
   - Performance targets unrealistic for chosen stack

4. **RECOMMENDATIONS**
   - Suggested stack combinations
   - Database optimization hints
   - Architecture alignment tips
   - Compliance & security best practices

---

## Monitoring & Debugging

### Check n8n Execution History

1. Open n8n dashboard
2. Click the workflow
3. Click **Execution** tab
4. View execution logs and outputs

### Check Backend Webhook Callback

```bash
# View recent webhook calls
docker logs gca-backend | grep "webhook.external_project"

# Check database for validation results
psql postgresql://gca:gca_secret@localhost:5432/gca
SELECT request_number, status, n8n_validation_result 
FROM external_project_request 
WHERE n8n_validation_result IS NOT NULL 
LIMIT 5;
```

### Common Issues

**Issue:** n8n webhook not triggering
- **Solution:** Check n8n is running: `docker logs gca-n8n`
- Check backend URL: `curl http://localhost:5678/webhook/external-project` should return 405 (method not allowed)

**Issue:** Qwen API not responding
- **Solution:** Verify API key in n8n credentials
- Check OpenRouter/HF quota not exceeded
- Test API directly: `curl https://api.openrouter.ai/api/v1/chat/completions`

**Issue:** Backend webhook callback failing
- **Solution:** Ensure backend is running: `docker logs gca-backend`
- Check POST /api/v1/webhooks/external-project-result endpoint exists
- Verify ExternalProjectRequest ID is valid UUID

**Issue:** Analysis incomplete or wrong format
- **Solution:** Adjust Qwen prompt in n8n
- Lower temperature to 0.3 for more deterministic JSON output
- Add JSON formatting instructions to prompt

---

## Architecture Flow (Detailed)

```
1. GP submits questionnaire via /novo-projeto?token=xxx
   ↓
2. Backend: submit_questionnaire()
   - Save questionnaire_data to DB
   - Update status: "submitted"
   - Send confirmation email to GP
   - Send admin notification email
   ↓
3. Async: N8nService.trigger_external_project_validation()
   - POST to http://localhost:5678/webhook/external-project
   - Payload: request_id, request_number, gp_email, questionnaire_data
   ↓
4. n8n receives webhook
   - Prepare Qwen analysis prompt
   ↓
5. Qwen AI analyzes questionnaire
   - Identifies gaps, conflicts, risks
   - Generates recommendations
   - Returns JSON analysis
   ↓
6. n8n calls backend callback
   - POST /api/v1/webhooks/external-project-result
   - Payload: request_id, analysis, validated result
   ↓
7. Backend webhook handler
   - Update ExternalProjectRequest.n8n_validation_result = analysis
   - Update status: "pending_approval"
   ↓
8. Admin reviews request
   - Views analysis from Qwen in AdminExternalRequestDetailPage
   - Can approve/reject with full context
   ↓
9. Admin approves
   - Status: "approved"
   - Project created immediately
   - GP notified via email
```

---

## Performance & Costs

**OpenRouter Qwen 2.5 7B Pricing:**
- Free tier: 1M tokens/month (typically includes 5000+ questionnaires)
- Paid: $0.002 per 1K input tokens, $0.002 per 1K output tokens
- Average questionnaire: ~2K tokens input + 500 tokens output = ~$0.000005

**Ollama (Local):**
- Cost: FREE
- Requires: ~7GB GPU/CPU memory
- Speed: 5-15 seconds per questionnaire

---

## Next Steps

1. ✅ Start all services: `docker-compose up -d`
2. ✅ Create n8n workflow (import JSON or manual)
3. ✅ Configure Qwen AI provider (OpenRouter/Ollama/HF)
4. ✅ Test webhook endpoint
5. ✅ Test full flow via frontend
6. ✅ Verify admin sees analysis

---

## Troubleshooting Checklist

- [ ] Docker containers running: `docker ps`
- [ ] n8n accessible: `curl http://localhost:5678/api/v1/health`
- [ ] Backend running: `curl http://localhost:8000/health`
- [ ] n8n workflow active/saved
- [ ] Qwen API key configured (if using external API)
- [ ] Backend can reach n8n: `curl http://gca-n8n:5678` from backend container
- [ ] Database n8n table created: `\dt` in psql

