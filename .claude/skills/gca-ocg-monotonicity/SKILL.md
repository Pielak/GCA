---
name: gca-ocg-monotonicity
description: Use ao tocar OCGUpdaterService, lógica de consolidação de scores, _load_persona_scores, _update_ocg_record, ocg_individual → pillars, ou em qualquer reporte de "OCG está caindo com novos documentos". Define o invariante canônico (§2.4 CLAUDE.md) "OCG só expande, nunca contrai por análise" e os 2 mecanismos que garantem ele em camadas (MAX-por-persona e guard universal no save). Único caminho legítimo de contração: REVERT_DOCUMENT_DELETE.
---

# Skill: Monotonicidade do OCG

> Esta skill existe porque a regra "OCG só expande" é fácil de falar e fácil de quebrar. O bug histórico (média simples diluindo) viveu meses sem ser pego — só veio à tona quando user reportou contração observável (overall caindo de 14.4 → 13.2 → 13.1 a cada novo doc ingerido). Há **2 camadas de defesa**; tocar qualquer uma exige entender as duas.

---

## 1. Invariante canônico (CLAUDE.md §2.4)

> "OCG só expande quando recebe informação de valor. **Nunca contrai por análise.** Ingestão ruim ou conflitante: documento vai para quarentena e não afeta o OCG."

**Três cenários permitidos:**
1. Score por pilar **sobe** quando doc novo traz evidência mais forte por persona.
2. Score por pilar **fica igual** quando doc novo é redundante.
3. Score por pilar **desce** **APENAS** quando `change_type='REVERT_DOCUMENT_DELETE'` (cascata MVP 34: GP soft-deletou um doc e o OCG precisa esquecer aquela evidência).

**Qualquer outra contração é bug.**

---

## 2. Camada 1 — `_load_persona_scores` (consolidação)

**Local**: `backend/app/services/ocg_updater_service.py`

Esta função roda quando o LLM updater não consegue consolidar e cai em fallback determinístico. **MAX por (pilar, persona) sobre todos os docs**, depois **média dos MAX** dentro de cada pilar.

```python
pillar_persona_max: dict[str, dict[str, float]] = {}
for row in rows:
    persona_tag_lower = (row.persona_id or "").lower()
    score = parecer.get("score", parecer.get("avg_score", 50))
    if persona_tag_lower not in PERSONA_TO_PILLAR:
        continue
    pillar_key = PERSONA_TO_PILLAR[persona_tag_lower]
    bucket = pillar_persona_max.setdefault(pillar_key, {})
    prev = bucket.get(persona_tag_lower)
    if prev is None or float(score) > prev:
        bucket[persona_tag_lower] = float(score)

result_data = {}
for pillar_key, persona_scores in pillar_persona_max.items():
    scores_list = list(persona_scores.values())
    avg = sum(scores_list) / len(scores_list)
    result_data[pillar_key] = {"score": round(avg, 1)}
```

**Por que é correto:**
- P5 (architecture) = ARQ + DEV. Doc1: ARQ=80, DEV=70. Doc2: ARQ=20, DEV=30.
- ARQ_max = 80 (do doc1, não regride). DEV_max = 70 (idem).
- p5 = média(80, 70) = 75.

**O bug histórico** (corrigido) era `pillar_scores.setdefault(pillar_key, []).append(score)` — empilhava todas as rows e fazia média:
- p5 = média(80, 70, 20, 30) = 50 ❌

---

## 3. Camada 2 — `_update_ocg_record` (guard universal no save)

**Local**: `backend/app/services/ocg_updater_service.py`

Defesa em camada — mesmo se o LLM updater retornar score menor (por hallucination, prompt mal formado, contexto truncado), o save bloqueia contração:

```python
is_revert = change_type == "REVERT_DOCUMENT_DELETE"
for n, col in _PILLAR_COLUMNS.items():
    score = _extract_pillar_score(pillars, n)
    if score is None:
        continue
    current = getattr(ocg, col, None)
    if (
        not is_revert
        and current is not None
        and float(score) < float(current)
    ):
        # Contração indevida — preserva o atual
        logger.info("ocg_updater.contraction_blocked",
                    project_id=str(ocg.project_id),
                    pillar=col, incoming=score, kept=current,
                    change_type=change_type)
        score = float(current)
        # Atualiza pillars dict pra coerência com COMPOSITE_SCORE
        key = _PILLAR_KEY_BY_NUM.get(n)
        if key and isinstance(pillars.get(key), dict):
            pillars[key]["score"] = score
    setattr(ocg, col, score)
    pillar_scores[n] = score
```

**Auditoria**: log estruturado `ocg_updater.contraction_blocked` toda vez que o guard age. Se aparecer com frequência → o LLM updater está degradando, investigar prompt.

---

## 4. Único caminho legítimo de contração

`change_type='REVERT_DOCUMENT_DELETE'` é o **único** valor que libera o guard. Caminho:

1. GP chama `DELETE /api/v1/projects/{pid}/ingestion/{did}?reason=manual` → soft-delete.
2. Celery `_revert_document_propagation_task` roda `DocumentRevertService.revert(doc_id)`.
3. `_recompute_ocg_from_remaining_individuals(project_id)` carrega `ocg_individual` JOIN `ingested_documents` filtrando `deleted_at IS NULL` → recalcula via `OCGUpdaterService._update_ocg_record(change_type='REVERT_DOCUMENT_DELETE')`.

