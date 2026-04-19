"""MVP 6 Emenda 2026-04-19 — testes de anexos + section/flow + Sustentação.

Cobertura:
- flow_description obrigatório
- section_reference opcional, truncado a 300
- Sustentação (is_support) recebe tickets target=admin junto com Admin
- Admin HERDA Support (is_admin=True já inclui nas queries de support)
- Support puro vê /admin/incidents mas não é Admin
- Anexo: validação tamanho/tipo/contagem máxima, sha256, sanitização de nome
- Delete de anexo: autor OU Admin. Support-puro não deleta anexo alheio.
- set_support_flag: só Admin
"""
from uuid import uuid4
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.base import (
    IncidentTicket,
    IncidentTicketAttachment,
    ProjectMember,
    User,
)
from app.services import incident_ticket_service as svc
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


async def _add_member(db, project_id, user_id, role):
    from datetime import datetime, timezone
    m = ProjectMember(
        id=uuid4(),
        project_id=project_id,
        user_id=user_id,
        role=role,
        accepted_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _make_ticket(db, project_id, author_id, **overrides):
    """Helper: cria ticket com defaults sanos + flow_description sempre."""
    defaults = dict(
        title="T",
        description="d",
        category="bug",
        priority="media",
        flow_description="estava fazendo X e o erro apareceu",
    )
    defaults.update(overrides)
    return await svc.create_ticket(
        db, project_id=project_id, author_id=author_id, **defaults,
    )


# ─── flow_description obrigatório ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_flow_description_required(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-flow-req")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")

    with pytest.raises(ValueError, match="flow_description"):
        await svc.create_ticket(
            db_session, project_id=project.id, author_id=dev.id,
            title="x", description="y", category="bug", priority="baixa",
            flow_description="",
        )


@pytest.mark.asyncio
async def test_section_reference_stored_and_truncated(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-sect")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")

    long_section = "/projects/" + ("x" * 400)
    t = await _make_ticket(
        db_session, project.id, dev.id,
        section_reference=long_section,
    )
    assert t.section_reference is not None
    assert len(t.section_reference) == 300


# ─── Sustentação herda Admin (scope=admin) ────────────────────────────────

@pytest.mark.asyncio
async def test_support_user_receives_admin_scoped_ticket_notifications(db_session):
    """GP abre ticket → target=admin → tanto Admin como Support recebem notif."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-sup-notif")
    gp = await create_test_user(db_session, is_admin=False)
    admin = await create_test_user(db_session, is_admin=True, is_active=True)
    # Support puro
    support = await create_test_user(db_session, is_admin=False)
    support.is_support = True
    await db_session.flush()
    await _add_member(db_session, project.id, gp.id, "gp")

    t = await _make_ticket(
        db_session, project.id, gp.id,
        title="GP escalou", priority="alta",
    )
    assert t.target_scope == "admin"

    # Ambos receberam notif
    from app.models.base import UserNotification
    for uid in (admin.id, support.id):
        notifs = (await db_session.execute(
            select(UserNotification).where(
                UserNotification.user_id == uid,
                UserNotification.event_type == "incident_ticket.opened",
            )
        )).scalars().all()
        assert len(notifs) == 1, f"user {uid} não recebeu notif"


@pytest.mark.asyncio
async def test_support_can_read_admin_ticket(db_session):
    """Support-puro (não-admin) lê ticket escalado a admin."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-sup-read")
    gp = await create_test_user(db_session, is_admin=False)
    support = await create_test_user(db_session, is_admin=False)
    support.is_support = True
    await db_session.flush()
    await _add_member(db_session, project.id, gp.id, "gp")

    t = await _make_ticket(db_session, project.id, gp.id)
    ticket, _ = await svc.get_ticket(db_session, ticket_id=t.id, requester_id=support.id)
    assert ticket.id == t.id


@pytest.mark.asyncio
async def test_support_flag_set_and_unset(db_session):
    admin = await create_test_user(db_session, is_admin=True)
    target = await create_test_user(db_session, is_admin=False)

    u = await svc.set_support_flag(
        db_session, target_user_id=target.id, new_value=True, actor_id=admin.id,
    )
    assert u.is_support is True
    assert u.is_admin is False  # não promove a admin

    u2 = await svc.set_support_flag(
        db_session, target_user_id=target.id, new_value=False, actor_id=admin.id,
    )
    assert u2.is_support is False


@pytest.mark.asyncio
async def test_non_admin_cannot_set_support_flag(db_session):
    support = await create_test_user(db_session, is_admin=False)
    support.is_support = True
    await db_session.flush()
    target = await create_test_user(db_session, is_admin=False)

    with pytest.raises(PermissionError, match="Admin"):
        await svc.set_support_flag(
            db_session, target_user_id=target.id, new_value=True, actor_id=support.id,
        )


