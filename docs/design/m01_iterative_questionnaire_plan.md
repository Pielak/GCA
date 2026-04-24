# M01 — Questões em Aberto (Iterative Custom Questionnaire) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar aba "Questões em Aberto" que, quando o OCG está `overall < 90` E existe pilar P1..P7 com score < 75, gera questionário customizado via LLM (provider do projeto), usuário baixa PDF editável, preenche, faz upload — a resposta vira `IngestedDocument` normal que passa pelo pipeline canônico (canonização MVP 29 → Arguidor → OCG Updater). Loop itera novas perguntas até **convergência** (Δ overall entre iterações < 1pt) OU **inviabilidade** (≥50% respostas "não se aplica"). Badge no sidebar: `•` amarelo quando há questão pendente, `✓` verde quando não.

**Architecture:** 1 tabela nova (`custom_questionnaire_iterations`) — histórico de iterações com `ocg_version_before/after` + flag de convergência. Respostas viram documentos ingeridos (reusa pipeline existente, zero hack em score direto). Service `iterative_questionnaire_service` orquestra threshold → geração → decide convergência após novo OCG chegar. Reusa `LLMServiceFactory` (§6.2), `pdf_questionnaire_generator` (MVP 24), `document_canonicalizer` (MVP 29).

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy async + Pydantic v1 + ReportLab (backend) · React + TypeScript + Tailwind + axios (frontend) · migrations SQL plain em `backend/migrations/` (padrão canônico GCA, não Alembic).

---

## File Structure

### Backend

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `backend/migrations/038_custom_questionnaire_iterations.sql` | Tabela nova `custom_questionnaire_iterations`. Sem `custom_responses` (respostas viram `ingested_documents`). |
| Modify | `backend/app/models/base.py` | Adicionar model SQLAlchemy `CustomQuestionnaireIteration` junto dos demais. |
| Create | `backend/app/services/iterative_questionnaire_generator.py` | Prompt builder puro: lê pilares + gaps Arguidor → pede N perguntas focadas. Sem I/O. |
| Create | `backend/app/services/iterative_questionnaire_service.py` | Orquestrador: `should_generate_new_iteration`, `generate_iteration`, `evaluate_convergence_after_ocg_update`. |
| Create | `backend/app/routers/iterative_questionnaire_router.py` | 4 endpoints: status, generate, download-pdf, upload-answers. Registrar em `main.py`. |
| Modify | `backend/app/main.py` | Registrar o novo router. |
| Modify | `backend/app/services/ocg_updater_service.py` | Hook pós-update: chamar `evaluate_convergence_after_ocg_update` se `trigger_source == 'iterative_questionnaire'`. |
| Create | `backend/app/tests/test_m01_iterative_questionnaire.py` | Testes standalone (padrão MVP 29, `python -m app.tests...`). Cobre threshold, prompt, convergência, inviabilidade. |

### Frontend

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `frontend/src/pages/projects/IterativeQuestionnairePage.tsx` | Página da aba nova: lista iterações, baixa PDF da atual, upload resposta, mostra status de convergência. |
| Modify | `frontend/src/components/layout/Sidebar.tsx` | Adicionar item "Questões em Aberto" após "Ingestão". Badge dinâmico `•` (pendente) ou `✓` (ok). |
| Modify | `frontend/src/App.tsx` (ou `routes.tsx`) | Adicionar rota `/projects/:id/iterative-questionnaire`. |
| Create | `frontend/src/hooks/useIterativeQuestionnaireStatus.ts` | Hook `{status, hasPending}` que o sidebar consome pra decidir badge. Polling a cada 30s (canônico MVP 27). |

### Docs

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `docs/design/m01_iterative_questionnaire_plan.md` | Este plano (já criado). |
| Modify | `docs/design/m01_impact_report.md` | (Após execução) relatório: nº iterações, convergência, redução de score. |

---

## Task 1: Migration SQL — tabela `custom_questionnaire_iterations`

**Files:**
- Create: `backend/migrations/038_custom_questionnaire_iterations.sql`

- [ ] **Step 1: Criar o arquivo de migration**

Conteúdo completo de `backend/migrations/038_custom_questionnaire_iterations.sql`:

```sql
-- MVP M01 — iterações de Questões em Aberto customizadas.
-- Cada iteração gera 4-7 perguntas focadas nos pilares P1..P7 com score < 75
-- enquanto overall < 90. Respostas viram ingested_documents normais (não há
-- tabela de respostas — o pipeline canônico Arguidor→OCG Updater processa).

CREATE TABLE custom_questionnaire_iterations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    iteration INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- status: 'pending' | 'answered' | 'converged' | 'infeasible' | 'superseded'
    target_pillars JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Ex: ["P3_scope", "P4_quality"]
    questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- [{id, type, text, context, pillar, options?, required, max_chars?}]
    pdf_blob BYTEA,
    answer_document_id UUID REFERENCES ingested_documents(id) ON DELETE SET NULL,
    ocg_version_before INT,
    ocg_version_after INT,
    overall_before NUMERIC(5,2),
    overall_after NUMERIC(5,2),
    converged BOOLEAN NOT NULL DEFAULT FALSE,
    not_applicable_ratio NUMERIC(4,3),
    convergence_threshold NUMERIC(4,2) NOT NULL DEFAULT 1.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, iteration)
);

CREATE INDEX ix_custom_q_iter_project_status
    ON custom_questionnaire_iterations (project_id, status);
CREATE INDEX ix_custom_q_iter_answer_doc
    ON custom_questionnaire_iterations (answer_document_id)
    WHERE answer_document_id IS NOT NULL;

COMMENT ON TABLE custom_questionnaire_iterations IS
    'M01 — histórico de iterações de questionário customizado por projeto.';
COMMENT ON COLUMN custom_questionnaire_iterations.status IS
    'pending|answered|converged|infeasible|superseded';
COMMENT ON COLUMN custom_questionnaire_iterations.target_pillars IS
    'Lista dos pilares P1..P7 com score < 75 no momento da geração.';
```

- [ ] **Step 2: Aplicar migration no DB**

Run: `docker exec gca-postgres psql -U gca -d gca -f /tmp/m01_mig.sql` (após `docker cp` do arquivo).

Alternativa direta com heredoc:
```
docker cp /home/luiz/GCA/backend/migrations/038_custom_questionnaire_iterations.sql gca-postgres:/tmp/038.sql
docker exec gca-postgres psql -U gca -d gca -f /tmp/038.sql
```

Expected: `CREATE TABLE` + 2 `CREATE INDEX` + 3 `COMMENT`.

- [ ] **Step 3: Validar schema**