Se o doc deletado era a única fonte do score alto de uma persona, o pilar **legitimamente** cai. Audit `DOCUMENT_REVERTED` no `audit_log_global` documenta a deleção.

Detalhe MVP 34: `docs/MVP_34_REVERT_DOCUMENT_DELETE.md` + skill `gca-ocg-engine`.

---

## 5. PERSONA_TO_PILLAR (mapa canônico)

```python
PERSONA_TO_PILLAR = {
    "gp":   "p1_business_score",
    "neg":  "p1_business_score",
    "conf": "p2_rules_score",     # bloqueante <60
    "lgpd": "p2_rules_score",
    "ux":   "p3_features_score",
    "ui":   "p3_features_score",
    "qa":   "p4_nfr_score",
    "arq":  "p5_architecture_score",
    "dev":  "p5_architecture_score",
    "dba":  "p6_data_score",
    "seg":  "p7_security_score",
    # AUD não mapeada — router/classificador, sem score próprio
}
```

P6 ou P7 zerados normalmente significam: persona DBA/SEG nunca emitiu `score>0` para nenhum doc. Causa comum: persona não recebeu contexto suficiente — ver `gca-n8n-workflow-mgmt §3` (`seed_shared_context` propagation) e CLAUDE.md §0.5 (Conjunto B).

---

## 6. Recompute manual sem rerodar personas

Operação útil quando bug do consolidador foi corrigido e quer aplicar nova consolidação aos `ocg_individual` existentes:

```python
# docker exec gca-backend python
import asyncio
from uuid import UUID
from app.db.database import AsyncSessionLocal
from app.services.ocg_updater_service import OCGUpdaterService

PROJECT_ID = UUID('<project_id>')

async def main():
    async with AsyncSessionLocal() as db:
        svc = OCGUpdaterService(db)
        scores = await svc._load_persona_scores(PROJECT_ID)
        ps = {
            'P1_business_case':  {'score': scores.get('p1_business_score', {}).get('score', 0)},
            'P2_rules':          {'score': scores.get('p2_rules_score', {}).get('score', 0)},
            'P3_features':       {'score': scores.get('p3_features_score', {}).get('score', 0)},
            'P4_nfr':            {'score': scores.get('p4_nfr_score', {}).get('score', 0)},
            'P5_architecture':   {'score': scores.get('p5_architecture_score', {}).get('score', 0)},
            'P6_data':           {'score': scores.get('p6_data_score', {}).get('score', 0)},
            'P7_security':       {'score': scores.get('p7_security_score', {}).get('score', 0)},
        }
        analysis = {'PILLAR_SCORES': ps, 'overall_score': scores.get('overall_score', 0),
                    'personas_executed': [], 'consolidated_findings': []}
        result = await svc.update_ocg_from_arguider(
            project_id=PROJECT_ID, arguider_analysis=analysis,
            trigger_source='manual_recompute_pillars',
        )
        print(result)

asyncio.run(main())
```

---

## 7. Diagnóstico de contração observada

Se user reportar "OCG está caindo":

1. Listar histórico via snapshots:
```sql
SELECT ocg_version_to,
       ocg_snapshot::jsonb->'PILLAR_SCORES' AS pillars,
       ocg_snapshot::jsonb->'overall_score' AS overall,
       source, persona_id, change_summary
FROM ocg_delta_log
WHERE project_id = '<pid>'
ORDER BY ocg_version_to DESC LIMIT 20;
```

2. Procurar:
   - Pilar caindo entre versões consecutivas com `source='document_ingestion'` → bug. Camada 1 ou 2 desativada/quebrada.
   - Caindo com `source='document_revert'` + `change_type='REVERT_DOCUMENT_DELETE'` → legítimo.
   - Logs `ocg_updater.contraction_blocked` aparecendo com frequência → LLM updater degradado, investigar.

3. Se confirmado bug: rodar **passo 1 (recompute)** acima — geralmente recupera scores diluídos pelo MAX-por-persona.

---

## 8. Pesos canônicos (composite)

```python
_PILLAR_WEIGHTS = {1: 0.10, 2: 0.15, 3: 0.20, 4: 0.20, 5: 0.15, 6: 0.10, 7: 0.10}
```

`overall_score` = média ponderada normalizada pelos pilares **presentes** (defesa contra OCG parcial). Em `governance_mode='solo_owner'`, P1 sai do denominador (`p1_excluded=true` em `COMPOSITE_SCORE`).

---

## 9. Referências cruzadas

- `gca-ocg-engine` — máquina de estado completa do OCG, propagação, backlog vivo.
- `gca-ingestion-pipeline-anatomy` — quem chama o updater (no `/ingestion-complete`).
- `gca-personas-engine` — Conjunto B + 12 personas + pesos no consolidador n8n.
- CLAUDE.md §2.4 — invariante canônico e cascata de revert.
- `docs/MVP_34_REVERT_DOCUMENT_DELETE.md` — único caminho legítimo de contração.
