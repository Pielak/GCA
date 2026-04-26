# GCA v0.1 — Guia Prático de Teste

**Objetivo**: Validar o pipeline completo (M01 → Personas → OCG) com documento AJA real

**Tempo estimado**: 15-20 minutos (incluindo resposta às questões)

---

## 🚀 **Pré-Requisitos**

- [ ] Servidor FastAPI rodando (`localhost:8000`)
- [ ] Documento AJA v3.0 real disponível (PDF ou .docx)
- [ ] `curl` instalado (ou Postman/Thunder Client)
- [ ] Acesso ao DB para verificar audit trail

---

## 📋 **Passo 1: Upload do Documento (Existing Endpoint)**

**Objetivo**: Ingerir o documento AJA v3.0 para extrair texto

### Comando

```bash
# Se o documento é PDF/DOCX, ele será extraído automaticamente
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/ingestion \
  -H "Authorization: Bearer {seu_token}" \
  -F "file=@/caminho/para/AJA_v3.0.pdf" \
  -F "document_type=requisitos" \
  -F "domain=juridico"
```

### Response (200 OK)

```json
{
  "document_id": "doc-uuid-abc123",
  "filename": "AJA_v3.0.pdf",
  "extracted_text": "SISTEMA DE AUTOMAÇÃO JURÍDICA ASSISTIDA...",
  "status": "ingested"
}
```

**Guarde o `document_id`** — você vai usar no próximo passo.

---

## 🤖 **Passo 2: M01 Gera Questionnaire (NOVO)**

**Objetivo**: M01Service lê o documento e gera 30-50 questões dinâmicas

### Comando

```bash
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/m01/generate-questionnaire \
  -H "Authorization: Bearer {seu_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc-uuid-abc123",
    "domain": "juridico",
    "doc_type": "requisitos"
  }'
```

### Response (200 OK)

```json
{
  "iteration_id": "iter-20260426-xyz789",
  "count": 42,
  "questions": [
    {
      "id": "M01_Q1",
      "text": "Qual é o principal objetivo do sistema AJA?",
      "tipo": "aberta",
      "opcoes": null,
      "obrigatoria": true,
      "dica": "Resuma em uma frase"
    },
    {
      "id": "M01_Q2",
      "text": "Quais tecnologias serão usadas no backend?",
      "tipo": "aberta",
      "opcoes": null,
      "obrigatoria": true,
      "dica": null
    },
    // ... mais 40 questões ...
  ],
  "extracted_concepts": [
    "automação jurídica",
    "documentos",
    "LGPD",
    "compliance",
    "assinatura digital"
  ],
  "gaps_identified": [
    "Timeline vaga para MVP",
    "Stack parcialmente definido",
    "Escalabilidade não mencionada"
  ]
}
```

**O que observar:**
- [ ] Contagem de questões: 30-50? ✅
- [ ] Conceitos extraídos fazem sentido? ✅
- [ ] Gaps identificados são reais? ✅
- [ ] Questões são específicas para o domínio (jurídico)? ✅

**Guarde o `iteration_id`** e copie as questões.

---

## 💬 **Passo 3: Você Responde o Questionnaire**

**Objetivo**: Simular resposta de um GP aos questions gerados

### Preparar JSON com respostas

```json
{
  "responses": {
    "M01_Q1": "Automação jurídica para gerar contratos com IA",
    "M01_Q2": "Python FastAPI, PostgreSQL, React 18, Redis, Celery",
    "M01_Q3": "6 meses MVP",
    "M01_Q4": "R$ 500k inicial",
    "M01_Q5": "100+ requisitos coletados",
    "M01_Q6": "5 advogados como piloto",
    "M01_Q7": "LGPD compliance obrigatório",
    "M01_Q8": "Assinatura digital ICP-Brasil",
    // ... respostas para TODAS as 42 questões ...
  },
  "extracted_concepts": [
    "automação jurídica",
    "documentos",
    "LGPD",
    "compliance",
    "assinatura digital"
  ],
  "document_domain": "juridico"
}
```

