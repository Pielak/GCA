"""MVP 6 — testes do incident_ticket_service.

Cobertura:
- Roteamento por papel do autor (Dev/Tester/QA → gp; GP/Admin → admin)
- RBAC em leitura (admin vê tudo; GP vê do projeto; dev vê os próprios)
- Cross-projeto: ticket de A não aparece pra membro de B
- Comentário + mudança de status preenchem updated_at / resolved_at
- Notificação in-app é gerada (UserNotification persistido)
- Validação: categoria/prioridade inválida, título vazio
"""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    IncidentTicket,
    IncidentTicketComment,
    ProjectMember,
    UserNotification,
)
from app.services import incident_ticket_service as svc
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


async def _add_member(db, project_id, user_id, role):
    """Helper: adiciona ProjectMember com accepted_at setado."""
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


# ─── Roteamento por papel ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dev_creates_ticket_routed_to_gp(db_session):
    """Dev/Tester/QA abre → target_scope='gp'."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-dev-gp")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")

    ticket = await svc.create_ticket(
        db_session,
        project_id=project.id,
        author_id=dev.id,
        title="Pipeline quebra ao gerar OCG",
        description="Ao clicar em Regenerar OCG retorna 500",
        category="bug",
        priority="alta",
    )
    assert ticket.target_scope == "gp"
    assert ticket.status == "open"
    assert ticket.resolved_at is None


@pytest.mark.asyncio
async def test_gp_creates_ticket_routed_to_admin(db_session):
    """GP abre → target_scope='admin'."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-gp-admin")
    gp = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, gp.id, "gp")

    ticket = await svc.create_ticket(
        db_session,
        project_id=project.id,
        author_id=gp.id,
        title="Necessidade: exportar backlog em CSV",
        description="GP do Time de Jurídico pediu export",
        category="pedido_feature",
        priority="media",
    )
    assert ticket.target_scope == "admin"


@pytest.mark.asyncio
async def test_admin_creates_ticket_routed_to_admin(db_session):
    """Admin global → target_scope='admin' (mesmo sem ser membro)."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-admin")
    admin = await create_test_user(db_session, is_admin=True)

    ticket = await svc.create_ticket(
        db_session,
        project_id=project.id,
        author_id=admin.id,
        title="Revisar retenção de backup",
        description="Retenção atual é 10 — validar se cobre cenário X",
        category="duvida",
        priority="baixa",
    )
    assert ticket.target_scope == "admin"


@pytest.mark.asyncio
async def test_non_member_non_admin_cannot_create(db_session):
    """Usuário sem vínculo e sem is_admin → ValueError."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-foreigner")
    outsider = await create_test_user(db_session, is_admin=False)

    with pytest.raises(ValueError, match="não é membro"):
        await svc.create_ticket(
            db_session,
            project_id=project.id,
            author_id=outsider.id,
            title="x", description="y", category="bug", priority="baixa",
        )


