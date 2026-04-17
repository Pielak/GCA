"""Testes do gate de setup do projeto (3 pré-requisitos obrigatórios)."""
import uuid
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    User, Organization, Project, ProjectGitConfig, ProjectSettings, Questionnaire,
)
from app.routers.project_setup_router import _check_setup_status
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio


async def _seed_project(db: AsyncSession, name: str) -> uuid.UUID:
    """Cria User + Organization + Project mínimos e devolve project_id."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"owner-{name}@test.local",
        password_hash=hash_password("password123"),
        full_name=f"Owner {name}",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    org = Organization(
        id=uuid.uuid4(),
        name=f"Org {name}",
        slug=f"org-{name}",
        owner_id=user_id,
    )
    db.add(org)
    await db.flush()

    proj = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Proj {name}",
        slug=f"proj-{name}",
        short_slug=f"p-{name}"[:16],
        deliverable_type="web_app",
        status="active",
    )
    db.add(proj)
    await db.flush()
    return proj.id


async def test_setup_status_fresh_project_has_nothing_configured(db_session: AsyncSession):
    pid = await _seed_project(db_session, "fresh")
    status = await _check_setup_status(db_session, pid)
    assert status == {
        "repo_configured": False,
        "llm_configured": False,
        "questionnaire_submitted": False,
        "ready_to_activate": False,
    }


async def test_setup_status_counts_questionnaire_with_responses(db_session: AsyncSession):
    pid = await _seed_project(db_session, "withq")
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=pid,
        gp_email="gp@test.local",
        responses=json.dumps({"1": "nome", "5": "Alta"}),
        status="pending",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(q)
    await db_session.flush()

    status = await _check_setup_status(db_session, pid)
    assert status["questionnaire_submitted"] is True


async def test_setup_status_ignores_empty_questionnaire(db_session: AsyncSession):
    """Questionário com responses='{}' NÃO conta como submetido."""
    pid = await _seed_project(db_session, "emptyq")
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=pid,
        gp_email="gp@test.local",
        responses="{}",
        status="pending",
    )
    db_session.add(q)
    await db_session.flush()

    status = await _check_setup_status(db_session, pid)
    assert status["questionnaire_submitted"] is False


async def test_ready_to_activate_requires_all_three(db_session: AsyncSession):
    pid = await _seed_project(db_session, "all3")

    db_session.add(ProjectGitConfig(
        id=uuid.uuid4(), project_id=pid,
        provider="github", repository_url="https://github.com/test/repo",
        pat_encrypted="fake-pat", connection_verified=True, default_branch="main",
    ))
    db_session.add(ProjectSettings(
        id=uuid.uuid4(), project_id=pid, setting_type="llm",
        settings_json=json.dumps({"provider": "anthropic", "model": "claude-opus-4-6"}),
    ))
    db_session.add(Questionnaire(
        id=uuid.uuid4(), project_id=pid, gp_email="gp@test.local",
        responses=json.dumps({"1": "x"}), status="pending",
        submitted_at=datetime.now(timezone.utc),
    ))
    await db_session.flush()

    status = await _check_setup_status(db_session, pid)
    assert status["ready_to_activate"] is True
    assert status["repo_configured"] is True
    assert status["llm_configured"] is True
    assert status["questionnaire_submitted"] is True