**Dica**: Use as respostas do teste E2E como baseline (arquivo `test_gca_v01_e2e_flow.py`)

---

## ✅ **Passo 4: Personas Validam (NOVO)**

**Objetivo**: 5 Personas analisam suas respostas e aprovam ou pedem clarificação

### Comando

```bash
curl -X POST http://localhost:8000/api/v1/questionnaires/projects/{project_id}/questionnaire/validate \
  -H "Authorization: Bearer {seu_token}" \
  -H "Content-Type: application/json" \
  -d @responses.json
```

(Ou via Postman: paste JSON no body)

### Response (200 OK) — Cenário 1: Todos aprovam

```json
{
  "all_approved": true,
  "next_action": "aggregate_to_ocg",
  "personas": [
    {
      "persona": "GP (Gerente de Projetos)",
      "status": "approved",
      "decision": "Escopo claro ✓, timeline realista ✓, viabilidade ✓",
      "severity": "info"
    },
    {
      "persona": "Arquiteto de Soluções",
      "status": "approved",
      "decision": "Stack bem definido ✓, padrões aplicáveis ✓, NFRs ✓",
      "severity": "info"
    },
    {
      "persona": "DBA (Especialista em Dados)",
      "status": "approved",
      "decision": "Schema viável ✓, retenção OK ✓, índices ✓",
      "severity": "info"
    },
    {
      "persona": "Dev Senior",
      "status": "approved",
      "decision": "6 meses realista ✓, tech debt mínimo ✓",
      "severity": "info"
    },
    {
      "persona": "QA (Qualidade)",
      "status": "approved",
      "decision": "Critérios de aceite claros ✓, testável ✓",
      "severity": "info"
    }
  ]
}
```

**O que observar:**
- [ ] Todas as 5 Personas responderam? ✅
- [ ] Status esperado (approved ou needs_clarification)? ✅
- [ ] Decision tem feedback útil? ✅
- [ ] Se alguma pediu clarificação, há followup_questions? (ver Cenário 2)

### Response (200 OK) — Cenário 2: Alguma Persona pede clarificação

```json
{
  "all_approved": false,
  "next_action": "generate_followup_questionnaire",
  "personas": [
    {
      "persona": "DBA (Especialista em Dados)",
      "status": "needs_clarification",
      "decision": "Preciso entender melhor a estratégia de backup",
      "severity": "warning",
      "followup_questions": [
        {
          "id": "FOLLOW_Q1",
          "text": "Qual será o RTO (Recovery Time Objective)?",
          "tipo": "aberta",
          "obrigatoria": true,
          "dica": "Quantas horas de downtime é aceitável?"
        },
        {
          "id": "FOLLOW_Q2",
          "text": "Quantos dias de retenção de backup?",
          "tipo": "aberta",
          "obrigatoria": true,
          "dica": null
        }
      ]
    },
    // ... outras 4 Personas com status "approved" ...
  ]
}
```

**Se isso acontecer:**
1. Responda as `followup_questions`
2. Volta ao Passo 4 (Validator novamente)
3. Continue até que `all_approved = true`

---

## 🎯 **Passo 5: OCG Atualiza (Existing)**

**Objetivo**: Confirmar que OCG foi construído com deltas auditados

### Verificar no Admin Panel

1. Acesse `localhost:3000/admin` (interface web)
2. Vá para aba **"Auditoria Global"**
3. Procure por entradas com:
   - `source` = "questionnaire_response"
   - `persona_id` = ["gp", "arquiteto", "dba", "dev_sr", "qa"]
   - `decision` = "approved" (ou "needs_clarification" se houve loop)

### Verificar via SQL (opcional)

```sql
SELECT 
  project_id,
  source,
  persona_id,
  decision,
  created_at
FROM ocg_delta_log
WHERE source = 'questionnaire_response'
ORDER BY created_at DESC
LIMIT 10;
```

