# MVP 32 — DT-081: OCG Updater funcional com payload n8n

**Status:** Aprovado com ressalvas pelo Gate 1 (gerente-projetos-ti, 2026-05-02)
**Pré-requisito:** MVP 31 mergeado em master (commit `41b6f3a`)
**Branch:** `feat/mvp32-dt081-updater-funcional`

---

## 1. Problema canônico

MVP 31 entregou a arquitetura cumulativa do OCG, mas em smoke E2E real descobriu-se que **o OCG nunca acumula em produção**:

1. **Bug LLM**: DeepSeek com prompt de ~23KB do payload n8n (9 personas + findings) retorna JSON sem `updated_ocg`/`changes` válidos.
2. **Bug fallback**: `OCGUpdaterService._load_persona_scores` (linha ~664) quebra com `AttributeError: type object 'DocumentRouteMap' has no attribute 'project_id'`. JOIN inválido — `DocumentRouteMap` não tem essa coluna.

**Efeito**: `ocg.status='ocg_pending'` para sempre, `ocg_delta_log` vazio, OCG nunca amadurece, CodeGen sempre bloqueado por `immature` (gate do MVP 31).

## 2. Objetivo

Sem refator amplo do `OCGUpdaterService`, fechar os 2 bugs para que pipeline n8n + handler + updater + delta_log funcionem ponta-a-ponta. OCG cresce monotonicamente conforme docs são ingeridos.

## 3. Invariantes preservadas (não negociáveis)

1. OCG só cresce (`_filter_negative_score_deltas` intocado)
2. Versionamento + hash chain em `ocg_delta_log` intactos
3. Política de criticidade alta para OCG update (Anthropic/OpenAI premium recomendado, DeepSeek com warning aceito)
4. Pipeline n8n permanece intocado
5. Modelos `OCGIndividual`/`OCGGlobal` do MVP 31 são reusados (sem nova migration)
6. Findings com `criticidade='critica'` ou CONF score<60 **nunca descartados** no truncamento de prompt (MUST do Gate 1)

## 4. Não-objetivos

- Refactor amplo do `OCGUpdaterService` (mantém estrutura, só conserta os 2 pontos)
- DT-079 (hardcode Anthropic em CodeGen) — fica para MVP 33
- DT-080 (ORM stubs filhas completos) — só faz sentido com HITL ativo
- DT-082 (defesa em profundidade Celery) — Minor, baixa prioridade
- DT-083 (Prometheus) — depende de instrumentação base do `metrics_service`
- Mudança de schema (não há)

## 5. Faseamento (3 fases — agile)

### Fase 32.1 — Reescrever `_load_persona_scores` para usar `OCGIndividual` (~0.5d)

**Problema atual** (`ocg_updater_service.py:650-720`):
```python
from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
from app.models.document_route_map import DocumentRouteMap

stmt = select(GatekeeperPersonaResponse).join(
    DocumentRouteMap,
    GatekeeperPersonaResponse.route_map_id == DocumentRouteMap.id,
).where(
    DocumentRouteMap.project_id == project_id,  # <-- AttributeError
)
```

**Substituição**:
```python
from app.models.base import OCGIndividual

# Lê todos os pareceres válidos (status='completed') de todas as ingestões do projeto
stmt = (
    select(OCGIndividual)
    .where(OCGIndividual.project_id == project_id)
    .where(OCGIndividual.status == 'completed')  # exclui personas falhas
    .order_by(OCGIndividual.created_at.desc())
)
```

Mapeamento `persona_id` (tag) → pillar continua via `PERSONA_TO_PILLAR` em `ocg_consolidator_service.py`.

Score por pillar continua sendo média dos scores das personas que contribuem para ele. Mas `OCGIndividual.parecer` é JSONB com formato persona-específico (não tem `scores` direto como `GatekeeperPersonaResponse`). Precisa derivar score do `parecer.score` (singular, do PersonaOutput-v2 do MVP 31).

**MUST do Gate 1**:
- Adicionar log estruturado `ocg_updater.no_ocg_individual_rows` (distinto de `no_persona_scores`) quando projeto não tem rows em `ocg_individual` — distingue "n8n não rodou" de "bug".

**Critério de aceite**:
- Grep confirma: `_load_persona_scores` não importa nem referencia `DocumentRouteMap`
- Smoke unit: projeto com 9 rows em `ocg_individual` → fallback retorna pillar_scores não-vazio
- Projeto sem rows em `ocg_individual` → fallback retorna `{}`, log `no_ocg_individual_rows` emitido

### Fase 32.2 — Tuning do `_build_user_prompt` para payload n8n (~1d)

**Problema atual** (`ocg_updater_service.py:959-985`):
```python
def _build_user_prompt(self, current_ocg, arguider_analysis):
    return f"""
OCG ATUAL: {json.dumps(current_ocg)}
ANÁLISE DO ARGUIDOR: {json.dumps(arguider_analysis)}  # 23KB do n8n
...
"""
```

