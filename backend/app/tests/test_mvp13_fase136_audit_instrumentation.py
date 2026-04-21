"""MVP 13 Fase 13.6 — Instrumentação de audit em projeto + questionário.

Contrato §7 MVP 13 Fase 13.6:
- `reject_project_request`: emite PROJECT_REJECTED via log_project_event.
- `set_project_status`: emite PROJECT_STATUS_CHANGED.
- `submit_questionnaire`: emite QUESTIONNAIRE_SUBMITTED sempre +
  QUESTIONNAIRE_APPROVED/REJECTED conforme score.

Testes validam que os eventos são gravados em audit_log_global após
cada operação, com payload canônico.
"""
import inspect
import json

import pytest


# ─── Verifica que os pontos alvo usam os helpers ──────────────────────


def test_reject_project_request_usa_log_project_event():
    from app.services import admin_service
    src = inspect.getsource(admin_service.AdminService.reject_project_request)
    assert "log_project_event" in src
    assert "PROJECT_REJECTED" in src


def test_set_project_status_usa_log_project_event():
    from app.services import admin_management_service
    src = inspect.getsource(admin_management_service.set_project_status)
    assert "log_project_event" in src
    assert "PROJECT_STATUS_CHANGED" in src


def test_submit_questionnaire_usa_audit_canonico():
    from app.services import questionnaire_service
    src = inspect.getsource(questionnaire_service.QuestionnaireService.submit_questionnaire)
    assert "QUESTIONNAIRE_SUBMITTED" in src
    assert "log_questionnaire_event" in src
    assert "QUESTIONNAIRE_APPROVED" in src
    assert "QUESTIONNAIRE_REJECTED" in src


# ─── Instrumentação end-to-end de reject_project_request ─────────────


@pytest.mark.asyncio
async def test_reject_project_request_grava_audit_log_global():
    """Valida que rejeitar projeto grava PROJECT_REJECTED em audit_log_global."""
    from datetime import datetime
    from uuid import uuid4

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.database import AsyncSessionLocal
    from app.models.base import GlobalAuditLog, User
    from app.models.onboarding import ProjectRequest, ProjectRequestStatus
    from app.services.admin_service import AdminService

    admin_id = uuid4()
    gp_id = uuid4()
    request_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(id=admin_id, email=f"mvp13-f136-admin-{admin_id.hex[:6]}@test.com",
                             password_hash=hash_password("T@1234"), full_name="A",
                             is_active=True, is_admin=True, created_at=datetime.utcnow()))
            session.add(User(id=gp_id, email=f"mvp13-f136-gp-{gp_id.hex[:6]}@test.com",
                             password_hash=hash_password("T@1234"), full_name="G",
                             is_active=True, is_admin=False, created_at=datetime.utcnow()))
            await session.flush()
            session.add(ProjectRequest(
                id=request_id, gp_id=gp_id,
                project_name=f"F136 {request_id.hex[:6]}",
                project_slug=f"f136-{request_id.hex[:6]}",
                description="desc", deliverable_type="new_system",
                status=ProjectRequestStatus.PENDING,
                requested_at=datetime.utcnow(),
            ))

    try:
        async with AsyncSessionLocal() as session:
            await AdminService(session).reject_project_request(
                request_id=request_id,
                admin_id=admin_id,
                reason="fora do escopo",
            )

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GlobalAuditLog).where(
                    (GlobalAuditLog.event_type == "project_rejected")
                    & (GlobalAuditLog.actor_id == admin_id)
                )
            )
            entry = res.scalar_one_or_none()
            assert entry is not None, "PROJECT_REJECTED não gravado"
            assert entry.resource_type == "project"
            details = json.loads(entry.details)
            assert details["old_status"] == "pending"
            assert details["new_status"] == "rejected"
            assert details["extra"]["reason"] == "fora do escopo"
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    GlobalAuditLog.__table__.delete().where(
                        GlobalAuditLog.actor_id.in_([admin_id])
                    )
                )
                await session.execute(ProjectRequest.__table__.delete().where(ProjectRequest.id == request_id))
                await session.execute(User.__table__.delete().where(User.id.in_([admin_id, gp_id])))


# ─── Instrumentação end-to-end de set_project_status ─────────────────


@pytest.mark.asyncio
async def test_set_project_status_grava_audit_log_global():
    from datetime import datetime
    from uuid import uuid4

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.database import AsyncSessionLocal
    from app.models.base import GlobalAuditLog, Organization, Project, User
    from app.services.admin_management_service import set_project_status

    admin_id = uuid4()
    org_id = uuid4()
    project_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(id=admin_id, email=f"mvp13-f136-lifecycle-{admin_id.hex[:6]}@test.com",
                             password_hash=hash_password("T@1234"), full_name="A",
                             is_active=True, is_admin=True, created_at=datetime.utcnow()))
            session.add(Organization(id=org_id, name=f"Org {org_id.hex[:6]}",
                                     slug=f"org-f136-{org_id.hex[:6]}", owner_id=admin_id,
                                     is_active=True, created_at=datetime.utcnow()))
            await session.flush()
            session.add(Project(id=project_id, organization_id=org_id,
                                name=f"P f136 {project_id.hex[:6]}",
                                slug=f"p-f136-{project_id.hex[:6]}",
                                status="active", deliverable_type="new_system",
                                created_at=datetime.utcnow()))

    try:
        async with AsyncSessionLocal() as session:
            await set_project_status(
                session,
                project_id=project_id,
                new_status="paused",
                actor_id=admin_id,
                reason="manutenção mensal",
            )

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GlobalAuditLog).where(
                    (GlobalAuditLog.event_type == "project_status_changed")
                    & (GlobalAuditLog.actor_id == admin_id)
                )
            )
            entry = res.scalar_one_or_none()
            assert entry is not None
            details = json.loads(entry.details)
            assert details["old_status"] == "active"
            assert details["new_status"] == "paused"
            assert details["extra"]["reason"] == "manutenção mensal"
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    GlobalAuditLog.__table__.delete().where(
                        GlobalAuditLog.actor_id.in_([admin_id])
                    )
                )
                await session.execute(Project.__table__.delete().where(Project.id == project_id))
                await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
                await session.execute(User.__table__.delete().where(User.id == admin_id))