**O que observar:**
- [ ] Existe entrada para cada Persona que validou? ✅
- [ ] `decision` está correto (approved/needs_clarification)? ✅
- [ ] `hash_chain` está presente (auditoria)? ✅
- [ ] OCG score aumentou (expansion, nunca contração)? ✅

---

## 📊 **Passo 6: Validar Output**

### Checklist de Sucesso

- [ ] M01 gerou 30-50 questões
- [ ] Questões são relevantes para domínio (juridico)
- [ ] 5 Personas responderam (ou geraram followup)
- [ ] OCG foi atualizado com deltas auditados
- [ ] Nenhum erro nos logs

### Comando para ver logs

```bash
# Terminal 1: Seguir logs em tempo real
tail -f /var/log/gca/app.log | grep -E "M01|Persona|OCG|questionnaire"

# Terminal 2: Rodar o teste enquanto acompanha logs
```

---

## 🔄 **Cenário: Loop Recursivo (Persona pede clarificação)**

Se alguma Persona retornar `needs_clarification`:

1. **Receba** `followup_questions`
2. **Responda** as novas questões
3. **Prepare** novo JSON:
   ```json
   {
     "responses": {
       "M01_Q1": "...",
       // ... respostas originais ...
       "FOLLOW_Q1": "Sua resposta à pergunta de clarificação",
       "FOLLOW_Q2": "Outra resposta"
     },
     "extracted_concepts": [ ... ],
     "document_domain": "juridico"
   }
   ```
4. **Chame** Validator novamente
5. **Repita** até `all_approved = true`

---

## ❌ **Troubleshooting**

### Erro: 422 Validation Error

**Causa**: JSON inválido ou campo faltando  
**Solução**: Verificar que:
- Todas as questões têm resposta (mesmo se vazia)
- Tipo de dados correto (string, não int)
- `extracted_concepts` é um array

### Erro: 500 Internal Server Error

**Causa**: Erro no servidor  
**Solução**: 
- Verificar logs: `tail -f /var/log/gca/app.log`
- Confirmar que Anthropic API key está configurada
- Verificar DB connection

### M01 gera < 30 ou > 50 questões

**Esperado**: M01 sempre retorna 30-50  
**Se não**: Verificar prompt em `app/services/m01_service.py`

---

## 📝 **Próximas Ações**

### Semana 2 (Imediatamente):
1. Teste com AJA v3.0 real (este guia)
2. Coleta feedback: "Que tal as questões?"
3. Anote quais Personas foram úteis

### Semana 3:
- Refine M01_SYSTEM_PROMPT baseado em feedback
- Ajuste critérios de cada Persona
- Expandir cobertura para casos especiais

### Semana 4:
- Release v0.1.0
- Documentação para os 5 advogados pilotos

---

## 🎥 **Exemplo Completo em cURL**

```bash
#!/bin/bash

PROJECT_ID="seu-project-uuid"
TOKEN="seu-bearer-token"

# 1. Upload (existing)
echo "📤 Passo 1: Upload do documento..."
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/ingestion \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@AJA_v3.0.pdf" \
  -F "document_type=requisitos" \
  -F "domain=juridico")

DOC_ID=$(echo $RESPONSE | jq -r '.document_id')
echo "✅ Document ID: $DOC_ID"

# 2. M01 gera questionnaire
echo "🤖 Passo 2: M01 gerando questionnaire..."
M01_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/m01/generate-questionnaire \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"document_id\": \"$DOC_ID\",
    \"domain\": \"juridico\",
    \"doc_type\": \"requisitos\"
  }")

ITER_ID=$(echo $M01_RESPONSE | jq -r '.iteration_id')
QUESTION_COUNT=$(echo $M01_RESPONSE | jq -r '.count')
echo "✅ Iteration ID: $ITER_ID"
echo "✅ Questões geradas: $QUESTION_COUNT"

# 3-4. Você responde e Personas validam (manual)
echo "⏸️  Pause aqui: responda as $QUESTION_COUNT questões"
echo "📋 Copie as respostas em um arquivo JSON"
echo "Depois continue com o Passo 4..."
```

---

**Bom teste! 🚀**