@pytest.mark.asyncio
async def test_admin_in_support_list(db_session):
    """list_support_team inclui Admins ativos E Supports ativos."""
    admin = await create_test_user(db_session, is_admin=True, full_name="Admin A")
    support = await create_test_user(db_session, is_admin=False, full_name="Sup A")
    support.is_support = True
    await db_session.flush()

    members = await svc.list_support_team(db_session)
    ids = {u.id for u in members}
    assert admin.id in ids
    assert support.id in ids


# ─── Anexos ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_attachment_writes_file_and_row(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)

    content = b"PNG\x00fake"
    att = await svc.upload_attachment(
        db_session,
        ticket_id=t.id, uploader_id=dev.id,
        filename="erro.png", mime="image/png",
        content=content,
    )
    assert att.size_bytes == len(content)
    assert att.sha256 and len(att.sha256) == 64

    full = Path(tmp_path) / att.storage_path
    assert full.exists()
    assert full.read_bytes() == content


@pytest.mark.asyncio
async def test_attachment_rejects_oversize(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-big")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)

    giant = b"0" * (svc.ATTACHMENT_MAX_BYTES + 1)
    with pytest.raises(ValueError, match="limite"):
        await svc.upload_attachment(
            db_session, ticket_id=t.id, uploader_id=dev.id,
            filename="huge.log", mime="text/plain", content=giant,
        )


@pytest.mark.asyncio
async def test_attachment_rejects_bad_mime(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-mime")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)

    with pytest.raises(ValueError, match="MIME"):
        await svc.upload_attachment(
            db_session, ticket_id=t.id, uploader_id=dev.id,
            filename="shell.sh", mime="application/x-sh", content=b"#!/bin/sh\n",
        )


@pytest.mark.asyncio
async def test_attachment_count_cap(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-cap")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)

    for i in range(svc.ATTACHMENT_MAX_PER_TICKET):
        await svc.upload_attachment(
            db_session, ticket_id=t.id, uploader_id=dev.id,
            filename=f"e{i}.txt", mime="text/plain", content=b"ok",
        )
    # próximo dispara
    with pytest.raises(ValueError, match="máximo"):
        await svc.upload_attachment(
            db_session, ticket_id=t.id, uploader_id=dev.id,
            filename="extra.txt", mime="text/plain", content=b"nop",
        )


@pytest.mark.asyncio
async def test_read_attachment_sha_verifies(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-sha")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)

    att = await svc.upload_attachment(
        db_session, ticket_id=t.id, uploader_id=dev.id,
        filename="a.txt", mime="text/plain", content=b"original",
    )

    # adulteramos o arquivo no disco
    full = Path(tmp_path) / att.storage_path
    full.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="SHA256"):
        svc.read_attachment_bytes(att)


@pytest.mark.asyncio
async def test_filename_sanitized(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-name")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)

    att = await svc.upload_attachment(
        db_session, ticket_id=t.id, uploader_id=dev.id,
        filename="Erro crítico de páginä.txt", mime="text/plain", content=b"x",
    )
    # sem espaço, sem acentos
    assert " " not in att.filename
    assert "ä" not in att.filename
    assert att.filename.endswith(".txt")


@pytest.mark.asyncio
async def test_delete_attachment_by_uploader(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-del-own")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)
    att = await svc.upload_attachment(
        db_session, ticket_id=t.id, uploader_id=dev.id,
        filename="x.txt", mime="text/plain", content=b"y",
    )
    await svc.delete_attachment(db_session, attachment_id=att.id, actor_id=dev.id)
    remaining = await svc.list_attachments(db_session, ticket_id=t.id)
    assert remaining == []


@pytest.mark.asyncio
async def test_support_cannot_delete_foreign_attachment(db_session, tmp_path, monkeypatch):
    """Support puro NÃO deleta anexo de outros (só Admin ou autor)."""
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-del-sup")
    dev = await create_test_user(db_session, is_admin=False)
    support = await create_test_user(db_session, is_admin=False)
    support.is_support = True
    await db_session.flush()
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)
    att = await svc.upload_attachment(
        db_session, ticket_id=t.id, uploader_id=dev.id,
        filename="x.txt", mime="text/plain", content=b"y",
    )
    with pytest.raises(PermissionError, match="Admin"):
        await svc.delete_attachment(db_session, attachment_id=att.id, actor_id=support.id)


@pytest.mark.asyncio
async def test_admin_can_delete_foreign_attachment(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "ATTACHMENT_STORAGE_ROOT", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-att-del-adm")
    dev = await create_test_user(db_session, is_admin=False)
    admin = await create_test_user(db_session, is_admin=True)
    await _add_member(db_session, project.id, dev.id, "dev")
    t = await _make_ticket(db_session, project.id, dev.id)
    att = await svc.upload_attachment(
        db_session, ticket_id=t.id, uploader_id=dev.id,
        filename="x.txt", mime="text/plain", content=b"y",
    )
    await svc.delete_attachment(db_session, attachment_id=att.id, actor_id=admin.id)
    remaining = await svc.list_attachments(db_session, ticket_id=t.id)
    assert remaining == []
