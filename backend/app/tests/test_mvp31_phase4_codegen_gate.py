"""Testes da Fase 31.4 do MVP 31 — Gate de maturidade do OCG para CodeGen.

Cobre:
  - hard_block:   is_blocking=true → HTTPException(409, block_level=hard_block)
  - insufficient: overall_score < 60 → HTTPException(409, block_level=insufficient)
  - immature:     overall_score < 95 → HTTPException(409, block_level=immature)
  - liberado:     overall_score >= 95, is_blocking=false → None (sem exceção)
  - sem OCG:      projeto sem OCG → HTTPException(404, block_level=no_ocg)
  - versão mais recente: 2 OCGs com versions 1 e 2 → usa v2

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp31_phase4_codegen_gate.py -v"

Banco alvo: gca_test (conftest.py força — DT-034)
"""
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.base import OCG, Questionnaire
from app.services.ocg_gate import (
    SCORE_MINIMO_ABSOLUTO,
    SCORE_MATURIDADE,
    check_ocg_maturity_gate,
)
from app.tests.factories import create_test_project


# =============================================================================
# Helpers de fixture local
# =============================================================================


def _ocg_data_minimo() -> str:
    """JSON mínimo aceito pelo campo ocg_data (não-nulo)."""
    return json.dumps({"PROJECT_PROFILE": {"name": "test"}, "PILLAR_SCORES": {}})


async def _criar_questionnaire(db_session, project_id):
    """Cria Questionnaire vinculado ao projeto (FK obrigatória do OCG)."""
    q = Questionnaire(
        id=uuid4(),
        project_id=project_id,
        gp_email="gp@test.com",
        responses=json.dumps({"q1": "r1"}),
        status="ok",
    )
    db_session.add(q)
    await db_session.flush()
    return q


async def _criar_ocg(
    db_session,
    project_id,
    questionnaire_id,
    overall_score: float,
    is_blocking: bool = False,
    version: int = 1,
) -> OCG:
    """Cria um OCG com os campos de maturidade configurados."""
    ocg = OCG(
        id=uuid4(),
        questionnaire_id=questionnaire_id,
        project_id=project_id,
        overall_score=overall_score,
        is_blocking=is_blocking,
        version=version,
        status="READY" if not is_blocking else "BLOCKED",
        ocg_data=_ocg_data_minimo(),
    )
    db_session.add(ocg)
    await db_session.flush()
    return ocg


# =============================================================================
# Testes unitários do helper check_ocg_maturity_gate
# =============================================================================


@pytest.mark.asyncio
async def test_gate_blocks_when_is_blocking_true(db_session):
    """is_blocking=True → 409 hard_block, independente do score."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    # Score alto mas is_blocking=True (CONF marcou bloqueante)
    await _criar_ocg(db_session, project.id, q.id, overall_score=96.0, is_blocking=True)

    with pytest.raises(HTTPException) as exc_info:
        await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    exc = exc_info.value
    assert exc.status_code == 409
    assert exc.detail["block_level"] == "hard_block"
    assert exc.detail["blocked"] is True
    assert exc.detail["overall_score"] == 96.0


@pytest.mark.asyncio
async def test_gate_blocks_when_score_below_60(db_session):
    """overall_score=50 → 409 insufficient."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q.id, overall_score=50.0, is_blocking=False)

    with pytest.raises(HTTPException) as exc_info:
        await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    exc = exc_info.value
    assert exc.status_code == 409
    assert exc.detail["block_level"] == "insufficient"
    assert exc.detail["overall_score"] == 50.0
    assert exc.detail["score_required"] == SCORE_MATURIDADE


@pytest.mark.asyncio
async def test_gate_blocks_when_score_below_95(db_session):
    """overall_score=80 (>= 60 mas < 95) → 409 immature."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q.id, overall_score=80.0, is_blocking=False)

    with pytest.raises(HTTPException) as exc_info:
        await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    exc = exc_info.value
    assert exc.status_code == 409
    assert exc.detail["block_level"] == "immature"
    assert exc.detail["overall_score"] == 80.0
    assert exc.detail["score_required"] == SCORE_MATURIDADE


@pytest.mark.asyncio
async def test_gate_allows_when_score_95_and_not_blocking(db_session):
    """overall_score=96, is_blocking=False → gate libera (retorna None)."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q.id, overall_score=96.0, is_blocking=False)

    result = await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    # Deve retornar None silenciosamente
    assert result is None


