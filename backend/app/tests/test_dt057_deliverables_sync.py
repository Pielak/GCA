"""
DT-057: `deliverable_registry.sync_from_ocg` tolerante a 2 formatos
do `OCG.DELIVERABLES`.

Histórico: o serviço esperava `OCG.DELIVERABLES` como lista de strings
(`["Arquitetura", "Stack", ...]`). DT-047 introduziu um fallback
determinístico (`_deliverables_from_metadata`) que escreve dict
`{"expected": [...], "output_formats": [...], "source": "..."}` quando
o LLM consolidator omite a chave. Resultado: sync no dogfood inseria
0 deliverables silenciosamente.

Fix: o serviço agora aceita lista (path canônico) e dict (variante DT-047,
extrai de `expected`/`items`/`deliverables`/`list`).
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OCG, ProjectDeliverable
from app.services.deliverable_registry import DeliverableRegistry
from app.tests.factories import create_test_organization, create_test_project


async def _setup_project(db: AsyncSession):
    org = await create_test_organization(db)
    project = await create_test_project(db, organization_id=org.id)
    return project


def _ocg_with_deliverables(deliverables_value, q_id=None):
    """Helper: gera dict OCG mínimo."""
    return {
        "ocg_id": str(uuid4()),
        "questionnaire_id": str(q_id or uuid4()),
        "DELIVERABLES": deliverables_value,
    }


@pytest.mark.asyncio
async def test_sync_accepts_list_of_strings_canonical(db_session: AsyncSession):
    """Path histórico — lista de strings funciona como sempre funcionou."""
    project = await _setup_project(db_session)
    svc = DeliverableRegistry(db_session)

    ocg = _ocg_with_deliverables(["Arquitetura", "Stack", "Doc técnico"])
    counters = await svc.sync_from_ocg(project.id, ocg)

    assert counters["inserted"] == 3
    rows = (await db_session.execute(
        select(ProjectDeliverable).where(ProjectDeliverable.project_id == project.id)
    )).scalars().all()
    names = sorted(r.name for r in rows)
    assert names == ["Arquitetura", "Doc técnico", "Stack"]


@pytest.mark.asyncio
async def test_sync_accepts_dt047_dict_with_expected(db_session: AsyncSession):
    """DT-047 path — dict com `expected: [...]` extrai a lista."""
    project = await _setup_project(db_session)
    svc = DeliverableRegistry(db_session)

    ocg = _ocg_with_deliverables({
        "expected": ["Arquitetura", "Stack", "Doc técnico", "Backlog", "Plano testes"],
        "output_formats": ["Painel GCA", "Markdown", "PDF"],
        "source": "questionnaire_deterministic_fallback",
    })
    counters = await svc.sync_from_ocg(project.id, ocg)

    assert counters["inserted"] == 5
    rows = (await db_session.execute(
        select(ProjectDeliverable).where(ProjectDeliverable.project_id == project.id)
    )).scalars().all()
    assert {r.name for r in rows} == {"Arquitetura", "Stack", "Doc técnico", "Backlog", "Plano testes"}


@pytest.mark.asyncio
async def test_sync_accepts_dict_with_items_alias(db_session: AsyncSession):
    """Alias `items` também funciona (forma alternativa de outras versões)."""
    project = await _setup_project(db_session)
    svc = DeliverableRegistry(db_session)

    ocg = _ocg_with_deliverables({"items": ["A", "B"]})
    counters = await svc.sync_from_ocg(project.id, ocg)
    assert counters["inserted"] == 2


@pytest.mark.asyncio
async def test_sync_returns_zero_on_unknown_dict_shape(db_session: AsyncSession):
    """Dict sem chave conhecida: zero, sem crash, sem falso-positivo."""
    project = await _setup_project(db_session)
    svc = DeliverableRegistry(db_session)

    ocg = _ocg_with_deliverables({"qualquer_outra_coisa": ["A", "B"]})
    counters = await svc.sync_from_ocg(project.id, ocg)
    assert counters["inserted"] == 0
    assert counters["skipped"] == 0


@pytest.mark.asyncio
async def test_sync_returns_zero_when_deliverables_missing(db_session: AsyncSession):
    project = await _setup_project(db_session)
    svc = DeliverableRegistry(db_session)
    counters = await svc.sync_from_ocg(project.id, {"ocg_id": str(uuid4())})
    assert counters["inserted"] == 0
