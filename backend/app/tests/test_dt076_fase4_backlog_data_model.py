"""DT-076 Fase 4 — Backlog gera items a partir do DATA_MODEL.

Cobre:
  - Item de revisão do modelo de dados aparece no backlog (categoria modules).
  - Tabelas não-núcleo viram items individuais.
  - Tabelas núcleo (users/sessions/config/audit_log/consent) NÃO viram items próprios.
  - Warnings do modelo viram items critical.
  - Projeto sem DATA_MODEL não quebra (continua regenerando resto do backlog).
  - Título do item principal cita engine + contagem de tabelas.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import BacklogItem, OCG, Questionnaire
from app.services.backlog_service import BacklogService
from app.services.data_model_inference import infer_data_model
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


async def _seed_ocg_with_data_model(db, *, data_model: dict | None = None,
                                     initiative: str = "E-commerce B2C"):
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(
        db, organization_id=org.id, slug=f"dt076f4-{uuid4().hex[:6]}",
    )
    if data_model is None:
        data_model = infer_data_model(
            {"initiative_type": initiative, "handles_pii": True},
            {"database": {"engine": "PostgreSQL"}},
        )
    q = Questionnaire(
        id=uuid4(), project_id=p.id, gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    db.add(q)
    await db.commit()
    ocg = OCG(
        id=uuid4(), project_id=p.id, questionnaire_id=q.id,
        version=1, change_type="CREATE",
        ocg_data=json.dumps({
            "STACK_RECOMMENDATION": {
                "database": {"engine": "PostgreSQL"},
            },
            "DATA_MODEL": data_model,
        }),
    )
    db.add(ocg)
    await db.commit()
    return p, user


# ────────────────────────────────────────────────────────────────────────
# Cenário feliz
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backlog_gera_item_de_revisao_principal(db_session):
    p, _ = await _seed_ocg_with_data_model(db_session)
    svc = BacklogService(db_session)
    await svc.regenerate_from_ocg(p.id)

    rows = await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == p.id)
    )
    items = rows.scalars().all()
    titles = [i.title for i in items]
    assert any("Revisar modelo de dados" in t for t in titles)


@pytest.mark.asyncio
async def test_backlog_item_principal_cita_engine_e_contagem(db_session):
    p, _ = await _seed_ocg_with_data_model(db_session)
    svc = BacklogService(db_session)
    await svc.regenerate_from_ocg(p.id)

    rows = await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == p.id)
    )
    items = rows.scalars().all()
    revisao = next(
        i for i in items if "Revisar modelo" in i.title
    )
    assert "postgresql" in revisao.title.lower()
    assert "tabelas" in revisao.title.lower()


@pytest.mark.asyncio
async def test_backlog_tabelas_de_dominio_viram_items(db_session):
    """E-commerce gera customers/products/orders/order_items — cada um é um item."""
    p, _ = await _seed_ocg_with_data_model(db_session, initiative="E-commerce B2C")
    svc = BacklogService(db_session)
    await svc.regenerate_from_ocg(p.id)

    rows = await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == p.id)
    )
    titles = [i.title for i in rows.scalars().all()]
    assert any("customers" in t for t in titles)
    assert any("products" in t for t in titles)
    assert any("orders" in t for t in titles)
    assert any("order_items" in t for t in titles)


@pytest.mark.asyncio
async def test_backlog_nao_duplica_items_para_tabelas_nucleo(db_session):
    """users, sessions, config, audit_log, consent não ganham item próprio."""
    p, _ = await _seed_ocg_with_data_model(db_session)
    svc = BacklogService(db_session)
    await svc.regenerate_from_ocg(p.id)

    rows = await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == p.id)
    )
    items = rows.scalars().all()
    # Nenhum item INDIVIDUAL pra tabela users (o principal pode citar, mas
    # não pode existir "Tabela users: ajustar ..." como item separado).
    has_users_specific = any(
        i.title.startswith("Tabela users:") for i in items
    )
    assert not has_users_specific


# ────────────────────────────────────────────────────────────────────────
# Warnings viram items critical
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_warning_engine_nao_suportado_vira_item_critical(db_session):
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "Oracle 19c"}},
    )
    p, _ = await _seed_ocg_with_data_model(db_session, data_model=dm)
    svc = BacklogService(db_session)
    await svc.regenerate_from_ocg(p.id)

    rows = await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == p.id)
    )
    items = rows.scalars().all()
    warning_items = [
        i for i in items if "Modelo de dados:" in i.title and i.priority == "critical"
    ]
    assert len(warning_items) >= 1
    assert any("Oracle" in i.title for i in warning_items)


@pytest.mark.asyncio
async def test_warning_sem_engine_vira_item_critical(db_session):
    dm = infer_data_model({"initiative_type": "generic"}, {"database": {}})
    p, _ = await _seed_ocg_with_data_model(db_session, data_model=dm)
    svc = BacklogService(db_session)
    await svc.regenerate_from_ocg(p.id)

    rows = await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == p.id)
    )
    items = rows.scalars().all()
    assert any(
        "Modelo de dados:" in i.title and i.priority == "critical"
        for i in items
    )


# ────────────────────────────────────────────────────────────────────────
# Robustez
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocg_sem_data_model_nao_quebra(db_session):
    """OCG legado (pré-DT-076) sem DATA_MODEL continua regenerando o resto."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(
        db_session, organization_id=org.id, slug=f"dt076f4-old-{uuid4().hex[:6]}",
    )
    q = Questionnaire(
        id=uuid4(), project_id=p.id, gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    db_session.add(q)
    await db_session.commit()
    ocg = OCG(
        id=uuid4(), project_id=p.id, questionnaire_id=q.id,
        version=1, change_type="CREATE",
        ocg_data=json.dumps({
            "STACK_RECOMMENDATION": {"database": {"engine": "PostgreSQL"}},
            # Sem DATA_MODEL
        }),
    )
    db_session.add(ocg)
    await db_session.commit()

    svc = BacklogService(db_session)
    result = await svc.regenerate_from_ocg(p.id)
    # Regeneração deve ter rodado sem erros
    assert "regenerated" in result