LLM se perde com 23KB. Precisa truncar/sumarizar inteligentemente.

**Estratégia**:
1. **Detectar fonte**: se `arguider_analysis` tem `personas_executed` (formato n8n) vs estrutura antiga do Arguidor → ramificar formatação.
2. **Truncar `consolidated_findings`** para top-K (K=20):
   - Critério: `criticidade='critica'` primeiro, depois `criticidade='alta'`, etc.
   - **Findings de CONF com score<60 SEMPRE incluídos** (MUST do Gate 1, regra de bloqueio)
3. **Sumarizar `ocg_individual`**: para cada persona, manter apenas `score`, `approved`, `blocking`, `findings_count`. Descartar `recommendations` longas e `metadata`.
4. **Manter `ocg_global_delta` integral** (já vem agregado pelo consolidador, tamanho gerenciável).

**Critério de aceite**:
- Prompt resultante < 8KB (cabe no contexto efetivo do DeepSeek com folga)
- DeepSeek retorna JSON com `updated_ocg` + `changes` válidos no smoke E2E real
- Findings críticos (criticidade='critica' ou CONF<60) presentes no prompt — verificar via log de debug
- SHOULD: system prompt instrui explicitamente que CONF score<60 implica `change_type='CONTRACT'` (reduz dependência do LLM "descobrir" a regra)

### Fase 32.3 — Testes E2E reais (sem mock LLM) + doc (~1d)

**Entrega**:

1. Teste unit: `backend/app/tests/test_mvp32_ocg_updater_dt081.py`:
   - `test_load_persona_scores_uses_ocg_individual` — fallback lê de `ocg_individual` corretamente
   - `test_load_persona_scores_returns_empty_when_no_rows` — log `no_ocg_individual_rows`
   - `test_documentroutemap_no_longer_referenced` — grep no código fonte
   - `test_critical_findings_never_truncated` — top-K preserva criticidade='critica' e CONF<60
   - `test_attributeerror_documentroutemap_regression` — guard contra reintrodução do bug

2. Teste E2E real (sem mock DeepSeek) `backend/app/tests/test_mvp32_e2e_real_llm.py` — **opt-in via env var** `MVP32_REAL_LLM=1` (custo de tokens ~R$0,05):
   - Smoke E2E real com 1 doc → assert `ocg.status='active'`, `ocg.version > previous`, `ocg_delta_log` ganha row com `trigger_source='document_ingestion_n8n'` E delta com `op` válido
   - Smoke 3 docs sequenciais → version cresce monotonicamente

3. Atualizações de doc:
   - `docs/n8n-pipeline/PIPELINE_OPERACIONAL.md §6` — DT-081 marcada como **RESOLVIDA pelo MVP 32**
   - `GCA_MVP_PROGRESS.md §3.2` DT-081 → **Quitada 2026-05-02 (MVP 32)** com referência ao commit
   - `docs/MVP_31_OCG_CUMULATIVO_PLAN.md §15` — atualizar status DT-081 como resolvida
   - `CHANGELOG.md` — entry MVP 32

**Critério de aceite**:
- Suíte MVP 32: testes unit verdes
- Smoke E2E opt-in passa quando rodado (custo controlado)
- Não-regressão: 35/35 testes MVP 31 mantidos verdes
- Doc canônico atualizado

## 6. Estimativa total

**~2-3 dias** (1 sprint pequeno, mas mais 0.5d se o tuning de prompt exigir iteração).

## 7. Gates Gatekeeper

| Gate | Persona | Status |
|---|---|---|
| 1 | gerente-projetos-ti | ✅ Aprovado com ressalvas (3 MUSTs) |
| 2 | arquiteto-projetos | ✅ Aprovado com ressalvas (2026-05-02) |
| 3 | dba | ✅ Pulado (confirmado pelo Arquiteto — sem mudança de schema) |
| 4 | dev-senior | ✅ Concluído (commits `506e1c0` + `80851d3` + este) |
| 5 | tester-qa | ✅ Aprovado — 53/53 verdes (fases 32.1+32.2) |
| skill `preparar-release` | — | Pendente |

## 8. Refinamentos do Gate 1 (aplicados em 2026-05-02)

**MUSTs aplicados ao plano:**
1. Fase 32.2 incorpora critério de prioridade no truncamento (criticidade='critica' + CONF<60 nunca descartados)
2. Fase 32.3 inclui assertion explícita de remoção de `DocumentRouteMap` (grep + teste)
3. Fase 32.1 adiciona log distinto `no_ocg_individual_rows` para distinguir "n8n não rodou" de "bug"

