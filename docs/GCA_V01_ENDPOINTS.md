# GCA v0.1 — Documentação dos Endpoints Novos

Data: 2026-04-26  
Status: ✅ Implementado e Testado  
Testes: 44/44 passando

---

## 1. Geração Automática de Questionnaire (M01)

**Endpoint**: `POST /api/v1/projects/{project_id}/m01/generate-questionnaire`

**Descrição**: Lê um documento de requisitos e gera automaticamente 30-50 questões dinâmicas baseadas em gaps detectados.

### Request

```json
{
  "document_id": "uuid-do-documento",
  "domain": "juridico",
  "doc_type": "requisitos"
}
```

**Campos**:
- `document_id` (string, obrigatório): ID do documento já ingestado
- `domain` (string, obrigatório): Domínio do projeto (ex: juridico, software, financeiro)
- `doc_type` (string, obrigatório): Tipo de documento (requisitos, design, spec, arquitetura)

### Response (200 OK)

```json
{
  "iteration_id": "iter-20260426-abc123",
  "count": 42,
  "questions": [
    {
      "id": "M01_Q1",
      "text": "Qual é o principal objetivo do sistema AJA?",
      "tipo": "aberta",
      "opcoes": null,
      "obrigatoria": true,
      "dica": "Resuma em uma frase o propósito central"
    },
    {
      "id": "M01_Q2",
      "text": "Quais tecnologias serão usadas no backend?",
      "tipo": "aberta",
      "opcoes": null,
      "obrigatoria": true,
      "dica": null
    }
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

**Status Codes**:
- `200`: Questionnaire gerado com sucesso (30-50 questões)
- `422`: Validação falhou (documento muito curto, < 100 chars)

---

## 2. Validação de Respostas por Personas

**Endpoint**: `POST /api/v1/questionnaires/projects/{project_id}/questionnaire/validate`

**Descrição**: 5 Personas especializadas (GP, Arquiteto, DBA, Dev Sr, QA) analisam as respostas do questionnaire e aprovam ou pedem clarificação.

### Request

```json
{
  "responses": {
    "M01_Q1": "Automação jurídica para gerar contratos com IA",
    "M01_Q2": "Python FastAPI, PostgreSQL, React 18, Redis, Celery",
    "M01_Q3": "6 meses MVP",
    "...": "outras respostas"
  },
  "extracted_concepts": [
    "automação",
    "documentos",
    "LGPD"
  ],
  "document_domain": "juridico"
}
```

**Campos**:
- `responses` (dict, obrigatório): Respostas do user ao questionnaire (chave = ID da questão, valor = resposta)
- `extracted_concepts` (array, obrigatório): Conceitos extraídos pelo M01 (saída do endpoint anterior)
- `document_domain` (string, obrigatório): Domínio do projeto

### Response (200 OK)

```json
{
  "all_approved": true,
  "next_action": "aggregate_to_ocg",
  "personas": [
    {
      "persona": "GP (Gerente de Projetos)",
      "status": "approved",
      "decision": "Escopo claro, timeline realista, viabilidade confirmada",
      "severity": "info"
    },
    {
      "persona": "Arquiteto de Soluções",
      "status": "approved",
      "decision": "Stack bem definido, padrões aplicáveis, NFRs alcançáveis",
      "severity": "info"
    },
    {
      "persona": "DBA (Especialista em Dados)",
      "status": "approved",
      "decision": "Schema viável, retenção OK, índices necessários identificados",
      "severity": "info"
    },
    {
      "persona": "Dev Senior",
      "status": "approved",
      "decision": "6 meses é realista para MVP, tech debt mínimo",
      "severity": "info"
    },
    {
      "persona": "QA (Qualidade)",
      "status": "approved",
      "decision": "Critérios de aceite claros, testabilidade confirmada",
      "severity": "info"
    }
  ]
}
```

**Ou, se alguma Persona pede clarificação**:

```json
{
  "all_approved": false,
  "next_action": "generate_followup_questionnaire",
  "personas": [
    {
      "persona": "DBA (Especialista em Dados)",
      "status": "needs_clarification",
      "decision": "Preciso entender melhor a estratégia de backup e disaster recovery",
      "severity": "warning",
      "followup_questions": [
        {
          "id": "FOLLOW_Q1",
          "text": "Qual será o RTO (Recovery Time Objective) exigido?",
          "tipo": "aberta",
          "obrigatoria": true
        },
        {
          "id": "FOLLOW_Q2",
          "text": "Quantos dias de retenção de backup são necessários?",
          "tipo": "aberta",
          "obrigatoria": true
        }
      ]
    },
    {
      "persona": "GP (Gerente de Projetos)",
      "status": "approved",
      "decision": "Escopo OK",
      "severity": "info"
    }
  ]
}
```

**Status Codes**:
- `200`: Validação completa, 5 Personas retornaram veredito
- `422`: Request inválido (campos obrigatórios faltando)

---

## Fluxo Completo GCA v0.1

```
1. User faz upload: AJA_v3.0.docx
   ↓
2. Endpoint ingestão (existing) processa
   ↓
3. POST /m01/generate-questionnaire
   Input: document_id, domain, doc_type
   Output: 40-50 questões + conceitos + gaps
   ↓
4. User responde questionnaire (UI existing)
   ↓
5. POST /questionnaire/validate
   Input: respostas + conceitos + domínio
   Output: 5 Personas [approved | needs_clarification]
   ↓
   ├─ Se 5/5 aprovam → aggregate_to_ocg
   └─ Se algum pede clarificação → volta ao passo 3 (novo questionnaire)
   ↓
6. OCG atualiza com deltas auditados (migration 053)
```

---

## Integração com OCG Delta Tracking (Migration 053)

Cada resposta aprovada cria entry em `ocg_delta_log`:

```sql
INSERT INTO ocg_delta_log (
  source,           -- 'questionnaire_response'
  persona_id,       -- 'gp' | 'arquiteto' | 'dba' | 'dev_sr' | 'qa'
  decision,         -- 'approved' | 'needs_clarification'
  hash_chain        -- SHA256 da sequência
)
VALUES (...)
```

**Garantia**: OCG nunca contrai (score sempre ≥ anterior) via trigger PL/pgSQL `validate_ocg_expansion()`.

---

## Testes

- **M01Service**: 16 unit tests (geração, truncação, JSON parsing, domain, modelo)
- **PersonaValidator**: 22 unit tests (5 personas × 2 cenários + consolidador)
- **E2E Flow**: 4 testes (M01 → Personas → OCG)
- **OCG Constraint**: 2 testes (expansion validation)

**Total**: 44/44 passando ✅

---

## Próximas Iterações

- **v0.1.1**: Paralelismo das 5 Personas (Celery gather)
- **v0.2**: Cache de questionnaires por hash documento
- **v0.3**: Versionamento de Personas (prompts evoluem)
