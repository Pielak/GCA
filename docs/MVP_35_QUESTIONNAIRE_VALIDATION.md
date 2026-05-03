# MVP 35 — Validação canônica do Questionário Técnico

**Status:** DEFINIDO 2026-05-03 — aguardando Gate 1.
**Branch:** `feat/mvp35-questionnaire-validation`
**Origem:** GP identificou 4 lacunas no fluxo Salvar/Validar/Submeter + necessidade de validação técnica de itens (combos válidos/inválidos) + validação cruzada entre respostas + UI inline com sugestões + Q13 multi-select com "outros".

## Decisões binárias (autorizadas pelo GP)

1. **Estado canônico** — enum `draft → validated → submitted`. Submeter exige `validated`.
2. **Submit cria `IngestedDocument`** tipo `questionnaire` — aparece na aba Ingestão.
3. **Ordem dos gates UX-guiada** — frontend libera aba Questionário só após repo+LLM ok.
4. **Validar obrigatório** — botão Submeter desabilitado se nunca validou OU validação falhou.

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

## 5 fases (~2d)

| Fase | Esforço | Entregável |
|---|---|---|
| 35.1 | 0.5d | DSL rules schema + 30 regras seed (catálogo FE×BE×DB) + engine `RulesEvaluator` + testes unit |
| 35.2 | 0.5d | Migration: estado `validated` no enum status. Endpoint `validate-field`. Refactor save: status nunca regride sem flag. |
| 35.3 | 0.5d | Frontend: validate-on-blur + UI inline (warning amarelo + dropdown sugestões). Botão Submeter desabilitado sem `validated`. |
| 35.4 | 0.25d | Q13 multi_select_with_other no schema + UI checkbox + outros field. Validar Q15 (LGPD) tem mesmo padrão. |
| 35.5 | 0.25d | Camada 2 LLM no submit. `IngestedDocument` tipo questionnaire criado. Testes + smoke E2E. |

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

## Próxima ação

Gate 1 (gerente-projetos-ti).