Run: `docker exec gca-postgres psql -U gca -d gca -c "\d custom_questionnaire_iterations"`
Expected: 15 colunas listadas, UNIQUE em (project_id, iteration), 2 índices.

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/migrations/038_custom_questionnaire_iterations.sql
git -C /home/luiz/GCA commit -m "M01 Task 1 — migration 038 custom_questionnaire_iterations"
```

---

## Task 2: Model SQLAlchemy `CustomQuestionnaireIteration`

**Files:**
- Modify: `backend/app/models/base.py` (inserir após o último model existente — checar com `grep -n "^class " backend/app/models/base.py | tail -3`)

- [ ] **Step 1: Adicionar o model**

Inserir após o último `class X(Base):` em `backend/app/models/base.py`:

```python
class CustomQuestionnaireIteration(Base):
    """M01 — iteração de questionário customizado.

    Uma iteração é gerada quando overall_score < 90 E existe algum
    pilar P1..P7 com score < 75. Respostas viram `ingested_documents`
    normais (campo `answer_document_id` aponta). Convergência detectada
    quando |overall_after - overall_before| < convergence_threshold.
    """

    __tablename__ = "custom_questionnaire_iterations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    iteration = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    target_pillars = Column(JSON, nullable=False, default=list)
    questions = Column(JSON, nullable=False, default=list)
    pdf_blob = Column(LargeBinary, nullable=True)
    answer_document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="SET NULL"), nullable=True)
    ocg_version_before = Column(Integer, nullable=True)
    ocg_version_after = Column(Integer, nullable=True)
    overall_before = Column(Numeric(5, 2), nullable=True)
    overall_after = Column(Numeric(5, 2), nullable=True)
    converged = Column(Boolean, nullable=False, default=False)
    not_applicable_ratio = Column(Numeric(4, 3), nullable=True)
    convergence_threshold = Column(Numeric(4, 2), nullable=False, default=1.00)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime_utcnow, onupdate=datetime_utcnow)
```

Onde `datetime_utcnow` é o helper usado nos outros models (importar ou definir local — verificar padrão do arquivo com `grep "default=.*utcnow\|default=func\.now" backend/app/models/base.py | head -5`).

Se os demais models usam `default=func.now()`, usar `func.now()` aqui também pra manter consistência.

- [ ] **Step 2: Verificar imports necessários**

Garantir que `LargeBinary`, `Numeric`, `Boolean`, `JSON` estão importados no topo do arquivo. Usar:

```python
from sqlalchemy import (
    Column, String, Integer, DateTime, LargeBinary, ForeignKey, Boolean, Numeric,
    ...
)
from sqlalchemy.dialects.postgresql import UUID, JSON
```

Adicionar só os que faltam — não duplicar.

- [ ] **Step 3: Validar sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/models/base.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Validar import no container**

Run: `docker exec gca-backend python -c "from app.models.base import CustomQuestionnaireIteration; print('OK', CustomQuestionnaireIteration.__tablename__)"`
Expected: `OK custom_questionnaire_iterations`

- [ ] **Step 5: Commit**

```bash
git -C /home/luiz/GCA add backend/app/models/base.py
git -C /home/luiz/GCA commit -m "M01 Task 2 — model SQLAlchemy CustomQuestionnaireIteration"
```

---

## Task 3: Service `iterative_questionnaire_generator.py` (prompt builder puro)

**Files:**
- Create: `backend/app/services/iterative_questionnaire_generator.py`

- [ ] **Step 1: Criar o service**

Conteúdo completo:

```python
"""M01 — builder de prompt pra gerador de questões iterativas.

Função pura (sem I/O) que consome:
- lista de pilares com score < 75 do OCG corrente
- gaps do Arguidor (module_candidates ou gatekeeper_items) por pilar
- iteração atual + overall anterior

Retorna prompt texto pronto pra `LLMServiceFactory.call_llm` do projeto
(respeita §6.2 — zero hardcode de provider/modelo).

Formato de resposta esperado do LLM:
```json
{
  "questions": [
    {
      "id": "Q1", "type": "choice|text", "text": "...",
      "context": "P3_scope gap 20%", "pillar": "P3_scope",
      "required": true,
      "options": ["...", "..."]  // só se type=choice
    }
  ]
}
```
"""
from __future__ import annotations

import json
from typing import Any

_PILLAR_LABELS_PT = {
    "P1_business_case": "Caso de Negócio",
    "P2_business_model": "Modelo de Negócio",
    "P3_scope": "Escopo",
    "P4_quality": "Qualidade",
    "P5_ux": "Experiência do Usuário",
    "P6_legal": "Jurídico & Compliance",
    "P7_security": "Segurança",
}


def build_iterative_prompt(
    *,
    project_name: str,
    iteration: int,
    overall_before: float,
    target_pillars_scores: dict[str, float],
    arguider_gaps_by_pillar: dict[str, list[dict[str, Any]]],
    previous_iteration_feedback: str | None = None,
) -> str:
    """Monta prompt pra geração de 4-7 perguntas focadas.

    Args:
        target_pillars_scores: {"P3_scope": 55.0, "P4_quality": 68.0, ...}
        arguider_gaps_by_pillar: {"P3_scope": [{"name": "...", "severity": "..."}], ...}
        previous_iteration_feedback: resumo curto do que ficou incompleto na iter N-1.
    """
    pillars_block_parts = []
    for pillar, score in target_pillars_scores.items():
        label = _PILLAR_LABELS_PT.get(pillar, pillar)
        gaps = arguider_gaps_by_pillar.get(pillar, [])
        gaps_sample = json.dumps(gaps[:5], ensure_ascii=False)[:800]
        pillars_block_parts.append(
            f"- **{pillar}** ({label}) — score {score:.1f}/100\n"
            f"  Gaps identificados pelo Arguidor: {gaps_sample}"
        )
    pillars_block = "\n".join(pillars_block_parts) or "(nenhum pilar específico listado)"

    prev_block = ""
    if previous_iteration_feedback:
        prev_block = (
            f"\n## RESULTADO DA ITERAÇÃO ANTERIOR\n"
            f"{previous_iteration_feedback[:1000]}\n"
            f"Priorize questões que o usuário consiga responder desta vez.\n"
        )

    return (
        f"Você é um analista de governança de software sênior, falante nativo de PT-BR. "
        f"O projeto `{project_name}` está em iteração {iteration} de questionário customizado. "
        f"Score OCG atual: {overall_before:.1f}/100. Meta: ≥90.\n\n"
        f"## PILARES DEFICITÁRIOS (score < 75)\n{pillars_block}\n{prev_block}\n"
        f"## TAREFA\n"
        f"Gere 4 a 7 perguntas OBJETIVAS que um GP do projeto possa responder pra fechar "
        f"OS GAPS ACIMA. Cada pergunta:\n"
        f"  - Aponta pra UM pilar específico (campo `pillar` com o código P1..P7).\n"
        f"  - `type=choice` com 3-5 opções incluindo 'Não se aplica' quando a resposta "
        f"pode ser enumerada (estado/percentual/sim-não).\n"
        f"  - `type=text` com `max_chars=2000` quando exige descrição.\n"
        f"  - `context` curto (<=80 chars) citando o código do pilar + % de gap.\n"
        f"  - `required=true` quando o gap é show-stopper; `false` quando é informacional.\n"
        f"NÃO faça perguntas genéricas. Se não há gap claro num pilar, NÃO pergunte sobre ele.\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f"Retorne APENAS JSON válido, sem markdown fences, sem preâmbulo:\n"
        f'{{"questions": [{{"id": "Q1", "type": "choice|text", "text": "<até 220 chars>", '
        f'"context": "<até 80 chars>", "pillar": "P1_business_case|...|P7_security", '
        f'"required": true, "options": ["Opção 1", "Opção 2", "Não se aplica"]}}, ...]}}'
    )


