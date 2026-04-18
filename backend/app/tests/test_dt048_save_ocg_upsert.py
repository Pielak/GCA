"""
DT-048: UPSERT em `AgentService.save_ocg`.

Antes: `save_ocg` fazia INSERT cego. Com `UNIQUE(questionnaire_id)` no
schema, Regenerate OCG sempre morria com `UniqueViolationError`.

Fix: detectar OCG existente por questionnaire_id; UPDATE in-place
preservando `id` (FKs de logs intactos), incrementando `version`, marcando
`change_type=REGENERATED`.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OCG, Questionnaire
from app.services.agent_service import AgentService
from app.schemas.ocg import OCGResponse
from app.tests.factories import create_test_organization, create_test_project


async def _make_questionnaire(db: AsyncSession):
    org = await create_test_organization(db)
    project = await create_test_project(db, organization_id=org.id)
    q_id = uuid4()
    q = Questionnaire(
        id=q_id,
        project_id=project.id,
        gp_email="test@example.com",
        responses=json.dumps({"1": "Test Project"}),
        status="approved",
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(q)
    await db.flush()
    return project, q


def _make_ocg_response(q_id, project_id, overall=75.0):
    return OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=q_id,
        project_id=project_id,
        generated_at=datetime.now(timezone.utc),
        PROJECT_PROFILE={"name": "Test"},
        PILLAR_SCORES={f"P{i}": {"score": overall} for i in range(1, 8)},
        COMPOSITE_SCORE={"overall": overall, "status": "READY"},
        STACK_RECOMMENDATION={"source": "test"},
        CRITICAL_FINDINGS=[],
        TESTING_REQUIREMENTS={},
        COMPLIANCE_CHECKLIST=[],
        DELIVERABLES={},
        ARCHITECTURE_OVERVIEW={},
        RISK_ANALYSIS={},
        APPROVAL_STATUS={"status": "READY"},
    )


@pytest.mark.asyncio
async def test_save_ocg_inserts_first_time(db_session: AsyncSession):
    """Primeira chamada para um questionário: INSERT novo OCG."""
    svc = AgentService(db_session)
    project, q = await _make_questionnaire(db_session)

    resp = _make_ocg_response(q.id, project.id, overall=75.0)
    first_id = resp.ocg_id
    saved = await svc.save_ocg(resp)

    assert saved.id == first_id
    assert saved.questionnaire_id == q.id
    assert saved.overall_score == 75.0
    assert saved.version == 1
    # generate_ocg inicial não marca change_type explicitamente
    assert saved.change_type in ("INITIAL", None)


@pytest.mark.asyncio
async def test_save_ocg_upserts_second_time(db_session: AsyncSession):
    """Segunda chamada para o mesmo questionário: UPDATE in-place.

    Preserva id, incrementa version, marca change_type=REGENERATED.
    Não levanta UniqueViolationError.
    """
    svc = AgentService(db_session)
    project, q = await _make_questionnaire(db_session)

    # Primeiro save
    first_resp = _make_ocg_response(q.id, project.id, overall=70.0)
    first_saved = await svc.save_ocg(first_resp)
    original_id = first_saved.id
    original_generated_at = first_saved.generated_at

    # Segundo save (regenerate) — novo uuid4 no ocg_response, score diferente
    second_resp = _make_ocg_response(q.id, project.id, overall=90.0)
    second_saved = await svc.save_ocg(second_resp)

    # Regra binária: mesmo id, version incrementado, score atualizado
    assert second_saved.id == original_id, (
        "DT-048: UPDATE deve preservar id. Mudança de id quebraria FKs "
        "em ocg_analysis_log e ocg_delta_log."
    )
    assert second_saved.version == 2
    assert second_saved.overall_score == 90.0
    assert second_saved.change_type == "REGENERATED"
    # generated_at permanece o original (não é a data da regeneração)
    assert second_saved.generated_at == original_generated_at

    # ocg_response.ocg_id foi sincronizado pelo save_ocg (caller usa isso em log_analysis)
    assert second_resp.ocg_id == original_id

    # Confirmar que só existe 1 OCG pra esse questionário
    all_ocgs = (await db_session.execute(
        select(OCG).where(OCG.questionnaire_id == q.id)
    )).scalars().all()
    assert len(all_ocgs) == 1


@pytest.mark.asyncio
async def test_save_ocg_third_regeneration_bumps_version_again(db_session: AsyncSession):
    """Regeneração seguida deve continuar subindo version."""
    svc = AgentService(db_session)
    project, q = await _make_questionnaire(db_session)

    await svc.save_ocg(_make_ocg_response(q.id, project.id, overall=60.0))
    await svc.save_ocg(_make_ocg_response(q.id, project.id, overall=70.0))
    third = await svc.save_ocg(_make_ocg_response(q.id, project.id, overall=85.0))

    assert third.version == 3
    assert third.overall_score == 85.0