# ─── RBAC em leitura ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dev_sees_only_own_tickets(db_session):
    """Dev vê só os próprios; não vê tickets abertos por outros devs."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-dev-scope")
    dev_a = await create_test_user(db_session, is_admin=False)
    dev_b = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev_a.id, "dev")
    await _add_member(db_session, project.id, dev_b.id, "dev")

    await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev_a.id,
        title="A", description="a", category="bug", priority="media",
    )
    await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev_b.id,
        title="B", description="b", category="bug", priority="media",
    )

    a_sees = await svc.list_for_project(db_session, project_id=project.id, requester_id=dev_a.id)
    b_sees = await svc.list_for_project(db_session, project_id=project.id, requester_id=dev_b.id)

    assert len(a_sees) == 1 and a_sees[0].author_id == dev_a.id
    assert len(b_sees) == 1 and b_sees[0].author_id == dev_b.id


@pytest.mark.asyncio
async def test_gp_sees_all_project_tickets(db_session):
    """GP vê todos os tickets do projeto (target_scope=gp + próprios)."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-gp-scope")
    gp = await create_test_user(db_session, is_admin=False)
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, gp.id, "gp")
    await _add_member(db_session, project.id, dev.id, "dev")

    await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev.id,
        title="D", description="d", category="bug", priority="alta",
    )
    await svc.create_ticket(
        db_session, project_id=project.id, author_id=gp.id,
        title="G", description="g", category="pedido_feature", priority="media",
    )

    seen = await svc.list_for_project(db_session, project_id=project.id, requester_id=gp.id)
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_admin_aggregated_cross_project(db_session):
    """Admin aggregated vê apenas target=admin cross-projeto."""
    org = await create_test_organization(db_session)
    p1 = await create_test_project(db_session, organization_id=org.id, slug="tkt-a")
    p2 = await create_test_project(db_session, organization_id=org.id, slug="tkt-b")
    gp1 = await create_test_user(db_session, is_admin=False)
    gp2 = await create_test_user(db_session, is_admin=False)
    dev1 = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, p1.id, gp1.id, "gp")
    await _add_member(db_session, p2.id, gp2.id, "gp")
    await _add_member(db_session, p1.id, dev1.id, "dev")

    # GP abre em P1 → target=admin
    await svc.create_ticket(
        db_session, project_id=p1.id, author_id=gp1.id,
        title="GP1", description="g1", category="bug", priority="alta",
    )
    # GP abre em P2 → target=admin
    await svc.create_ticket(
        db_session, project_id=p2.id, author_id=gp2.id,
        title="GP2", description="g2", category="duvida", priority="baixa",
    )
    # Dev abre em P1 → target=gp (NÃO deve vir no list_for_admin)
    await svc.create_ticket(
        db_session, project_id=p1.id, author_id=dev1.id,
        title="DEV1", description="d1", category="bug", priority="media",
    )

    admin_view = await svc.list_for_admin(db_session)
    assert len(admin_view) == 2
    assert {t.title for t in admin_view} == {"GP1", "GP2"}

    # Filtro por projeto
    only_p1 = await svc.list_for_admin(db_session, project_id=p1.id)
    assert len(only_p1) == 1 and only_p1[0].title == "GP1"


# ─── Comentários + status ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comment_updates_ticket_and_notifies(db_session):
    """Comentário: cria row + toca updated_at + gera notificação pro autor."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-cmt")
    dev = await create_test_user(db_session, is_admin=False)
    gp = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    await _add_member(db_session, project.id, gp.id, "gp")

    ticket = await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev.id,
        title="Erro X", description="x", category="bug", priority="alta",
    )
    before = ticket.updated_at

    await svc.add_comment(db_session, ticket_id=ticket.id, author_id=gp.id, body="Vou investigar")

    refreshed = (await db_session.execute(
        select(IncidentTicket).where(IncidentTicket.id == ticket.id)
    )).scalar_one()
    assert refreshed.updated_at > before

    comments = (await db_session.execute(
        select(IncidentTicketComment).where(IncidentTicketComment.ticket_id == ticket.id)
    )).scalars().all()
    assert len(comments) == 1 and comments[0].body == "Vou investigar"

    # Autor do ticket recebeu notif do comentário
    notifs = (await db_session.execute(
        select(UserNotification).where(
            UserNotification.user_id == dev.id,
            UserNotification.event_type == "incident_ticket.commented",
        )
    )).scalars().all()
    assert len(notifs) == 1


@pytest.mark.asyncio
async def test_resolve_sets_resolved_fields(db_session):
    """Mudar status para resolved preenche resolved_at + resolved_by."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-resolve")
    dev = await create_test_user(db_session, is_admin=False)
    gp = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    await _add_member(db_session, project.id, gp.id, "gp")

    ticket = await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev.id,
        title="Y", description="y", category="bug", priority="media",
    )

    updated = await svc.update_status(
        db_session, ticket_id=ticket.id, actor_id=gp.id, new_status="resolved",
    )
    assert updated.status == "resolved"
    assert updated.resolved_at is not None
    assert updated.resolved_by == gp.id


