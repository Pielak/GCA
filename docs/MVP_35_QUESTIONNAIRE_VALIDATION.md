# MVP 35 — Validação canônica do Questionário Técnico

**Status:** DEFINIDO 2026-05-03 — aguardando Gate 1.
**Branch:** `feat/mvp35-questionnaire-validation`
**Origem:** GP identificou 4 lacunas no fluxo Salvar/Validar/Submeter + necessidade de validação técnica de itens (combos válidos/inválidos) + validação cruzada entre respostas + UI inline com sugestões + Q13 multi-select com "outros".

## Decisões binárias (autorizadas pelo GP)

1. **Estado canônico** — enum `draft → validated → submitted`. Submeter exige `validated`.
2. **Submit cria `IngestedDocument`** tipo `questionnaire` — aparece na aba Ingestão.
3. **Ordem dos gates UX-guiada** — frontend libera aba Questionário só após repo+LLM ok.
4. **Validar obrigatório** — botão Submeter desabilitado se nunca validou OU validação falhou.
5. **Deletar questionário na Ingestão = volta a fase configuração** (decisão GP 2026-05-03 pós-confirmação inicial). Quando GP soft-deleta `IngestedDocument` tipo `questionnaire`:
   - `TechnicalQuestionnaire.status` reverte de `submitted` → `archived` (não `draft` — preserva histórico, força novo)
   - `Questionnaire.approved` → `False` (FK do OCG marcada como não-aprovada)
   - `_check_setup_status.questionnaire_submitted` → `False`
   - `_check_setup_status.ready_to_activate` → `False`
   - Projeto volta a fase configuração: setup checklist mostra Questionário como pendente
   - Frontend redireciona próxima sessão para `/projects/{id}/settings?tab=questionario` com novo questionário em branco (não recupera o archived)
   - Pipeline n8n bloqueado até novo questionário submetido
   - Cascata canônica via DocumentRevertService (MVP 34) — não duplica lógica

## Approach de validação (autorizado)

**Híbrido em 2 camadas:**

### Camada 1 — Regras determinísticas (DSL JSON)
- Catálogo seed ~30 regras cobre matriz comum FE×BE×DB×infra×compliance.
- Engine `evaluate_rules(responses) → {conflicts[], warnings[], suggestions[]}` < 10ms.
- Espelhada frontend (TS) + backend (Python). Backend é fonte de verdade.
- Inline: validate-on-blur por campo modificado.

### Camada 2 — LLM como sanity check
- Roda 1× no submit final. Provider via `AIKeyResolver` (já configurado).
- Prompt: detectar incoerências técnicas que regras determinísticas não pegam.
- Custo: ~R$0.001/submit (DeepSeek). Latência aceitável (não-inline).

## 6 fases (~2.5d)

| Fase | Esforço | Entregável |
|---|---|---|
| 35.1 | 0.5d | DSL rules schema + 30 regras seed (catálogo FE×BE×DB) + engine `RulesEvaluator` + testes unit |
| 35.2 | 0.5d | Migration: estado `validated` no enum status. Endpoint `validate-field`. Refactor save: status nunca regride sem flag. |
| 35.3 | 0.5d | Frontend: validate-on-blur + UI inline (warning amarelo + dropdown sugestões). Botão Submeter desabilitado sem `validated`. |
| 35.4 | 0.25d | Q13 multi_select_with_other no schema + UI checkbox + outros field. Validar Q15 (LGPD) tem mesmo padrão. |
| 35.5 | 0.25d | Camada 2 LLM no submit. `IngestedDocument` tipo questionnaire criado. |
| 35.6 | 0.5d | Hook `DocumentRevertService` para tipo `questionnaire`: archive TechnicalQuestionnaire + mark Questionnaire.approved=False. Backend gate retorna `ready_to_activate=False`. Frontend redirect setup. Smoke E2E real (delete questionnaire → projeto volta a setup). |

## Schema regras DSL

```python
{
  "id": "RULE_DB_NOSQL_TRANSACTION",  # ID canônico
  "when": {                            # condições AND
    "Q9": "mongodb",
    "Q14_contains": "transaction_acid"
  },
  "verdict": "conflict",               # ok | warning | conflict
  "severity": "error",                 # info | warning | error
  "message": "MongoDB não garante ACID multi-doc...",
  "suggestions": ["postgres", "cockroachdb"]  # opções alternativas
}
```

## Não-objetivos

- Não reescreve `TECHNICAL_QUESTIONS_SCHEMA` (só estende Q13/Q15).
- Não muda fluxo de personas Celery após submit (mantém comportamento atual).
- Não bloqueia repo/LLM gates pré-existentes.
- Não cobre validação semântica de texto livre (futuro MVP).

## Critério de aceite (testável)

1. ✅ Status enum aceita `validated`
2. ✅ `POST /technical-questionnaire/validate-field?field=Qx` retorna `{conflicts, warnings, suggestions}` < 50ms
3. ✅ 30 regras seed catalogadas + 30/30 testes verdes
4. ✅ Botão Submeter desabilitado quando `status != 'validated'` ou `conflicts > 0`
5. ✅ Q13 renderiza checkbox + textarea quando "Outros" marcado
6. ✅ Submit cria `IngestedDocument` tipo questionnaire (visível na aba Ingestão)
7. ✅ LLM camada 2 chamado 1× no submit, payload coerente
8. ✅ Suite ampla 0 regressão
9. ✅ Smoke E2E real: GP preenche AJA → Validar → conflito mock → corrige → Validar OK → Submete → status `submitted` + IngestedDocument criado
10. ✅ Delete IngestedDocument tipo questionnaire → TechnicalQuestionnaire `archived` + Questionnaire.approved=False + setup_status.ready_to_activate=False
11. ✅ Smoke E2E real revert: deletar questionnaire do AJA → consultar setup-status → ready_to_activate=False + questionnaire_submitted=False
12. ✅ Frontend redireciona para `/settings?tab=questionario` quando ready_to_activate=False após delete questionnaire

## Próxima ação

Gate 1 (gerente-projetos-ti).