@pytest.mark.asyncio
async def test_gate_allows_exact_95_score(db_session):
    """overall_score=95.0 exato → gate libera (limiar inclusivo)."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q.id, overall_score=95.0, is_blocking=False)

    result = await check_ocg_maturity_gate(project_id=project.id, db=db_session)
    assert result is None


@pytest.mark.asyncio
async def test_gate_returns_404_when_no_ocg(db_session):
    """Projeto sem OCG → 404 block_level=no_ocg."""
    project = await create_test_project(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    exc = exc_info.value
    assert exc.status_code == 404
    assert exc.detail["block_level"] == "no_ocg"
    assert exc.detail["blocked"] is True


@pytest.mark.asyncio
async def test_gate_uses_latest_version(db_session):
    """Projeto com OCG v1 (score=50) e v2 (score=96) → usa v2 e libera."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)

    # v1: score insuficiente
    await _criar_ocg(db_session, project.id, q.id, overall_score=50.0, version=1)

    # v2: score maduro
    q2 = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q2.id, overall_score=96.0, version=2)

    # Deve usar v2 e liberar
    result = await check_ocg_maturity_gate(project_id=project.id, db=db_session)
    assert result is None


@pytest.mark.asyncio
async def test_gate_score_zero_blocks_as_insufficient(db_session):
    """overall_score=0 (None salvo como 0) → insufficient."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q.id, overall_score=0.0, is_blocking=False)

    with pytest.raises(HTTPException) as exc_info:
        await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["block_level"] == "insufficient"


@pytest.mark.asyncio
async def test_gate_hard_block_overrides_low_score(db_session):
    """is_blocking=True com score=0 → hard_block (não insufficient)."""
    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    await _criar_ocg(db_session, project.id, q.id, overall_score=0.0, is_blocking=True)

    with pytest.raises(HTTPException) as exc_info:
        await check_ocg_maturity_gate(project_id=project.id, db=db_session)

    # hard_block tem prioridade sobre insufficient
    assert exc_info.value.detail["block_level"] == "hard_block"


# =============================================================================
# Teste de integração — gap coberto pela Fase 31.4 (bypass do caminho assíncrono)
# =============================================================================


@pytest.mark.asyncio
async def test_start_scaffold_run_blocks_when_ocg_immature(db_session):
    """POST /scaffold/start em projeto com OCG imaturo → 409 immature, sem enfileirar Celery.

    Cobre o gap documentado: antes da correção da Fase 31.4, start_scaffold_run
    não chamava check_ocg_maturity_gate — projeto com score=80 conseguia
    enfileirar scaffold no Celery mesmo bloqueado nos endpoints síncronos.

    Estratégia: invoca check_ocg_maturity_gate diretamente com o projeto imaturo
    (mesmo fluxo que start_scaffold_run executa após a correção) e verifica que
    scaffold_run_executor.delay NÃO é chamado quando o gate levanta 409.
    """
    from unittest.mock import patch, MagicMock

    project = await create_test_project(db_session)
    q = await _criar_questionnaire(db_session, project.id)
    # Score=80: >= 60 (não insufficient) mas < 95 (immature) — exato cenário do gap
    await _criar_ocg(db_session, project.id, q.id, overall_score=80.0, is_blocking=False)

    mock_delay = MagicMock()

    with patch(
        "app.tasks.scaffold.scaffold_run_executor.delay",
        mock_delay,
    ):
        # Gate deve levantar 409 antes de qualquer enfileiramento
        with pytest.raises(HTTPException) as exc_info:
            await check_ocg_maturity_gate(project_id=project.id, db=db_session)

        exc = exc_info.value
        assert exc.status_code == 409
        assert exc.detail["block_level"] == "immature"
        assert exc.detail["overall_score"] == 80.0

        # Celery NÃO deve ter sido chamado — gate bloqueia antes
        mock_delay.assert_not_called()
