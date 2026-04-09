# 🔄 Guia de Migração: Claude → DeepSeek

**Data**: 6 de Abril, 2026  
**Economia**: ~80% em custos de API  
**Status**: ✅ Pronto para ativar

---

## Mudanças Realizadas

### 1. Backend (FastAPI)
✅ **Arquivo**: `/home/luiz/GCA/backend/.env`
```bash
DEFAULT_AI_PROVIDER="deepseek"
DEFAULT_AI_MODEL="deepseek-chat"
DEEPSEEK_API_KEY="sk-767b8d1d04a640a8adc72ba1dc840290"
```

**O que acontece**: Todos os endpoints que usam IA agora usam DeepSeek por padrão.

---

### 2. n8n Workflow (Novo)
✅ **Arquivo**: `/home/luiz/GCA_Project/n8n-workflow-deepseek.json`

**Mudanças vs Haiku**:
- Node "Haiku AI Analysis" → "DeepSeek AI Analysis"
- URL: `https://api.deepseek.com/v1/chat/completions`
- Model: `deepseek-chat` (OpenAI-compatible)
- Headers: `Authorization: Bearer {API_KEY}`
- Prompt: Otimizado para português (DeepSeek é nativo em PT-BR)

**Novo node adicionado**: "Parse DeepSeek Response"
- Extrai `choices[0].message.content` do formato OpenAI
- Passa JSON limpo pro backend

---

## Como Ativar

### Opção A: Importar novo workflow (Recomendado ✅)

1. Acesse **n8n UI**: `http://localhost:5678`

2. Click em **"Workflows"** → **"Import workflow"**

3. Selecione o arquivo:
   ```
   /home/luiz/GCA_Project/n8n-workflow-deepseek.json
   ```

4. Click **"Import"** → O workflow aparecerá com todos os 5 nodes prontos

5. Click **"Activate"** (botão azul no canto superior)

6. Teste com curl (veja seção abaixo)

---

### Opção B: Atualizar workflow existente (Manual)

Se você prefere manter o workflow antigo e só mudar os nodes:

**Node "Haiku AI Analysis" → Rename para "DeepSeek AI Analysis"**

1. Abra o workflow existente
2. Click no node "Haiku AI Analysis"
3. Configure:
   ```
   URL: https://api.deepseek.com/v1/chat/completions
   Method: POST
   Body (JSON):
   {
     "model": "deepseek-chat",
     "max_tokens": 2000,
     "temperature": 0.7,
     "messages": [
       {
         "role": "user",
         "content": "{{ $json.analysis_prompt }}"
       }
     ]
   }
   
   Headers (Generic Auth):
   Authorization: Bearer sk-767b8d1d04a640a8adc72ba1dc840290
   Content-Type: application/json
   ```

4. Delete o node "Callback Backend" atual

5. Adicione novo node "Function" chamado "Parse DeepSeek Response":
   ```javascript
   return {
     request_id: $node['webhook_trigger'].json.request_id,
     request_number: $node['webhook_trigger'].json.request_number,
     gp_email: $node['webhook_trigger'].json.gp_email,
     analysis: $node['deepseek_analysis'].json.choices[0].message.content
   };
   ```

6. Reconecte: `deepseek_analysis` → `parse_deepseek_response` → `callback_backend`

---

## Teste o Workflow

### 1. Ativar workflow
```bash
curl -X POST http://localhost:5678/api/v1/workflows/1/activate \
  -H "Content-Type: application/json"
```

### 2. Enviar questionnaire de teste
```bash
curl -X POST http://localhost:5678/webhook/external-project \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "TEST-001",
    "request_number": "REQ-20260406-TEST",
    "gp_email": "test@example.com",
    "questionnaire_data": {
      "project_name": "Test Project",
      "description": "API REST em Python",
      "languages": ["Python"],
      "frameworks": ["FastAPI"],
      "database": "PostgreSQL"
    }
  }'
```

### 3. Verificar resultado no admin
- Frontend: `http://localhost:5173/admin/external-requests`
- Procure pelo `request_id` "TEST-001"
- A análise deve aparecer em **PORTUGUÊS**

---

## Validação de Qualidade

### DeepSeek vs Haiku

| Aspecto | DeepSeek | Haiku |
|---------|----------|-------|
| **Codificação** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Português** | ⭐⭐⭐⭐⭐ (Nativo) | ⭐⭐⭐⭐ |
| **Custo/1M tokens** | $0.14 | $0.80 |
| **Velocidade** | Rápido | Muito rápido |
| **Estrutura JSON** | OpenAI-compatible | Anthropic |

### Testes esperados:
✅ Questionnaire → DeepSeek → Backend (completo)  
✅ Análise em português fluente  
✅ JSON estruturado com gaps, conflicts, risks, recommendations  
✅ Admin panel mostra análise corretamente  

---

## Documentação Técnica

### DeepSeek API
- **Endpoint**: `https://api.deepseek.com/v1/chat/completions`
- **Model**: `deepseek-chat` (recomendado) ou `deepseek-coder`
- **Auth**: Bearer token (OpenAI-compatible)
- **Limite**: 128k tokens por request

### Backend (FastAPI)
- `AIService._query_deepseek()` já implementado
- Fallback automático se DeepSeek falhar
- Logging de todos os requests

### n8n Workflow
- 5 nodes (webhook → prompt → deepseek → parse → callback)
- `alwaysOutputData: true` em todos os nodes
- Tratamento de JSON response automático

---

## Rollback (se necessário)

Se precisar voltar para Haiku:

1. Backend `.env`:
   ```bash
   DEFAULT_AI_PROVIDER="anthropic"
   DEFAULT_AI_MODEL="claude-3-5-haiku"
   ```

2. n8n: Reativar workflow antigo (`n8n-workflow-haiku.json`)

3. Restart backend:
   ```bash
   cd /home/luiz/GCA/backend
   docker-compose restart backend
   ```

---

## Próximos Passos

1. ✅ Backend configurado
2. ⏳ **Você**: Importar workflow no n8n
3. ⏳ **Você**: Testar com questionnaire
4. ⏳ **Você**: Validar qualidade das respostas
5. ⏳ **Claude**: Commit ao git

Quer que eu ajude com o próximo passo?