@pytest.mark.asyncio
async def test_reopen_clears_resolved_fields(db_session):
    """Reabrir ticket (resolved → in_progress) limpa resolved_at."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-reopen")
    dev = await create_test_user(db_session, is_admin=False)
    gp = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    await _add_member(db_session, project.id, gp.id, "gp")

    ticket = await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev.id,
        title="Z", description="z", category="bug", priority="baixa",
    )
    await svc.update_status(db_session, ticket_id=ticket.id, actor_id=gp.id, new_status="resolved")
    reopened = await svc.update_status(
        db_session, ticket_id=ticket.id, actor_id=gp.id, new_status="in_progress",
    )
    assert reopened.status == "in_progress"
    assert reopened.resolved_at is None
    assert reopened.resolved_by is None


# ─── Notificação na abertura ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_opening_ticket_notifies_gps(db_session):
    """Dev abre → GPs do projeto (não o autor) recebem UserNotification."""
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-notif")
    dev = await create_test_user(db_session, is_admin=False)
    gp1 = await create_test_user(db_session, is_admin=False)
    gp2 = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    await _add_member(db_session, project.id, gp1.id, "gp")
    await _add_member(db_session, project.id, gp2.id, "gp")

    await svc.create_ticket(
        db_session, project_id=project.id, author_id=dev.id,
        title="Bug crítico", description="xyz",
        category="bug", priority="critica",
    )

    for gp_id in (gp1.id, gp2.id):
        notifs = (await db_session.execute(
            select(UserNotification).where(
                UserNotification.user_id == gp_id,
                UserNotification.event_type == "incident_ticket.opened",
            )
        )).scalars().all()
        assert len(notifs) == 1
        assert notifs[0].severity == "error"  # critica → error

    # Autor não recebe notif do próprio ticket
    self_notifs = (await db_session.execute(
        select(UserNotification).where(
            UserNotification.user_id == dev.id,
            UserNotification.event_type == "incident_ticket.opened",
        )
    )).scalars().all()
    assert len(self_notifs) == 0


# ─── Validação ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_category_rejected(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-invcat")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    with pytest.raises(ValueError, match="Categoria"):
        await svc.create_ticket(
            db_session, project_id=project.id, author_id=dev.id,
            title="x", description="y", category="nonsense", priority="baixa",
        )


@pytest.mark.asyncio
async def test_invalid_priority_rejected(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-invprio")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    with pytest.raises(ValueError, match="Prioridade"):
        await svc.create_ticket(
            db_session, project_id=project.id, author_id=dev.id,
            title="x", description="y", category="bug", priority="urgentissimo",
        )


@pytest.mark.asyncio
async def test_empty_title_rejected(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="tkt-emptytitle")
    dev = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, project.id, dev.id, "dev")
    with pytest.raises(ValueError, match="obrigatórios"):
        await svc.create_ticket(
            db_session, project_id=project.id, author_id=dev.id,
            title="   ", description="y", category="bug", priority="baixa",
        )


# ─── Cross-projeto ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_foreign_project_member_denied(db_session):
    """Membro de projeto B não consegue ver ticket de projeto A."""
    org = await create_test_organization(db_session)
    p_a = await create_test_project(db_session, organization_id=org.id, slug="tkt-cross-a")
    p_b = await create_test_project(db_session, organization_id=org.id, slug="tkt-cross-b")
    dev_a = await create_test_user(db_session, is_admin=False)
    gp_b = await create_test_user(db_session, is_admin=False)
    await _add_member(db_session, p_a.id, dev_a.id, "dev")
    await _add_member(db_session, p_b.id, gp_b.id, "gp")

    ticket = await svc.create_ticket(
        db_session, project_id=p_a.id, author_id=dev_a.id,
        title="privado A", description="...", category="bug", priority="baixa",
    )

    # GP do projeto B tenta ver → PermissionError
    with pytest.raises(PermissionError):
        await svc.get_ticket(db_session, ticket_id=ticket.id, requester_id=gp_b.id)

    # Listagem do projeto A para GP do projeto B → lista vazia
    lst = await svc.list_for_project(db_session, project_id=p_a.id, requester_id=gp_b.id)
    assert lst == []