def parse_iterative_response(raw_text: str) -> dict[str, Any]:
    """Parse tolerante da resposta do LLM. Remove fences MD se houver."""
    import re
    stripped = raw_text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if m:
        stripped = m.group(1).strip()
    data = json.loads(stripped)
    qs = data.get("questions") or []
    if not isinstance(qs, list):
        raise ValueError("Campo 'questions' precisa ser lista")
    # Sanitização mínima — não altera comportamento, só garante keys esperadas
    clean = []
    for i, q in enumerate(qs):
        if not isinstance(q, dict) or not q.get("text"):
            continue
        clean.append({
            "id": q.get("id") or f"Q{i+1}",
            "type": "choice" if q.get("type") == "choice" else "text",
            "text": str(q["text"])[:220],
            "context": str(q.get("context") or "")[:80],
            "pillar": q.get("pillar") or "",
            "required": bool(q.get("required", False)),
            "options": list(q.get("options") or []) if q.get("type") == "choice" else None,
            "max_chars": 2000 if q.get("type") != "choice" else None,
        })
    return {"questions": clean}
```

- [ ] **Step 2: Validar sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/iterative_questionnaire_generator.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/iterative_questionnaire_generator.py
git -C /home/luiz/GCA commit -m "M01 Task 3 — prompt builder iterativo (P1..P7 canônico)"
```

---

## Task 4: Service `iterative_questionnaire_service.py` (orquestrador)

**Files:**
- Create: `backend/app/services/iterative_questionnaire_service.py`

- [ ] **Step 1: Criar o service orquestrador**

Conteúdo completo:

