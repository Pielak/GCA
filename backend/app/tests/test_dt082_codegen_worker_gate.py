"""DT-082 — Defesa em profundidade: gate de maturidade do OCG no worker Celery.

Antes: `execute_run` em scaffold_run_service.py confiava que o caller HTTP
já tinha validado o gate. Se algum caller futuro (cron, debug, ferramenta
manual) enfileirasse uma run sem passar pelo endpoint, gate era bypassado.

Depois: `execute_run` chama `evaluate_ocg_maturity` na entrada e marca
`run.status='blocked'` em vez de levantar HTTPException (worker não tem
caller HTTP).

Cobre:
  - `evaluate_ocg_maturity` retorna OCGGateResult sem levantar exceção.
  - Cobertura dos 4 níveis: liberado, no_ocg, hard_block, insufficient, immature.
  - `check_ocg_maturity_gate` (caminho HTTP) continua levantando 404/409.
  - Não-regressão: payload das HTTPException mantém formato.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_dt082_codegen_worker_gate.py -v"
"""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.base import OCG, Questionnaire
from app.services.ocg_gate import (
    SCORE_MATURIDADE,
    SCORE_MINIMO_ABSOLUTO,
    check_ocg_maturity_gate,
    evaluate_ocg_maturity,
)
from app.tests.factories import (
    create_test_organization,
    create_test_project,
)


# =============================================================================
# Helpers
# =============================================================================


async def _seed_project(db):
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"dt082-{uuid4().hex[:6]}"
    )
    return project


async def _seed_ocg(db, project_id, *, overall_score=None, is_blocking=False, status="active"):
    questionnaire = Questionnaire(
        id=uuid4(),
        project_id=project_id,
        gp_email=f"dt082-{uuid4().hex[:6]}@test.com",
        responses="{}",
        status="pending",
    )
    db.add(questionnaire)
    await db.flush()

    ocg = OCG(
        id=uuid4(),
        questionnaire_id=questionnaire.id,
        project_id=project_id,
        overall_score=overall_score,
        status=status,
        is_blocking=is_blocking,
        ocg_data="{}",
        version=1,
    )
    db.add(ocg)
    await db.flush()
    return ocg


# =============================================================================
# evaluate_ocg_maturity — caminho worker (sem raise)
# =============================================================================


@pytest.mark.asyncio
async def test_evaluate_no_ocg_returns_blocked(db_session):
    """Projeto sem OCG → blocked=True, block_level='no_ocg' (sem raise)."""
    project = await _seed_project(db_session)

    result = await evaluate_ocg_maturity(project.id, db_session)

    assert result["blocked"] is True
    assert result["block_level"] == "no_ocg"
    assert result["overall_score"] == 0.0
    assert result["ocg_version"] is None
    assert "questionário" in result["blocking_reason"].lower()


@pytest.mark.asyncio
async def test_evaluate_hard_block_when_is_blocking(db_session):
    """OCG com is_blocking=True → blocked + block_level='hard_block'."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=85, is_blocking=True)

    result = await evaluate_ocg_maturity(project.id, db_session)

    assert result["blocked"] is True
    assert result["block_level"] == "hard_block"
    assert result["overall_score"] == 85.0
    assert result["ocg_version"] == 1


@pytest.mark.asyncio
async def test_evaluate_insufficient_when_below_minimum(db_session):
    """overall_score < 60 → blocked + block_level='insufficient'."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=SCORE_MINIMO_ABSOLUTO - 1)

    result = await evaluate_ocg_maturity(project.id, db_session)

    assert result["blocked"] is True
    assert result["block_level"] == "insufficient"
    assert result["overall_score"] == SCORE_MINIMO_ABSOLUTO - 1


@pytest.mark.asyncio
async def test_evaluate_immature_when_below_maturity(db_session):
    """60 <= overall_score < 95 → blocked + block_level='immature'."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=80)

    result = await evaluate_ocg_maturity(project.id, db_session)

    assert result["blocked"] is True
    assert result["block_level"] == "immature"
    assert result["overall_score"] == 80.0


@pytest.mark.asyncio
async def test_evaluate_liberado_when_score_at_threshold(db_session):
    """overall_score >= 95 → blocked=False (CodeGen liberado)."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=SCORE_MATURIDADE)

    result = await evaluate_ocg_maturity(project.id, db_session)

    assert result["blocked"] is False
    assert result["block_level"] is None
    assert result["overall_score"] == SCORE_MATURIDADE
    assert result["blocking_reason"] is None


