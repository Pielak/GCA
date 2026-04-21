"""MVP 13 Fase 13.5 — Helpers canônicos por domínio.

Contrato §7 MVP 13 Fase 13.5:
- `AuditEvents` ganha constantes canônicas de projeto, questionário e
  CodeGen.
- `AuditService` ganha 3 helpers: `log_project_event`,
  `log_questionnaire_event`, `log_codegen_event`.
- Cada helper valida whitelist de event_type + monta payload canônico.

Fase 13.6 instrumenta projeto+questionário; Fase 13.7 instrumenta
OCG+CodeGen + chain integrity E2E. Este arquivo cobre apenas
shape/validação dos helpers.
"""
import json
from uuid import uuid4

import pytest


# ─── AuditEvents canônicos ────────────────────────────────────────────


@pytest.mark.parametrize("const_name,expected_value", [
    ("PROJECT_APPROVED", "project_approved"),
    ("PROJECT_REJECTED", "project_rejected"),
    ("PROJECT_STATUS_CHANGED", "project_status_changed"),
    ("QUESTIONNAIRE_APPROVED", "questionnaire_approved"),
    ("QUESTIONNAIRE_REJECTED", "questionnaire_rejected"),
    ("CODEGEN_SCAFFOLD_GENERATED", "codegen_scaffold_generated"),
    ("CODEGEN_SCAFFOLD_APPLIED", "codegen_scaffold_applied"),
    ("CODEGEN_FILE_REGENERATED", "codegen_file_regenerated"),
])
def test_audit_events_canonicos_registrados(const_name, expected_value):
    from app.services.audit_service import AuditEvents
    assert getattr(AuditEvents, const_name) == expected_value


# ─── log_project_event ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_project_event_aceita_approved():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditEvents, AuditService

    project_id = uuid4()
    async with AsyncSessionLocal() as session:
        entry = await AuditService(session).log_project_event(
            event_type=AuditEvents.PROJECT_APPROVED,
            actor_id=None,
            project_id=project_id,
            action="approve",
            old_status="pending",
            new_status="active",
        )
        assert entry.event_type == "project_approved"
        assert entry.resource_type == "project"
        assert entry.resource_id == project_id
        details = json.loads(entry.details)
        assert details["project_id"] == str(project_id)
        assert details["old_status"] == "pending"
        assert details["new_status"] == "active"
        assert details["action"] == "approve"
        await session.rollback()


@pytest.mark.asyncio
async def test_log_project_event_rejeita_event_type_fora_whitelist():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditService

    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await AuditService(session).log_project_event(
                event_type="role_granted",  # pertence a outro domínio
                actor_id=None,
                project_id=uuid4(),
                action="x",
            )


@pytest.mark.asyncio
async def test_log_project_event_extra_preservado():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditEvents, AuditService

    async with AsyncSessionLocal() as session:
        entry = await AuditService(session).log_project_event(
            event_type=AuditEvents.PROJECT_STATUS_CHANGED,
            actor_id=None,
            project_id=uuid4(),
            action="pause",
            old_status="active",
            new_status="paused",
            extra={"reason": "admin_request", "ticket_id": "abc-123"},
        )
        details = json.loads(entry.details)
        assert details["extra"] == {"reason": "admin_request", "ticket_id": "abc-123"}
        await session.rollback()


# ─── log_questionnaire_event ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_questionnaire_event_aceita_approved():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditEvents, AuditService

    project_id = uuid4()
    quest_id = uuid4()
    async with AsyncSessionLocal() as session:
        entry = await AuditService(session).log_questionnaire_event(
            event_type=AuditEvents.QUESTIONNAIRE_APPROVED,
            actor_id=None,
            project_id=project_id,
            questionnaire_id=quest_id,
            action="auto_approve",
            score=95.5,
        )
        assert entry.event_type == "questionnaire_approved"
        assert entry.resource_type == "questionnaire"
        assert entry.resource_id == quest_id
        details = json.loads(entry.details)
        assert details["project_id"] == str(project_id)
        assert details["questionnaire_id"] == str(quest_id)
        assert details["score"] == 95.5
        await session.rollback()


@pytest.mark.asyncio
async def test_log_questionnaire_event_rejeita_event_type_fora_whitelist():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditService

    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await AuditService(session).log_questionnaire_event(
                event_type="project_approved",
                actor_id=None,
                project_id=uuid4(),
                questionnaire_id=uuid4(),
                action="x",
            )


# ─── log_codegen_event ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_codegen_event_scaffold_generated():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditEvents, AuditService

    project_id = uuid4()
    async with AsyncSessionLocal() as session:
        entry = await AuditService(session).log_codegen_event(
            event_type=AuditEvents.CODEGEN_SCAFFOLD_GENERATED,
            actor_id=None,
            project_id=project_id,
            action="generate",
            files_count=23,
        )
        assert entry.event_type == "codegen_scaffold_generated"
        assert entry.resource_type == "codegen"
        assert entry.resource_id == project_id
        details = json.loads(entry.details)
        assert details["files_count"] == 23
        assert details["file_path"] is None
        await session.rollback()


@pytest.mark.asyncio
async def test_log_codegen_event_file_regenerated_com_commit_sha():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditEvents, AuditService

    async with AsyncSessionLocal() as session:
        entry = await AuditService(session).log_codegen_event(
            event_type=AuditEvents.CODEGEN_FILE_REGENERATED,
            actor_id=None,
            project_id=uuid4(),
            action="regenerate",
            file_path="src/services/payments.py",
            commit_sha="abc1234def5678",
        )
        details = json.loads(entry.details)
        assert details["file_path"] == "src/services/payments.py"
        assert details["commit_sha"] == "abc1234def5678"
        await session.rollback()


@pytest.mark.asyncio
async def test_log_codegen_event_rejeita_event_type_fora_whitelist():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditService

    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await AuditService(session).log_codegen_event(
                event_type="role_granted",
                actor_id=None,
                project_id=uuid4(),
                action="x",
            )