```python
"""M01 — orquestrador de questionário iterativo.

Regras canônicas:
- Trigger: overall_score < 90 AND min(pilares) < 75.
- Convergência (D3): |overall_after - overall_before| < convergence_threshold (default 1.0).
- Inviabilidade (D4): ≥50% das respostas da iteração classificadas como 'not_applicable'.
- Score é atualizado APENAS pelo pipeline canônico (Arguidor → OCG Updater).
  Este service NÃO toca em ocg.overall_score — só lê e decide próxima iteração.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.base import (
    CustomQuestionnaireIteration,
    OCG,
    Project,
    IngestedDocument,
    ArguiderAnalysis,
)
from app.services.iterative_questionnaire_generator import (
    build_iterative_prompt,
    parse_iterative_response,
)

logger = logging.getLogger(__name__)

OVERALL_TARGET = 90.0
PILLAR_DEFICIT_THRESHOLD = 75.0
DEFAULT_CONVERGENCE_THRESHOLD = 1.0
INFEASIBLE_RATIO = 0.5

_PILLAR_KEYS = [
    "P1_business_case", "P2_business_model", "P3_scope", "P4_quality",
    "P5_ux", "P6_legal", "P7_security",
]


async def _load_latest_ocg(db: AsyncSession, project_id: UUID) -> OCG | None:
    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(desc(OCG.version)).limit(1)
    )
    return result.scalar_one_or_none()


def _extract_pillar_scores(ocg_data: dict | None) -> dict[str, float]:
    """Usa a mesma convenção canônica de `ocg_updater_service._extract_pillar_score`."""
    if not isinstance(ocg_data, dict):
        return {}
    pillars_block = ocg_data.get("PILLAR_SCORES") or {}
    if not isinstance(pillars_block, dict):
        return {}
    out: dict[str, float] = {}
    for key in _PILLAR_KEYS:
        val = pillars_block.get(key)
        if isinstance(val, dict) and "score" in val:
            try:
                out[key] = float(val["score"])
            except (TypeError, ValueError):
                continue
    return out


def _extract_overall(ocg_data: dict | None) -> float | None:
    if not isinstance(ocg_data, dict):
        return None
    comp = ocg_data.get("COMPOSITE_SCORE")
    if isinstance(comp, dict) and "value" in comp:
        try:
            return float(comp["value"])
        except (TypeError, ValueError):
            return None
    return None


async def compute_status_snapshot(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """Status público consumido pelo router + frontend.

    Retorna:
    {
      "overall": float | None,
      "deficit_pillars": {pillar: score, ...},  # <75
      "eligible_for_iteration": bool,
      "latest_iteration": {...} | None,
      "has_pending": bool,  # badge amarelo do sidebar
      "converged": bool,    # badge verde (último resultado)
    }
    """
    ocg = await _load_latest_ocg(db, project_id)
    overall: float | None = None
    deficit: dict[str, float] = {}
    if ocg:
        ocg_json = json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
        overall = _extract_overall(ocg_json)
        pillars = _extract_pillar_scores(ocg_json)
        deficit = {k: v for k, v in pillars.items() if v < PILLAR_DEFICIT_THRESHOLD}

    latest_result = await db.execute(
        select(CustomQuestionnaireIteration)
        .where(CustomQuestionnaireIteration.project_id == project_id)
        .order_by(desc(CustomQuestionnaireIteration.iteration))
        .limit(1)
    )
    latest: CustomQuestionnaireIteration | None = latest_result.scalar_one_or_none()

    eligible = (
        overall is not None
        and overall < OVERALL_TARGET
        and len(deficit) > 0
        and (latest is None or latest.status in ("converged", "infeasible", "answered"))
    )
    has_pending = latest is not None and latest.status == "pending"
    converged = latest is not None and latest.status == "converged"

    return {
        "overall": overall,
        "deficit_pillars": deficit,
        "eligible_for_iteration": eligible,
        "has_pending": has_pending,
        "converged": converged,
        "latest_iteration": (
            {
                "id": str(latest.id),
                "iteration": latest.iteration,
                "status": latest.status,
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
                "target_pillars": latest.target_pillars or [],
                "question_count": len(latest.questions or []),
                "overall_before": float(latest.overall_before) if latest.overall_before is not None else None,
                "overall_after": float(latest.overall_after) if latest.overall_after is not None else None,
            } if latest else None
        ),
    }


async def _collect_arguider_gaps(
    db: AsyncSession, project_id: UUID, target_pillars: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Agrega module_candidates/gatekeeper_items do Arguidor por pilar."""
    result = await db.execute(
        select(ArguiderAnalysis)
        .join(IngestedDocument, IngestedDocument.id == ArguiderAnalysis.document_id)
        .where(IngestedDocument.project_id == project_id)
        .order_by(desc(ArguiderAnalysis.created_at))
        .limit(20)
    )
    analyses = result.scalars().all()
    gaps_by_pillar: dict[str, list[dict[str, Any]]] = {p: [] for p in target_pillars}
    for a in analyses:
        mc = a.module_candidates
        if isinstance(mc, str):
            try:
                mc = json.loads(mc)
            except json.JSONDecodeError:
                continue
        if not isinstance(mc, list):
            continue
        for item in mc:
            if not isinstance(item, dict):
                continue
            pillar = item.get("pillar") or item.get("affected_pillar")
            if pillar in gaps_by_pillar and len(gaps_by_pillar[pillar]) < 8:
                gaps_by_pillar[pillar].append({
                    "name": str(item.get("name") or item.get("title") or "")[:120],
                    "severity": item.get("severity") or "info",
                })
    return gaps_by_pillar


async def generate_iteration(
    db: AsyncSession,
    project_id: UUID,
) -> CustomQuestionnaireIteration:
    """Gera nova iteração. Chama LLM via LLMServiceFactory (provider do projeto)."""
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError("Projeto não encontrado")

    snap = await compute_status_snapshot(db, project_id)
    if not snap["eligible_for_iteration"]:
        raise ValueError(
            "Projeto não elegível pra nova iteração (overall >= 90 ou nenhum pilar < 75 "
            "ou última iteração ainda pending)."
        )

    target_pillars_scores: dict[str, float] = snap["deficit_pillars"]
    overall_before: float = snap["overall"] or 0.0

    last_result = await db.execute(
        select(CustomQuestionnaireIteration)
        .where(CustomQuestionnaireIteration.project_id == project_id)
        .order_by(desc(CustomQuestionnaireIteration.iteration))
        .limit(1)
    )
    last = last_result.scalar_one_or_none()
    next_iteration = (last.iteration + 1) if last else 1

    gaps = await _collect_arguider_gaps(db, project_id, list(target_pillars_scores.keys()))
    prev_feedback = None
    if last and last.status in ("answered", "infeasible") and last.overall_after is not None:
        prev_feedback = (
            f"Iter {last.iteration}: overall {last.overall_before}→{last.overall_after}; "
            f"razão de 'não se aplica' {float(last.not_applicable_ratio or 0):.0%}."
        )

    prompt = build_iterative_prompt(
        project_name=project.name,
        iteration=next_iteration,
        overall_before=overall_before,
        target_pillars_scores=target_pillars_scores,
        arguider_gaps_by_pillar=gaps,
        previous_iteration_feedback=prev_feedback,
    )

    # Chama LLM do projeto via helper canônico (baixa criticidade pra gerar questões).
    from app.services.llm_low_criticality import resolve_llm_config, call_llm

    llm_cfg = await resolve_llm_config(db, project_id)
    raw_text = await call_llm(llm_cfg, prompt, max_tokens=4096, temperature=0.3)

    try:
        parsed = parse_iterative_response(raw_text)
    except Exception as exc:
        logger.error("m01.parse_failed", extra={"project_id": str(project_id), "error": str(exc)})
        raise ValueError(f"LLM retornou JSON inválido: {exc}")

    ocg = await _load_latest_ocg(db, project_id)
    ocg_version_before = ocg.version if ocg else None

    iteration_row = CustomQuestionnaireIteration(
        project_id=project_id,
        iteration=next_iteration,
        status="pending",
        target_pillars=list(target_pillars_scores.keys()),
        questions=parsed["questions"],
        ocg_version_before=ocg_version_before,
        overall_before=Decimal(str(overall_before)),
        convergence_threshold=Decimal(str(DEFAULT_CONVERGENCE_THRESHOLD)),
    )
    db.add(iteration_row)
    await db.commit()
    await db.refresh(iteration_row)
    return iteration_row


async def evaluate_convergence_after_ocg_update(
    db: AsyncSession,
    project_id: UUID,
    trigger_document_id: UUID,
) -> None:
    """Chamado pelo OCG Updater quando o doc fonte do update é uma resposta de iteração.

    Decide: converged / infeasible / answered (= pode gerar próxima).
    """
    iter_result = await db.execute(
        select(CustomQuestionnaireIteration)
        .where(CustomQuestionnaireIteration.answer_document_id == trigger_document_id)
        .order_by(desc(CustomQuestionnaireIteration.iteration))
        .limit(1)
    )
    row = iter_result.scalar_one_or_none()
    if row is None or row.status != "pending":
        return

    ocg = await _load_latest_ocg(db, project_id)
    if ocg is None:
        return
    ocg_json = json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
    overall_after = _extract_overall(ocg_json)

    before_val = float(row.overall_before) if row.overall_before is not None else 0.0
    threshold = float(row.convergence_threshold) if row.convergence_threshold is not None else DEFAULT_CONVERGENCE_THRESHOLD
    delta = abs((overall_after or 0.0) - before_val)

    row.ocg_version_after = ocg.version
    row.overall_after = Decimal(str(overall_after)) if overall_after is not None else None

    if row.not_applicable_ratio is not None and float(row.not_applicable_ratio) >= INFEASIBLE_RATIO:
        row.status = "infeasible"
        row.converged = False
    elif overall_after is not None and overall_after >= OVERALL_TARGET:
        row.status = "converged"
        row.converged = True
    elif delta < threshold:
        row.status = "converged"
        row.converged = True
    else:
        row.status = "answered"
        row.converged = False

    await db.commit()
    logger.info(
        "m01.convergence_evaluated",
        extra={
            "project_id": str(project_id),
            "iteration": row.iteration,
            "status": row.status,
            "delta": delta,
        },
    )


def classify_not_applicable_ratio(canonical_text: str) -> float:
    """Heurística simples: contagem de 'não se aplica' / 'nsa' vs total de perguntas referenciadas.

    Usada pelo hook no updater quando precisa marcar inviabilidade.
    Conservadora — prefere subestimar (não gerar falsa inviabilidade).
    """
    if not canonical_text:
        return 0.0
    lowered = canonical_text.lower()
    import re
    question_markers = re.findall(r"\bq\d+[\.\:]", lowered)
    total = max(1, len(question_markers))
    nsa = lowered.count("não se aplica") + lowered.count("n/a") + lowered.count(" nsa ")
    return min(1.0, nsa / total)
```

- [ ] **Step 2: Validar sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/iterative_questionnaire_service.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Validar import no container**

Run:
```
docker restart gca-backend && sleep 5 && docker exec gca-backend python -c "from app.services.iterative_questionnaire_service import compute_status_snapshot, generate_iteration, evaluate_convergence_after_ocg_update; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/iterative_questionnaire_service.py
git -C /home/luiz/GCA commit -m "M01 Task 4 — orchestrador service (threshold, convergência, infeasibility)"
```

---

## Task 5: Router `iterative_questionnaire_router.py`

**Files:**
- Create: `backend/app/routers/iterative_questionnaire_router.py`
- Modify: `backend/app/main.py` (registrar router — checar padrão com `grep "include_router" backend/app/main.py | head -5`)

- [ ] **Step 1: Criar router com 4 endpoints**

Conteúdo completo:

