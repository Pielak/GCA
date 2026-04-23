"""MVP 24 Fase 24.4 — Testes do cascateamento ativo pós-questionário.

Cobre:
  - AuditEvents.RNF_QUESTIONNAIRE_APPLIED registrado após aplicação.
  - propagate_questionnaire_impact_task.delay disparado com payload correto.
  - Questionário vazio (sem applied/info_debt/complements) NÃO dispara cascata.
  - Falha de enqueue NÃO quebra aplicação (log + segue).
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis, GatekeeperItem, GlobalAuditLog, IngestedDocument,
    Organization, Project, User,
)
from app.services.arguider_questionnaire_parser import (
    ItemAnswer, ParsedQuestionnaire, apply_parsed_responses,
)
from app.services.audit_service import AuditEvents


async def _mk_user_proj_analysis(session):
    uniq = uuid4().hex[:6]
    user = User(
        id=uuid4(), email=f"p244-{uniq}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="P244", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    org = Organization(
        id=uuid4(), name=f"P244-Org-{uniq}", slug=f"p244-{uniq}",
        owner_id=user.id, is_active=True, created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name=f"P244 {uniq}", slug=f"p244-p-{uniq}",
        description="t", deliverable_type="web_app",
        status="active", created_at=datetime.utcnow(),
    )
    session.add(project)
    doc = IngestedDocument(
        id=uuid4(), project_id=project.id,
        filename=f"{uuid4().hex}.pdf", original_filename="req.pdf",
        file_type="pdf", file_hash="0" * 64, file_size_bytes=100,
        uploaded_by=user.id,
    )
    session.add(doc)
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=project.id,
        llm_model="test-model", tokens_used=0, latency_ms=1,
    )
    session.add(analysis)
    await session.flush()
    return user, project, analysis


async def _mk_pending(session, project, analysis, code: str, data: dict | None = None):
    item = GatekeeperItem(
        id=uuid4(), project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type="gap", item_id_in_analysis=code,
        item_data=json.dumps(data or {"text": f"Pergunta {code}"}, ensure_ascii=False),
        status="pending",
    )
    session.add(item)
    await session.flush()
    return item


@pytest.mark.asyncio
async def test_aplicacao_dispara_celery_e_audit(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending(db_session, project, analysis, "G300")

    parsed = ParsedQuestionnaire(
        answers=(ItemAnswer(item_id=str(item.id), text="resposta"),),
        offered_ids=(str(item.id),),
    )
    with patch(
        "app.tasks.pipeline.propagate_questionnaire_impact_task.delay"
    ) as mock_delay:
        report = await apply_parsed_responses(
            db_session, project.id, user.id, parsed,
        )

    assert report.applied == 1
    # Task disparada com payload canônico
    mock_delay.assert_called_once()
    args = mock_delay.call_args.args
    assert args[0] == str(project.id)
    payload = args[1]
    assert payload["applied"] == 1
    assert "G300" in payload["resolved_codes"]

    # Audit canônico emitido
    audit_rows = (await db_session.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.event_type == AuditEvents.RNF_QUESTIONNAIRE_APPLIED,
            GlobalAuditLog.resource_id == project.id,
        )
    )).scalars().all()
    assert len(audit_rows) == 1
    details = json.loads(audit_rows[0].details or "{}")
    assert details["applied"] == 1
    assert details["project_id"] == str(project.id)


@pytest.mark.asyncio
async def test_questionario_vazio_nao_dispara_cascata(db_session: AsyncSession):
    user, project, _ = await _mk_user_proj_analysis(db_session)
    parsed = ParsedQuestionnaire()  # vazio

    with patch(
        "app.tasks.pipeline.propagate_questionnaire_impact_task.delay"
    ) as mock_delay:
        report = await apply_parsed_responses(
            db_session, project.id, user.id, parsed,
        )

    assert report.applied == 0
    assert not mock_delay.called

    # Nenhum audit RNF_QUESTIONNAIRE_APPLIED
    audit_rows = (await db_session.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.event_type == AuditEvents.RNF_QUESTIONNAIRE_APPLIED,
            GlobalAuditLog.resource_id == project.id,
        )
    )).scalars().all()
    assert audit_rows == []


@pytest.mark.asyncio
async def test_info_debt_isolado_dispara_cascata(db_session: AsyncSession):
    """Mesmo sem answers, se skipped provoca info_debt, cascata dispara."""
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending(
        db_session, project, analysis, "G301",
        data={"text": "Pergunta ignorada", "skip_count": 1},
    )

    parsed = ParsedQuestionnaire(
        answers=(),
        offered_ids=(str(item.id),),  # oferecido mas sem answer
    )
    with patch(
        "app.tasks.pipeline.propagate_questionnaire_impact_task.delay"
    ) as mock_delay:
        report = await apply_parsed_responses(
            db_session, project.id, user.id, parsed,
        )

    assert report.applied == 0
    assert str(item.id) in report.info_debt_promoted
    mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_falha_na_celery_nao_quebra_aplicacao(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending(db_session, project, analysis, "G302")

    parsed = ParsedQuestionnaire(
        answers=(ItemAnswer(item_id=str(item.id), text="resposta"),),
        offered_ids=(str(item.id),),
    )
    with patch(
        "app.tasks.pipeline.propagate_questionnaire_impact_task.delay",
        side_effect=RuntimeError("broker down"),
    ):
        # Não pode levantar — cascata é best-effort, aplicação segue
        report = await apply_parsed_responses(
            db_session, project.id, user.id, parsed,
        )

    assert report.applied == 1
    await db_session.refresh(item)
    assert item.status == "resolved"