**SHOULDs registrados (avaliar durante implementação):**
1. System prompt instruir explicitamente regra CONF<60 → `change_type=CONTRACT`
2. Smoke E2E verifica conteúdo do delta (não apenas existência da row)
3. Teste de regressão específico contra reintrodução do `AttributeError DocumentRouteMap`

## 9. Riscos identificados (Gate 1)

| # | Risco | Probabilidade | Mitigação |
|---|---|---|---|
| R1 | Fallback novo retorna vazio se n8n não rodou (projeto novo) — OCG fica em ocg_pending por razão diferente | Baixa | Log distinto `no_ocg_individual_rows` permite diagnóstico |
| R2 | Truncamento de findings descarta criticidade='critica' inadvertidamente | Média | Critério de prioridade obrigatório (MUST do Gate 1) |
| R3 | `OCGIndividual.parecer` (JSONB persona-específico) não bate com formato esperado pelo prompt | Média | Sumarização extrai apenas score/approved/blocking/findings_count — formato uniforme |
| R4 | Custo de tokens em teste E2E real | Baixa | Opt-in via env var `MVP32_REAL_LLM=1`, custo total ~R$0,05 |

## 10. Refinamentos do Gate 2 (aplicados em 2026-05-02)

Veredito: **Aprovado com ressalvas** (arquiteto-projetos, 2026-05-02). Decisões críticas:

1. **R-CRÍTICO detectado e endossado como MUST**: `PERSONA_TO_PILLAR` em `ocg_consolidator_service.py:25-33` usa tags **lowercase** (`"gp"`, `"arq"`) com 7 entradas legacy. `OCGIndividual.persona_id` armazena **uppercase** (`"GP"`, `"ARQ"`) com 12 personas. Sem normalização, fallback retorna `{}` silenciosamente. **Fix obrigatório**: normalizar `persona_tag.lower()` antes do lookup em `_load_persona_scores`.
2. **`arguider_compactor.py` como módulo separado** (não inline): seguir convenção do `ocg_compactor.compact_ocg_for_prompt` existente. Função `compact_arguider_for_prompt(arguider_analysis, max_findings=20)` com critério de prioridade.
3. **Log distinto `ocg_updater.conf_blocking_score`** quando fallback encontrar CONF score<60 — alinhado com §6.2 do contrato.
4. **`PERSONA_TO_PILLAR` tem só 7 entradas** — 5 personas novas (SEG, CONF, LGPD, NEG, AUD) sem mapeamento. Aceitável para MVP 32 com documentação explícita; expansão fica para MVP 33.
5. **Acoplamento updater↔ocg_individual aprovado**: ambos GCA-domain, fluxo unidirecional `n8n → ocg_individual → updater → ocg`. Sem ciclo. Fallback dual (`ocg_individual` + `gatekeeper_persona_responses`) **NÃO** recomendado — manutenção paralela infinita.
6. **Gate 3 (DBA) PULADO**: confirmado pelo Arquiteto. Sem mudança de schema, sem nova migration, sem query nova de escrita.

## 11. Próximo passo

**Gate 4 — Dev Sênior** com mandato específico:

1. Implementar `_load_persona_scores` com query em `ocg_individual` + normalização `persona_tag.lower()` antes do lookup em `PERSONA_TO_PILLAR` (MUST).
2. Criar `backend/app/services/arguider_compactor.py` seguindo padrão do `ocg_compactor.py`. Função `compact_arguider_for_prompt(arguider_analysis, max_findings=20)`. Critério de prioridade por `criticidade` — `criticidade='critica'` e CONF `score<60` imunes ao corte (MUST).
3. Refatorar `_build_user_prompt` para chamar `compact_arguider_for_prompt` antes de serializar (não implementar truncamento inline).
4. Adicionar log `ocg_updater.conf_blocking_score` quando fallback detectar CONF score<60.
5. Testes conforme §5 Fase 32.3 + caso adicional de normalização de case + caso de CONF imune ao corte.

> ✅ **Gate 4 concluído** — todos os itens acima implementados nos commits `506e1c0` + `80851d3`. Fase 32.3 encerra o MVP 32.

---

## 12. Status final (2026-05-02)

MVP 32 entregue:
- Fase 32.1 ✓ (commit `506e1c0`) — `_load_persona_scores` reescrito com OCGIndividual
- Fase 32.2 ✓ (commit `506e1c0` + `80851d3`) — `arguider_compactor.py` + tuning
- Fase 32.3 ✓ (este commit) — testes E2E reais opt-in + doc final

Métricas:
- 18/18 testes unit verdes (MVP 32)
- 53/53 com não-regressão MVP 31
- 1 teste E2E real (`MVP32_REAL_LLM=1`, custo ~R$0,05)
- Compactor: 217KB → 7.8KB (96.4% redução)

Próximo: skill `preparar-release`.