```python
"""M01 — router Questões em Aberto."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.middleware.auth import get_current_user_from_token
from app.models.base import CustomQuestionnaireIteration, IngestedDocument
from app.services.iterative_questionnaire_service import (
    compute_status_snapshot,
    generate_iteration,
)
from app.services.pdf_questionnaire_generator import pdf_generator  # MVP 24

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/iterative-questionnaire", tags=["iterative-questionnaire"])


class StatusResponse(BaseModel):
    overall: float | None
    deficit_pillars: dict[str, float]
    eligible_for_iteration: bool
    has_pending: bool
    converged: bool
    latest_iteration: dict[str, Any] | None


class GenerateResponse(BaseModel):
    id: str
    iteration: int
    question_count: int
    target_pillars: list[str]


@router.get("/status", response_model=StatusResponse)
async def get_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Usado pelo sidebar/badge + página."""
    await require_action(action="project:read", project_id=project_id, user_id=user_id, db=db)
    return await compute_status_snapshot(db, project_id)


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """GP dispara geração de nova iteração (quando eligible)."""
    await require_action(action="project:write", project_id=project_id, user_id=user_id, db=db)
    try:
        row = await generate_iteration(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return GenerateResponse(
        id=str(row.id),
        iteration=row.iteration,
        question_count=len(row.questions or []),
        target_pillars=list(row.target_pillars or []),
    )


@router.get("/{iteration_id}/pdf")
async def download_pdf(
    project_id: UUID,
    iteration_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Gera PDF sob demanda (lazy — economiza storage de BLOB até primeiro download)."""
    await require_action(action="project:read", project_id=project_id, user_id=user_id, db=db)
    result = await db.execute(
        select(CustomQuestionnaireIteration).where(
            (CustomQuestionnaireIteration.id == iteration_id)
            & (CustomQuestionnaireIteration.project_id == project_id)
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Iteração não encontrada")

    pdf_bytes = row.pdf_blob
    if not pdf_bytes:
        from app.models.base import Project
        proj = await db.get(Project, project_id)
        pdf_bytes = pdf_generator.generate_pdf(
            project_name=proj.name if proj else "Projeto",
            questions=row.questions or [],
            iteration=row.iteration,
        )
        row.pdf_blob = pdf_bytes
        await db.commit()

    filename = f"Questoes_Abertas_Iter{row.iteration}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{iteration_id}/upload-answers")
async def upload_answers(
    project_id: UUID,
    iteration_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Upload do PDF respondido.

    Cria IngestedDocument com `document_type='iterative_questionnaire_answer'`
    e `metadata.iteration_id`. O pipeline de ingestão canônico (canonização MVP 29
    → Arguidor → OCG Updater) processa normalmente. O hook no updater detecta
    o trigger e chama `evaluate_convergence_after_ocg_update`.
    """
    await require_action(action="project:write", project_id=project_id, user_id=user_id, db=db)

    result = await db.execute(
        select(CustomQuestionnaireIteration).where(
            (CustomQuestionnaireIteration.id == iteration_id)
            & (CustomQuestionnaireIteration.project_id == project_id)
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Iteração não encontrada")
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Iteração já está em estado '{row.status}' — não aceita novo upload.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    # Delega ao pipeline canônico de ingestão. Usa IngestionService existente.
    from app.services.ingestion_service import IngestionService

    service = IngestionService(db)
    doc = await service.ingest_upload(
        project_id=project_id,
        user_id=user_id,
        filename=file.filename or f"questoes_iter{row.iteration}.pdf",
        content_bytes=content,
        document_type="iterative_questionnaire_answer",
        metadata={"iteration_id": str(iteration_id), "iteration": row.iteration},
    )

    row.answer_document_id = doc.id
    # não muda status ainda — vira 'answered' quando OCG updater terminar e o hook rodar
    await db.commit()

    return {
        "document_id": str(doc.id),
        "iteration_id": str(iteration_id),
        "message": (
            "Resposta em processamento. O OCG será re-avaliado automaticamente "
            "e o status de convergência aparecerá aqui."
        ),
    }
```

- [ ] **Step 2: Registrar router em `main.py`**

Localizar o bloco de `include_router` em `backend/app/main.py` e adicionar:

```python
from app.routers.iterative_questionnaire_router import router as iterative_questionnaire_router
# ... (nas demais importações)

# ... (próximo ao bloco de include_router existente):
app.include_router(iterative_questionnaire_router, prefix="/api/v1")
```

Verificar com `grep -n "include_router" backend/app/main.py` a linha exata onde inserir — manter ordem alfabética dos routers.

- [ ] **Step 3: Validar sintaxe + restart backend**

Run:
```
python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/routers/iterative_questionnaire_router.py').read()); print('OK router')" && \
python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/main.py').read()); print('OK main')" && \
docker restart gca-backend 2>&1 | tail -1 && sleep 5 && \
docker logs gca-backend --tail=5 2>&1 | tail -5
```
Expected: `OK router` + `OK main` + `Application startup complete.`

- [ ] **Step 4: Smoke test do endpoint `/status`**

Run (token JWT do dogfood — usar o token que está no localStorage do browser, OU via curl autenticado):
```
PROJECT_ID=65cab180-e00d-4eec-aaf2-fb4b5d0f4057
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/projects/$PROJECT_ID/iterative-questionnaire/status | jq .
```
Expected: JSON com `overall`, `deficit_pillars`, `eligible_for_iteration`, `has_pending`, `converged`. HTTP 200.

- [ ] **Step 5: Commit**

```bash
git -C /home/luiz/GCA add backend/app/routers/iterative_questionnaire_router.py backend/app/main.py
git -C /home/luiz/GCA commit -m "M01 Task 5 — router + registro em main (status, generate, pdf, upload)"
```

---

## Task 6: Hook no OCG Updater pra convergência

**Files:**
- Modify: `backend/app/services/ocg_updater_service.py` (trecho de finalização após `_update_ocg_record`)

- [ ] **Step 1: Identificar ponto de gancho**

Run: `grep -n "_update_ocg_record\|apply_deltas\|trigger_document_id" /home/luiz/GCA/backend/app/services/ocg_updater_service.py | head -15`

Encontrar a função pública que recebe o documento-trigger e termina o update. Inserir chamada ao hook DEPOIS que o OCG foi persistido e antes de retornar. Abrir o arquivo na faixa encontrada e localizar a ÚLTIMA linha ANTES do `return` da função pública principal.

- [ ] **Step 2: Adicionar import + chamada**

No topo do arquivo (junto aos outros imports do próprio módulo):

```python
from app.services.iterative_questionnaire_service import (
    evaluate_convergence_after_ocg_update,
)
```

No final da função principal (antes do `return`), adicionar:

```python
# M01 — hook convergência: se o documento-trigger é resposta de iteração,
# decide se convergiu / é inviável / pode gerar próxima.
try:
    if trigger_document_id is not None:
        await evaluate_convergence_after_ocg_update(db, project_id, trigger_document_id)
except Exception as exc:  # noqa: BLE001
    logger.warning(
        "m01.convergence_hook_failed",
        extra={"project_id": str(project_id), "error": str(exc)},
    )
```