@pytest.mark.asyncio
async def test_evaluate_liberado_when_score_above_threshold(db_session):
    """overall_score=100 → liberado."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=100)

    result = await evaluate_ocg_maturity(project.id, db_session)

    assert result["blocked"] is False


# =============================================================================
# check_ocg_maturity_gate — caminho HTTP (com raise) — não-regressão
# =============================================================================


@pytest.mark.asyncio
async def test_check_no_ocg_raises_404(db_session):
    """Caminho HTTP: sem OCG → HTTPException 404."""
    project = await _seed_project(db_session)

    with pytest.raises(HTTPException) as exc:
        await check_ocg_maturity_gate(project.id, db_session)

    assert exc.value.status_code == 404
    assert exc.value.detail["block_level"] == "no_ocg"


@pytest.mark.asyncio
async def test_check_hard_block_raises_409(db_session):
    """Caminho HTTP: is_blocking=True → HTTPException 409 hard_block."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=85, is_blocking=True)

    with pytest.raises(HTTPException) as exc:
        await check_ocg_maturity_gate(project.id, db_session)

    assert exc.value.status_code == 409
    assert exc.value.detail["block_level"] == "hard_block"
    assert exc.value.detail["overall_score"] == 85.0
    assert exc.value.detail["score_required"] == SCORE_MATURIDADE


@pytest.mark.asyncio
async def test_check_insufficient_raises_409(db_session):
    """Caminho HTTP: insufficient → HTTPException 409."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=40)

    with pytest.raises(HTTPException) as exc:
        await check_ocg_maturity_gate(project.id, db_session)

    assert exc.value.status_code == 409
    assert exc.value.detail["block_level"] == "insufficient"


@pytest.mark.asyncio
async def test_check_immature_raises_409(db_session):
    """Caminho HTTP: immature → HTTPException 409."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=80)

    with pytest.raises(HTTPException) as exc:
        await check_ocg_maturity_gate(project.id, db_session)

    assert exc.value.status_code == 409
    assert exc.value.detail["block_level"] == "immature"


@pytest.mark.asyncio
async def test_check_liberado_returns_none(db_session):
    """Caminho HTTP: maduro → retorna None silenciosamente."""
    project = await _seed_project(db_session)
    await _seed_ocg(db_session, project.id, overall_score=98)

    # Não deve levantar
    result = await check_ocg_maturity_gate(project.id, db_session)
    assert result is None


# =============================================================================
# Guard: execute_run integra evaluate_ocg_maturity
# =============================================================================


def test_execute_run_imports_evaluate_ocg_maturity():
    """Guard: execute_run em scaffold_run_service.py importa evaluate_ocg_maturity."""
    from pathlib import Path

    src = (
        Path(__file__).parent.parent
        / "services"
        / "scaffold_run_service.py"
    ).read_text(encoding="utf-8")

    assert "from app.services.ocg_gate import evaluate_ocg_maturity" in src, (
        "execute_run não importa evaluate_ocg_maturity — DT-082 incompleta"
    )


def test_execute_run_marks_failed_status_with_canonical_prefix_when_gate_blocks():
    """Guard: execute_run tem branch que marca run.status='failed' + prefixo
    `[ocg_gate:` no error quando gate bloqueia.

    DT-083 (2026-05-03) corrigiu DT-082: status original 'blocked' violava
    `scaffold_runs_status_check`. Agora usa 'failed' + prefixo canônico no
    error, permitindo que a métrica `gca_codegen_blocked_total{block_level}`
    parseie sem migration.
    """
    from pathlib import Path

    src = (
        Path(__file__).parent.parent
        / "services"
        / "scaffold_run_service.py"
    ).read_text(encoding="utf-8")

    assert 'run.status = "failed"' in src, (
        "execute_run não marca run.status='failed' no branch do gate — "
        "DT-082+DT-083 incompletas"
    )
    assert '[ocg_gate:' in src, (
        "Prefixo canônico '[ocg_gate:' ausente no error — métrica DT-083 não popula"
    )
    assert 'scaffold_run.blocked_by_ocg_gate' in src, (
        "Log canônico 'scaffold_run.blocked_by_ocg_gate' ausente"
    )
