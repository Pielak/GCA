# OCG Reativo + Billing IA por Projeto — Especificação Técnica

**Data**: 2026-04-09
**Sessão**: 17
**Status**: Aprovado pelo usuário

---

## Objetivo

Transformar o OCG de documento estático (gerado uma vez) em **inteligência viva** que evolui continuamente com base em eventos do sistema. Toda ingestão de documento dispara atualização do OCG via IA, com versionamento, delta-log, billing e propagação para módulos dependentes.

---

## Princípios

1. **Sempre IA** — todo documento ingerido passa pelo LLM com OCG atual como contexto
2. **Fallback = circuit breaker** — se IA indisponível, documento fica `ocg_pending` (nunca persiste OCG parcial)
3. **Versionamento obrigatório** — toda mudança gera nova versão + delta-log
4. **Billing compartimentalizado** — custo em USD registrado por projeto, por operação
5. **Propagação seletiva** — apenas módulos afetados pelos campos alterados são reavaliados

---

## Novos Serviços

### 1. OCGUpdaterService (`ocg_updater_service.py`)

**Responsabilidade**: Receber análise do Arguidor → chamar LLM → atualizar OCG → delta-log → billing → emitir evento.

**Fluxo**:
```
Arguidor completa análise
    ↓
OCGUpdaterService.update_from_analysis(project_id, document_id, analysis)
    ├── Carrega OCG atual (versão N)
    ├── Monta prompt: OCG atual + análise + texto do documento
    ├── Chama LLM (AIKeyResolver.get_gca_key ou get_project_key)
    ├── Parseia resposta: updated_ocg, changes[], change_type, context_health
    ├── Valida: schema OK? campos obrigatórios presentes?
    │   ├── SIM → persiste OCG versão N+1
    │   └── NÃO → registra erro, mantém versão N
    ├── Registra delta-log (ocg_delta_log)
    ├── Registra billing (ai_usage_log)
    ├── Emite evento OCG_UPDATED via AuditService
    └── Dispara PropagationService.propagate(project_id, changes)
```

**Prompt ao LLM**:
```
CONTEXTO:
- OCG atual (JSON, versão N)
- Análise do Arguidor (classificação, gaps, módulos candidatos)
- Texto extraído do documento

INSTRUÇÃO (em PT-BR):
Dado o OCG atual e esta nova análise, retorne JSON com:
1. "updated_ocg": OCG completo atualizado (mesmo schema v1.0.0)
2. "changes": lista de {field, old, new, reason} para cada campo alterado
3. "change_type": "EXPAND" (mais contexto) ou "CONTRACT" (reduz confiança)
4. "context_health": {depth, confidence (0-1), quality (good|partial|bad)}

Regras:
- Manter campos não afetados intactos
- Recalcular COMPOSITE_SCORE se pillar scores mudaram
- Atualizar APPROVAL_STATUS se score composto cruzou threshold
- Toda justificativa em Português-BR
```

**Fallback** (IA indisponível):
- Marca `ingested_documents.arguider_status = 'ocg_pending'`
- Não altera OCG
- Job periódico ou endpoint manual reprocessa pendentes

### 2. PropagationService (`propagation_service.py`)

**Responsabilidade**: Analisar campos alterados no OCG e disparar ações seletivas.

**Mapeamento de propagação**:

| Campos alterados | Ação |
|-----------------|------|
| `STACK_RECOMMENDATION` | Regenera backlog "modules". Marca CodeGen desatualizado |
| `COMPLIANCE_CHECKLIST` | Regenera backlog "compliance". Reavalia quarentena |
| `TESTING_REQUIREMENTS` | Regenera backlog "tests". Marca QA desatualizado |
| `ARCHITECTURE_OVERVIEW` | Regenera backlog "modules" + "security" |
| `RISK_ANALYSIS` | Atualiza APPROVAL_STATUS |
| Qualquer mudança | BacklogService.regenerate_from_ocg(). Incrementa LiveDocs. Evento BACKLOG_REGENERATED |

**Execução**: Async (não bloqueia upload). Se falhar, registra erro — propagação pode ser re-disparada via `POST /projects/{id}/ocg/propagate`.

### 3. AIBillingService (`ai_billing_service.py`)

**Responsabilidade**: Registrar toda chamada LLM com custo estimado. Fornecer resumo por projeto.