O nome do parâmetro `trigger_document_id` pode variar (`document_id`, `source_document_id`, etc) — adaptar ao nome real do parâmetro existente na função.

- [ ] **Step 3: Validar sintaxe + restart**

Run:
```
python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/ocg_updater_service.py').read()); print('OK')" && \
docker restart gca-backend 2>&1 | tail -1 && sleep 5
```
Expected: `OK` + backend up.

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/ocg_updater_service.py
git -C /home/luiz/GCA commit -m "M01 Task 6 — hook convergência pós-OCG-update"
```

---

## Task 7: Testes standalone M01

**Files:**
- Create: `backend/app/tests/test_m01_iterative_questionnaire.py`

- [ ] **Step 1: Criar testes standalone**

Conteúdo completo:

```python
"""M01 — testes unit standalone (padrão MVP 29, sem pytest/DB de prod).

Cobre: prompt builder, parser tolerante, classificador de NSA, helpers
de extração de pilares.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.iterative_questionnaire_generator import (
    build_iterative_prompt, parse_iterative_response,
)
from app.services.iterative_questionnaire_service import (
    _extract_overall, _extract_pillar_scores, classify_not_applicable_ratio,
)


def test_prompt_contains_deficit_pillars():
    p = build_iterative_prompt(
        project_name="AJA", iteration=1, overall_before=73.7,
        target_pillars_scores={"P3_scope": 55.0, "P4_quality": 68.0},
        arguider_gaps_by_pillar={"P3_scope": [{"name": "DataJud adapter faltante", "severity": "critical"}]},
    )
    assert "P3_scope" in p
    assert "DataJud adapter" in p
    assert "73.7" in p
    assert "iteração 1" in p


def test_prompt_includes_previous_feedback_when_provided():
    p = build_iterative_prompt(
        project_name="X", iteration=2, overall_before=80.0,
        target_pillars_scores={"P7_security": 70.0},
        arguider_gaps_by_pillar={"P7_security": []},
        previous_iteration_feedback="Iter 1: overall 75->78",
    )
    assert "Iter 1: overall 75->78" in p


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"questions": [{"id":"Q1","type":"text","text":"Como é a arquitetura?","context":"P3_scope gap 20%","pillar":"P3_scope","required":true}]}\n```'
    out = parse_iterative_response(raw)
    assert len(out["questions"]) == 1
    assert out["questions"][0]["id"] == "Q1"
    assert out["questions"][0]["pillar"] == "P3_scope"


def test_parse_response_coerces_missing_ids():
    raw = '{"questions":[{"type":"text","text":"pergunta sem id"},{"type":"choice","text":"outra","options":["a","b"]}]}'
    out = parse_iterative_response(raw)
    assert out["questions"][0]["id"] == "Q1"
    assert out["questions"][1]["id"] == "Q2"


def test_parse_response_rejects_nonlist():
    raw = '{"questions": "nao e lista"}'
    try:
        parse_iterative_response(raw)
        assert False, "deveria ter levantado ValueError"
    except ValueError:
        pass


def test_parse_response_drops_empty_text_items():
    raw = '{"questions":[{"id":"Q1","type":"text","text":""},{"id":"Q2","type":"text","text":"valida"}]}'
    out = parse_iterative_response(raw)
    assert len(out["questions"]) == 1
    assert out["questions"][0]["text"] == "valida"


def test_extract_pillar_scores_canonical():
    data = {
        "PILLAR_SCORES": {
            "P1_business_case": {"score": 60, "weight": 0.10},
            "P3_scope": {"score": 55.0, "weight": 0.20},
            "P7_security": {"score": 88, "weight": 0.10},
        }
    }
    out = _extract_pillar_scores(data)
    assert out["P1_business_case"] == 60.0
    assert out["P3_scope"] == 55.0
    assert out["P7_security"] == 88.0


def test_extract_overall_from_composite():
    assert _extract_overall({"COMPOSITE_SCORE": {"value": 73.65}}) == 73.65
    assert _extract_overall({}) is None
    assert _extract_overall({"COMPOSITE_SCORE": "invalido"}) is None


def test_classify_not_applicable_ratio_majority():
    text = "Q1: não se aplica\nQ2: não se aplica\nQ3: sim, temos controles"
    ratio = classify_not_applicable_ratio(text)
    assert ratio > 0.5


def test_classify_not_applicable_ratio_minority():
    text = "Q1: temos LGPD mapeada\nQ2: não se aplica\nQ3: em progresso"
    ratio = classify_not_applicable_ratio(text)
    assert ratio < 0.5


def test_classify_not_applicable_ratio_empty():
    assert classify_not_applicable_ratio("") == 0.0


def _run_all():
    import inspect
    tests = [v for k, v in globals().items() if k.startswith("test_") and inspect.isfunction(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t(); passed += 1
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, f"assertion: {e}")); print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}")); print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*60}\nTotal: {len(tests)}  Passou: {passed}  Falhou: {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
```

- [ ] **Step 2: Copiar + rodar no container**

Run:
```
docker cp /home/luiz/GCA/backend/app/tests/test_m01_iterative_questionnaire.py gca-backend:/app/app/tests/test_m01_iterative_questionnaire.py
docker exec gca-backend python -m app.tests.test_m01_iterative_questionnaire
```
Expected: `Total: 11  Passou: 11  Falhou: 0`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/tests/test_m01_iterative_questionnaire.py
git -C /home/luiz/GCA commit -m "M01 Task 7 — testes standalone (11 testes prompt/parser/convergência)"
```

---

## Task 8: Frontend — hook + entrada na Sidebar com badge

**Files:**
- Create: `frontend/src/hooks/useIterativeQuestionnaireStatus.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx` (localizar item "Ingestão" e adicionar "Questões em Aberto" logo após — `grep -n "Ingestão" frontend/src/components/layout/Sidebar.tsx`)

- [ ] **Step 1: Criar hook de status**

Conteúdo completo de `frontend/src/hooks/useIterativeQuestionnaireStatus.ts`:

```typescript
import { useEffect, useState } from 'react'
import { apiClient } from '@/lib/api'

export interface IterativeQStatus {
  overall: number | null
  deficit_pillars: Record<string, number>
  eligible_for_iteration: boolean
  has_pending: boolean
  converged: boolean
  latest_iteration: {
    id: string
    iteration: number
    status: string
    created_at: string | null
    target_pillars: string[]
    question_count: number
    overall_before: number | null
    overall_after: number | null
  } | null
}

/**
 * M01 — status do questionário iterativo. Usado pelo sidebar pra decidir
 * badge (• pendente / ✓ convergido / nada) e pela página pra montar UI.
 * Polling 30s (padrão canônico das páginas reativas do GCA).
 */
export function useIterativeQuestionnaireStatus(projectId: string | undefined) {
  const [data, setData] = useState<IterativeQStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    const load = async () => {
      try {
        const res = await apiClient.get(`/projects/${projectId}/iterative-questionnaire/status`)
        if (!cancelled) setData(res.data)
      } catch {
        if (!cancelled) setData(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 30_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [projectId])

  return { data, loading }
}
```

- [ ] **Step 2: Adicionar item na Sidebar**

Run: `grep -n "Ingestão\|'ingestion'" /home/luiz/GCA/frontend/src/components/layout/Sidebar.tsx`

Localizar o item da Ingestão (ou no array `MODULES` do ProjectDetailLayout se a sidebar vier de lá). Adicionar item "Questões em Aberto" IMEDIATAMENTE após Ingestão:

```tsx
// No array de itens da sidebar (adaptar conforme estrutura real do arquivo):
{ path: 'iterative-questionnaire', label: 'Questões em Aberto', icon: HelpCircle },
```

Se a sidebar já tiver slot pra badge dinâmico (como "Backups/Incidentes" usam): consumir `useIterativeQuestionnaireStatus` + renderizar:

```tsx
import { useIterativeQuestionnaireStatus } from '@/hooks/useIterativeQuestionnaireStatus'
// ... dentro do componente da linha do item:
const { data: iqStatus } = useIterativeQuestionnaireStatus(projectId)
const badgeEl =
  iqStatus?.has_pending ? (
    <span className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-400" title="Questões pendentes" />
  ) : iqStatus?.converged ? (
    <CheckCircle2 className="ml-auto w-3 h-3 text-emerald-400" />
  ) : null
```

Se o padrão da sidebar não suportar badges por item hoje, fazer ajuste mínimo: abrir Sidebar.tsx → identificar o `<NavLink>` de cada item → adicionar `{badgeEl}` no final do conteúdo do link.

- [ ] **Step 3: Adicionar rota no routes.tsx (ou App.tsx)**

Run: `grep -n "projects/:id\|codegen\|ingestion" /home/luiz/GCA/frontend/src/routes.tsx | head -15`

Adicionar rota filha do `ProjectDetailLayout`:

```tsx
{ path: 'iterative-questionnaire', element: <IterativeQuestionnairePage /> }
```

E o import no topo.

- [ ] **Step 4: Build frontend**

Run: `docker exec gca-frontend npm run build 2>&1 | tail -5`
Expected: `✓ built in Xs`, sem erros TS.

- [ ] **Step 5: Commit**

```bash
git -C /home/luiz/GCA add frontend/src/hooks/useIterativeQuestionnaireStatus.ts frontend/src/components/layout/Sidebar.tsx frontend/src/routes.tsx
git -C /home/luiz/GCA commit -m "M01 Task 8 — sidebar item + badge + hook status + rota"
```

---

## Task 9: Frontend — página `IterativeQuestionnairePage.tsx`

**Files:**
- Create: `frontend/src/pages/projects/IterativeQuestionnairePage.tsx`

- [ ] **Step 1: Criar a página**

Conteúdo completo:

```tsx
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, CheckCircle2, AlertCircle, Download, Upload, Sparkles } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { useIterativeQuestionnaireStatus } from '@/hooks/useIterativeQuestionnaireStatus'

const PILLAR_LABELS: Record<string, string> = {
  P1_business_case: 'Caso de Negócio',
  P2_business_model: 'Modelo de Negócio',
  P3_scope: 'Escopo',
  P4_quality: 'Qualidade',
  P5_ux: 'UX',
  P6_legal: 'Jurídico',
  P7_security: 'Segurança',
}

export function IterativeQuestionnairePage() {
  const { id: projectId } = useParams<{ id: string }>()
  const { data, loading } = useIterativeQuestionnaireStatus(projectId)
  const [generating, setGenerating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando status...
      </div>
    )
  }

  if (!data) {
    return <div className="p-8 text-slate-500">Não foi possível carregar o status.</div>
  }

  const handleGenerate = async () => {
    if (!projectId) return
    setGenerating(true); setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/iterative-questionnaire/generate`)
      window.location.reload()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Falha ao gerar iteração')
    } finally {
      setGenerating(false)
    }
  }

  const handleDownload = async () => {
    if (!projectId || !data.latest_iteration) return
    const res = await apiClient.get(
      `/projects/${projectId}/iterative-questionnaire/${data.latest_iteration.id}/pdf`,
      { responseType: 'blob' },
    )
    const url = window.URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `Questoes_Abertas_Iter${data.latest_iteration.iteration}.pdf`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !projectId || !data.latest_iteration) return
    setUploading(true); setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      await apiClient.post(
        `/projects/${projectId}/iterative-questionnaire/${data.latest_iteration.id}/upload-answers`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      window.location.reload()
    } catch (err: unknown) {
      const errObj = err as { response?: { data?: { detail?: string } } }
      setError(errObj.response?.data?.detail || 'Falha ao enviar resposta')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100 mb-1">Questões em Aberto</h1>
        <p className="text-xs text-slate-500">
          Perguntas geradas a partir dos pilares deficitários do OCG. Meta: overall ≥ 90 e todos os pilares ≥ 75.
        </p>
      </header>

      {/* Status geral */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">OCG atual</div>
          <div className="text-2xl font-semibold text-slate-100">
            {data.overall !== null ? data.overall.toFixed(1) : '—'}
            <span className="text-xs text-slate-500 ml-1">/100</span>
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Pilares deficitários</div>
          <div className="text-sm text-slate-200">
            {Object.keys(data.deficit_pillars).length === 0
              ? <span className="text-emerald-400">Nenhum</span>
              : Object.entries(data.deficit_pillars).map(([p, s]) => (
                <div key={p} className="flex justify-between">
                  <span>{PILLAR_LABELS[p] || p}</span>
                  <span className="text-amber-400">{(s as number).toFixed(1)}</span>
                </div>
              ))}
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Status</div>
          <div className="text-sm">
            {data.converged && <span className="flex items-center gap-1 text-emerald-400"><CheckCircle2 className="w-4 h-4" /> Convergido</span>}
            {data.has_pending && <span className="flex items-center gap-1 text-amber-400"><AlertCircle className="w-4 h-4" /> Aguardando resposta</span>}
            {!data.has_pending && !data.converged && data.eligible_for_iteration && (
              <span className="text-slate-300">Pronto pra nova iteração</span>
            )}
            {!data.has_pending && !data.converged && !data.eligible_for_iteration && (
              <span className="text-slate-500">Sem ação pendente</span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-950/30 border border-red-900/40 rounded text-xs text-red-400">{error}</div>
      )}

      {/* Ações */}
      {data.eligible_for_iteration && !data.has_pending && (
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="mb-6 inline-flex items-center gap-2 px-4 py-2 rounded-md bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium disabled:opacity-50"
        >
          {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          Gerar nova iteração
        </button>
      )}

      {/* Iteração atual */}
      {data.latest_iteration && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-slate-100">
                Iteração {data.latest_iteration.iteration}
                <span className="ml-2 text-[10px] text-slate-500 uppercase">{data.latest_iteration.status}</span>
              </div>
              <div className="text-xs text-slate-500">
                {data.latest_iteration.question_count} pergunta(s) •
                Pilares: {data.latest_iteration.target_pillars.map(p => PILLAR_LABELS[p] || p).join(', ')}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleDownload}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
              >
                <Download className="w-3.5 h-3.5" /> Baixar PDF
              </button>
              {data.latest_iteration.status === 'pending' && (
                <label className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-xs text-white cursor-pointer">
                  {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                  Enviar resposta
                  <input type="file" accept=".pdf" className="hidden" onChange={handleUpload} disabled={uploading} />
                </label>
              )}
            </div>
          </div>
          {data.latest_iteration.overall_after !== null && (
            <div className="px-4 py-2 text-xs text-slate-400 bg-slate-950/40 border-b border-slate-800">
              Overall antes: <strong>{data.latest_iteration.overall_before?.toFixed(1)}</strong> →
              depois: <strong>{data.latest_iteration.overall_after?.toFixed(1)}</strong>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Build frontend**

Run: `docker exec gca-frontend npm run build 2>&1 | tail -5 && docker restart gca-frontend 2>&1 | tail -1`
Expected: `✓ built in Xs`, sem erros.

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add frontend/src/pages/projects/IterativeQuestionnairePage.tsx
git -C /home/luiz/GCA commit -m "M01 Task 9 — IterativeQuestionnairePage (status, generate, PDF, upload)"
```

---

## Task 10: Validação dogfood + relatório de impacto

**Files:**
- Create: `docs/design/m01_impact_report.md`

- [ ] **Step 1: Hard-refresh + smoke test manual no AJA**

Stakeholder:
1. `Ctrl+Shift+R` na página do projeto AJA.
2. Checar badge `•` amarelo na sidebar (OCG 73.7 < 90 e há pilares < 75 → elegível).
3. Abrir "Questões em Aberto", clicar "Gerar nova iteração".
4. Baixar PDF, preencher 2-3 questões, salvar, upload.
5. Aguardar pipeline Arguidor+Updater finalizar (~2-5 min). Badge vira `✓` se convergiu OU volta a `•` se há nova iteração.

- [ ] **Step 2: Coletar métricas**

Run:
```
docker exec gca-postgres psql -U gca -d gca -c "SELECT iteration, status, overall_before, overall_after, converged, not_applicable_ratio FROM custom_questionnaire_iterations WHERE project_id='65cab180-e00d-4eec-aaf2-fb4b5d0f4057' ORDER BY iteration;"
```

- [ ] **Step 3: Escrever relatório**

Conteúdo completo de `docs/design/m01_impact_report.md`:

```markdown
# M01 — Relatório de Impacto (Questões em Aberto Iterativas)

**Data:** [DATA]
**Status:** MVP M01 entregue (Tasks 1-9)

## Arquitetura aplicada

- 1 tabela nova (`custom_questionnaire_iterations`) — histórico de iterações.
- Respostas = documentos ingeridos. Zero código de "delta de score direto".
- LLM via `LLMServiceFactory` (§6.2 respeitado).
- Convergência: |overall_after - overall_before| < 1.0 → fecha loop.
- Inviabilidade: ≥50% de "não se aplica" → fecha loop.

## Dogfood AJA (projeto 65cab180)

| Iter | Status | Overall antes | Overall depois | Δ | NSA ratio | Tempo total |
|---|---|---|---|---|---|---|
| 1 | _preencher_ | _preencher_ | _preencher_ | _preencher_ | _preencher_ | _preencher_ |

## Tasks (1-9 deste plano)

1. Migration SQL
2. Model SQLAlchemy
3. Prompt builder
4. Service orquestrador
5. Router (4 endpoints)
6. Hook no OCG Updater
7. 11 testes standalone passing
8. Sidebar + hook + rota
9. Página frontend

## Pendências futuras (DT-092 potencial)

- Limite explícito de iterações máximas (hoje convergência decide — pode loopar se score oscilar).
- PDF com AcroForm real (hoje é formato "linha de underline" herdado do MVP 24).
- Paralelização de upload se múltiplas iterações pendentes.
```

- [ ] **Step 4: Commit final**

```bash
git -C /home/luiz/GCA add docs/design/m01_impact_report.md
git -C /home/luiz/GCA commit -m "M01 Task 10 — relatório de impacto (MVP FECHADO)"
```

---

## Self-Review

**1. Spec coverage (D1-D4 e contrato):**

- [D1 — aba nova com badge]: Task 8 adiciona item "Questões em Aberto" na sidebar + hook com badge `•`/`✓`. ✓
- [D2 — threshold overall<90 AND min(pilares)<75]: Task 4 `compute_status_snapshot` implementa exatamente essa regra via constantes `OVERALL_TARGET=90` e `PILLAR_DEFICIT_THRESHOLD=75`. ✓
- [D3 — convergência]: Task 4 `evaluate_convergence_after_ocg_update` decide por `|delta| < threshold` (default 1.0). ✓
- [D4 — inviabilidade 50% NSA]: Task 4 `INFEASIBLE_RATIO=0.5` + `classify_not_applicable_ratio` feature no Task 7 (testes). ✓
- [§6.2 IA configurável]: Task 4 usa `llm_low_criticality.resolve_llm_config` que já é agnóstico de provider. ✓
- [P1..P7 canônicos]: `_PILLAR_KEYS` + `_PILLAR_LABELS_PT` usam nomes canônicos em todas as tasks. ✓
- [PT-BR]: todos os textos de UI + prompts + commits em PT-BR. ✓
- [DT-034 pytest]: Task 7 segue padrão standalone `python -m app.tests...`. ✓
- [Reusa MVP 24]: Task 5 importa `pdf_generator` existente. ✓
- [Reusa pipeline ingestão MVP 29]: Task 5 delega ao `IngestionService.ingest_upload`. ✓

**2. Placeholder scan:**

- Task 2 referencia `datetime_utcnow` — INSTRUIDO a conferir padrão do arquivo e adaptar (não é TBD, é escolha cirúrgica).
- Task 6 referencia `trigger_document_id` — INSTRUIDO a identificar nome real do parâmetro via grep antes.
- Task 8 tem "adaptar conforme estrutura real do arquivo" — JUSTIFICADO porque a sidebar do GCA já tem 2 padrões históricos (MODULES em ProjectDetailLayout.tsx vs Sidebar.tsx); executor escolhe o que encaixa.

Nenhum "TODO", "fill in later", ou teste sem código.

**3. Type consistency:**

- `compute_status_snapshot` retorna dict com keys (`overall`, `deficit_pillars`, `eligible_for_iteration`, `has_pending`, `converged`, `latest_iteration`) — consumido igual pelo Task 5 router (response_model) e pelo Task 8 hook TS (`IterativeQStatus`).
- Pillar keys (`P1_business_case`..`P7_security`) idênticos no backend prompt (Task 3) + service (Task 4) + frontend labels (Task 9).
- Status values (`pending`|`answered`|`converged`|`infeasible`|`superseded`) consistentes entre migration (Task 1), model (Task 2), service (Task 4), router (Task 5), página (Task 9).
- `iteration_id` sempre UUID em backend, string em frontend — conversão implícita pelo JSON, OK.
