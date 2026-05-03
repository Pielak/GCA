# MVP 33 — Expansão do PERSONA_TO_PILLAR para 12 personas LLM

**Status:** FECHADO 2026-05-02
**Branch:** `feat/mvp33-persona-pillar-expansion`
**Origem:** MVP 31 deixou explícito que SEG/CONF/LGPD/NEG/AUD não estavam mapeados; MVP 32 hot-fix DT-081 deixou comentário "MVP 33 vai expandir PERSONA_TO_PILLAR".

## Problema

Antes do MVP 33, `PERSONA_TO_PILLAR` em `ocg_consolidator_service.py` cobria apenas 7 das 12 personas LLM canônicas (Conjunto B do glossário §0.5):

```python
PERSONA_TO_PILLAR = {
    "gp": "p1_business_score",
    "arq": "p5_architecture_score",
    "dba": "p6_data_score",
    "dev": "p5_architecture_score",
    "qa": "p4_nfr_score",
    "ux": "p3_features_score",
    "ui": "p3_features_score",
}
```

Consequência prática no fallback `_load_persona_scores`:

- **SEG, CONF, LGPD, NEG** retornavam parecer com score válido mas eram silenciosamente descartadas no agregado (`if persona_tag_lower not in PERSONA_TO_PILLAR: continue`).
- **CONF**: score<60 emitia log `conf_blocking_score` (alerta independente do mapeamento), mas o score não influenciava nenhum pillar.
- **P2 (rules) e P7 (security)** ficavam sempre `None` quando o caminho de fallback era usado, mesmo com SEG/CONF/LGPD presentes em `ocg_individual`.

Resultado: o OCG cumulativo subnotificava conformidade regulatória e segurança quando o LLM falhava (caminho de fallback ativado).

## Decisão de mapeamento

| Persona LLM | → Pillar canônico | Justificativa |
|---|---|---|
| GP, NEG | P1 (business) | NEG soma valor estratégico/ROI ao GP |
| CONF, LGPD | P2 (rules) | Conformidade regulatória + LGPD são regras legais |
| UX, UI | P3 (features) | Mantido (legado) |
| QA | P4 (nfr) | Mantido (legado) |
| ARQ, DEV | P5 (architecture) | Mantido (legado) |
| DBA | P6 (data) | Mantido (legado) |
| SEG | P7 (security) | 1:1 óbvio — OWASP, AuthN/Z |
| AUD | (não mapear) | Router/classificador — sem score próprio |

**Cobertura final:** 11 personas → 7 pillars. AUD permanece skipped (intencional).

**Trade-off LGPD em P2 vs P7:** LGPD tem componente técnico-segurança (criptografia em repouso, controle de acesso) e componente regulatório (base legal, consentimento, retenção). Optei por P2 (rules) porque o foco da persona LGPD é a aderência regulatória, não o controle técnico — esse último é da SEG. Quem controla técnica = SEG/P7; quem controla legalidade = LGPD/P2.

## Mudanças

### `backend/app/services/ocg_consolidator_service.py`
- `PERSONA_TO_PILLAR` expandido de 7 para 11 entradas.
- Comentário cabeçalho documenta cobertura canônica e exceção AUD.

### `backend/app/services/ocg_updater_service.py`
- Comentários "MVP 33 vai mapear/expandir" removidos (eram TODO refs ao próprio MVP 33).
- Comentário em `_load_persona_scores` esclarece que apenas AUD fica de fora.

### `backend/app/tests/test_mvp33_persona_pillar_expansion.py` (novo)
10 testes:
- Mapping puro: 4 personas novas, AUD fora, não-regressão das 7 antigas, contagem 11, cobertura de todos os 7 pillars.
- Fallback `_load_persona_scores`: SEG→P7, CONF+LGPD→P2 (média), NEG+GP→P1 (média), AUD ignorado, cenário canônico 11 personas → 7 pillars.

## Validação

```
$ pytest app/tests/test_mvp33_persona_pillar_expansion.py \
        app/tests/test_mvp32_ocg_updater_dt081.py \
        app/tests/test_mvp32_fix_parse_fallback.py -v
34 passed
```

- 10/10 MVP 33 ✅
- 18/18 MVP 32 não-regressão ✅
- 6/6 hot-fix DT-081 não-regressão ✅

E2E real (DeepSeek) **não foi re-executado neste MVP** porque MVP 33 não muda control flow — apenas amplia o conjunto de personas que vão para a média. Caminho de fallback foi validado E2E real no MVP 32 hot-fix (commit `215c31a`); MVP 33 herda essa validação.

## Dívidas registradas

### DT-084 — Suite de testes legado com falhas pré-existentes
Identificadas 5 falhas em master (independentes do MVP 33):
- `test_persona_evaluation.py` (3 testes): erro SQL em `gatekeeper_persona_responses` — provavelmente schema desalinhado com factories.
- `test_mvp10_fase107_live_docs.py::test_module_doc_provenance_inclui_ocg_llm_hash`.
- `test_parallel_evaluator.py::test_parallel_evaluator_passada_1_with_multiple_personas`: `MagicMock can't be used in 'await' expression`.

Adicionalmente, 4 arquivos com erro de import (`ImportError: cannot import name 'SessionLocal'`):
- `test_phase_b3_integration.py`, `test_fase1_auditor_orchestrator.py`, `test_mvp10_fase102_spec_generator.py`, `test_mvp9_fase92_module_details.py`.

**Nada disso bloqueia MVP 33** — testes do MVP 33 e os MVPs 31/32 vizinhos estão verdes. Endereçamento separado em MVP futuro de cleanup.

## Métricas

| Item | Valor |
|---|---|
| Esforço real | ~1h |
| LOC adicionado | +192 (test) +20 (mapping doc) |
| LOC removido | -5 (comentários "MVP 33 vai...") |
| Testes novos | 10 |
| Não-regressão validada | 24 (18 MVP 32 + 6 hot-fix) |
| Schema afetado | 0 (apenas dict Python) |
| Migration | nenhuma |