**Registro por chamada**:
- `project_id` — compartimentalizado
- `provider` — deepseek, anthropic, openai, grok, gemini
- `model` — deepseek-chat, claude-opus-4-6, etc.
- `operation` — ocg_generation, ocg_update, arguider_analysis, codegen, qa_execution, etc.
- `tokens_input` + `tokens_output`
- `cost_usd` — calculado pela tabela de preços
- `actor_id` — quem disparou
- `created_at`

**Tabela de preços** (config no backend, não banco):
```python
AI_PRICING = {
    "deepseek": {"deepseek-chat": {"input": 0.14, "output": 0.28}},  # por 1M tokens
    "anthropic": {"claude-opus-4-6": {"input": 15.0, "output": 75.0}},
    "openai": {"gpt-4o": {"input": 2.50, "output": 10.0}},
    "grok": {"grok-3-mini": {"input": 0.30, "output": 0.50}},
}
```

**Cálculo**: `cost = (tokens_input / 1_000_000 * price_input) + (tokens_output / 1_000_000 * price_output)`

**Resumo por projeto**: total USD, breakdown por operação, por provider, timeline.

---

## Novos Endpoints

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/projects/{id}/ocg/history` | Histórico de versões do OCG | Membro |
| `GET` | `/projects/{id}/ocg/delta-log` | Log de mudanças (campo, antes, depois, justificativa) | Membro |
| `GET` | `/projects/{id}/ocg/health` | Saúde do contexto (depth, confidence, quality) | Membro |
| `POST` | `/projects/{id}/ocg/propagate` | Forçar re-propagação manual | GP |
| `POST` | `/projects/{id}/ingestion/{doc_id}/release` | Liberar documento da quarentena → dispara OCG update | GP |
| `GET` | `/projects/{id}/billing` | Resumo de gastos IA (total, por operação, por provider) | GP/Admin |
| `GET` | `/projects/{id}/billing/detail` | Log detalhado de cada chamada IA | GP/Admin |

---

## Alterações em Tabelas Existentes

### `ocg`
- Adicionar `context_health` (TEXT/JSON) — `{depth, confidence, quality}`
- Adicionar `change_type` (VARCHAR 20) — `INITIAL`, `EXPAND`, `CONTRACT`

### `ingested_documents`
- `arguider_status` aceita novo valor: `ocg_pending` (documento analisado pelo Arguidor mas OCG não atualizado por indisponibilidade da IA)

---

## Nova Tabela

### `ai_usage_log`
```sql
CREATE TABLE ai_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_usage_project ON ai_usage_log(project_id);
CREATE INDEX idx_ai_usage_operation ON ai_usage_log(project_id, operation);
CREATE INDEX idx_ai_usage_created ON ai_usage_log(created_at);
```

---

## Integração com Código Existente

### `ingestion_service.py` → `_analyze_async()`
Após Arguidor completar análise:
```python
# Existente: marca ocg_updated = True
# NOVO: chama OCGUpdaterService
from app.services.ocg_updater_service import OCGUpdaterService
updater = OCGUpdaterService(db)
await updater.update_from_analysis(project_id, document_id, analysis_result)
```

### `agent_service.py` → `_call_llm()`
Após cada chamada:
```python
# NOVO: registra billing
from app.services.ai_billing_service import AIBillingService
billing = AIBillingService(db)
await billing.log_usage(project_id, provider, model, operation, tokens_input, tokens_output, actor_id)
```

### `ocg_service.py` → `generate_ocg_from_questionnaire()`
Na geração inicial, registrar `change_type = 'INITIAL'` e billing de todas as chamadas.

---

## Critérios de Aceite

1. Documento ingerido → Arguidor analisa → OCG atualizado automaticamente (versão N+1)
2. Delta-log registra campos alterados com justificativa em PT-BR
3. Context health atualizado (depth, confidence, quality)
4. Billing registra custo USD por chamada, visível no dashboard do projeto
5. Propagação regenera backlog seletivamente baseado nos campos alterados
6. Se IA indisponível, documento fica `ocg_pending` (OCG não corrompido)
7. `POST /ocg/propagate` permite re-disparo manual
8. `POST /ingestion/{doc_id}/release` libera quarentena e dispara OCG update
9. Histórico de versões e delta-log acessíveis via API

---

## Fora de Escopo (futuro)

- Dashboard frontend de billing (apenas API nesta iteração)
- Página frontend de OCG history/delta-log (apenas API)
- Budget alerts (ex: notificar quando projeto passar de X USD)
- Comparação visual entre versões do OCG
