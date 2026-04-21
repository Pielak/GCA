"""MVP 20 Fase 20.1a — testes de foundation do Issue Tracker Bridge.

Valida:
- Migration 035 aplicada: tabela `external_issues` + UNIQUE canônica +
  índices.
- Modelo `ExternalIssue` aceita leitura/escrita dos fields canônicos.
- Idempotência: mesmo (project_id, provider, external_id) só entra 1 vez.
- Porta `IssueTrackerPort` define contrato obrigatório; registry canônico
  funciona (register/get/clear).
- Service `issue_tracker_service`:
    - `upsert_from_payload` cria ou atualiza corretamente (respeita
      UNIQUE; não duplica; atualiza status + synced_at).
    - `list_external_issues` filtra por project_id (compartimentalização).
    - `resolve_adapter` levanta erro explícito quando provider ausente.
    - Métodos ainda-não-implementados (`create_issue_from_module`,
      `apply_webhook_event`) levantam NotImplementedError.
"""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis,
    ExternalIssue,
    IngestedDocument,
    ModuleCandidate,
    Organization,
    Project,
    User,
)
from app.services.issue_tracker_service import (
    get_external_issue_by_external_id,
    list_external_issues,
    resolve_adapter,
    upsert_from_payload,
)
from app.services.ports.issue_tracker_port import (
    IssuePayload,
    IssueTrackerConfigError,
    IssueTrackerPort,
    _clear_registry_for_tests,
    get_adapter,
    register_adapter,
    registered_providers,
)


# ===========================================================================
# Helpers
# ===========================================================================

async def _make_user(db) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        email=f"it-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="IT Tester",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db, user) -> Project:
    org = Organization(
        id=uuid4(),
        name=f"Org {uuid4().hex[:6]}",
        slug=f"org-it-{uuid4().hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="Projeto Issue Tracker",
        slug=f"it-{uuid4().hex[:6]}",
        description="Projeto pra teste de issue tracker.",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


async def _make_module(db, project, user) -> ModuleCandidate:
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        filename=f"{uuid4().hex}.pdf",
        original_filename="req.pdf",
        file_type="pdf",
        file_hash="0" * 64,
        file_size_bytes=100,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        llm_model="claude-3-5-sonnet",
        tokens_used=500,
        latency_ms=200,
    )
    db.add(analysis)
    await db.flush()
    mod = ModuleCandidate(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name="Login",
        description="Login via email+senha",
        module_type="feature",
        priority="high",
    )
    db.add(mod)
    await db.flush()
    return mod


# ===========================================================================
# Migration 035 — schema
# ===========================================================================

@pytest.mark.asyncio
async def test_migration_035_tabela_external_issues_existe(db_session):
    result = await db_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'external_issues' "
            "ORDER BY ordinal_position"
        )
    )
    rows = result.fetchall()
    assert rows, "tabela external_issues não existe — migration 035 não aplicada"
    col_names = {r[0] for r in rows}
    esperados = {
        "id", "project_id", "module_candidate_id", "provider", "external_id",
        "url", "title", "status_canonical", "status_raw", "priority",
        "provider_specific", "created_at", "created_by", "synced_at", "closed_at",
    }
    assert esperados.issubset(col_names), f"faltam colunas: {esperados - col_names}"


@pytest.mark.asyncio
async def test_migration_035_unique_provider_external_id(db_session):
    """Índice UNIQUE (project_id, provider, external_id) garante idempotência."""
    result = await db_session.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = 'external_issues' "
            "AND indexname = 'uniq_external_issue_provider_external_id'"
        )
    )
    row = result.fetchone()
    assert row is not None, "UNIQUE de idempotência ausente"
    indexdef = row[1]
    assert "UNIQUE" in indexdef.upper()
    assert "provider" in indexdef
    assert "external_id" in indexdef
    assert "project_id" in indexdef


# ===========================================================================
# Modelo ExternalIssue — leitura/escrita
# ===========================================================================

@pytest.mark.asyncio
async def test_external_issue_aceita_fields_canonicos(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    mod = await _make_module(db_session, project, user)

    issue = ExternalIssue(
        project_id=project.id,
        module_candidate_id=mod.id,
        provider="jira",
        external_id="PROJ-123",
        url="https://example.atlassian.net/browse/PROJ-123",
        title="RF-001 Login",
        status_canonical="todo",
        status_raw="To Do",
        priority="high",
        provider_specific={"epic_key": "PROJ-1", "sprint_id": 42},
    )
    db_session.add(issue)
    await db_session.flush()

    # reload
    fresh = await get_external_issue_by_external_id(
        db_session, project.id, "jira", "PROJ-123"
    )
    assert fresh is not None
    assert fresh.title == "RF-001 Login"
    assert fresh.status_canonical == "todo"
    assert fresh.provider_specific == {"epic_key": "PROJ-1", "sprint_id": 42}


@pytest.mark.asyncio
async def test_external_issue_unique_constraint_bloqueia_duplicata(db_session):
    """Mesma (project_id, provider, external_id) só pode existir 1 vez."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    a = ExternalIssue(
        project_id=project.id, provider="jira", external_id="DUP-1",
        title="primeira", status_canonical="todo",
    )
    db_session.add(a)
    await db_session.flush()

    b = ExternalIssue(
        project_id=project.id, provider="jira", external_id="DUP-1",
        title="segunda", status_canonical="in_progress",
    )
    db_session.add(b)
    with pytest.raises(Exception):  # IntegrityError via asyncpg
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_external_issue_mesmo_external_id_em_projetos_diferentes_ok(db_session):
    """UNIQUE inclui project_id — compartimentalização §2.2 preservada.

    Projeto A pode ter PROJ-123 (Jira) e projeto B também — são trackers
    diferentes, não conflitam.
    """
    user = await _make_user(db_session)
    proj_a = await _make_project(db_session, user)
    proj_b = await _make_project(db_session, user)

    a = ExternalIssue(
        project_id=proj_a.id, provider="jira", external_id="PROJ-123",
        title="no A", status_canonical="todo",
    )
    b = ExternalIssue(
        project_id=proj_b.id, provider="jira", external_id="PROJ-123",
        title="no B", status_canonical="todo",
    )
    db_session.add_all([a, b])
    await db_session.flush()  # não levanta


# ===========================================================================
# Porta IssueTrackerPort + registry
# ===========================================================================

class _FakeAdapter(IssueTrackerPort):
    """Adapter fake pra teste do registry — não faz network."""

    provider = "jira"

    async def create_issue(self, config, *, title, description_markdown,
                            priority=None, labels=None):
        return IssuePayload(
            external_id="FAKE-1", url=None, title=title,
            status_canonical="todo", status_raw="To Do",
        )

    async def update_status(self, config, external_id, status):
        return IssuePayload(
            external_id=external_id, url=None, title="x",
            status_canonical=status, status_raw=status,
        )

    async def get_issue(self, config, external_id):
        return IssuePayload(
            external_id=external_id, url=None, title="x",
            status_canonical="todo", status_raw="To Do",
        )

    async def add_comment(self, config, external_id, comment_markdown):
        return None

    def verify_webhook(self, config, headers, raw_body):
        return True

    def parse_webhook(self, config, payload):
        return None


def test_registry_register_get_clear():
    _clear_registry_for_tests()
    assert registered_providers() == []

    register_adapter(_FakeAdapter())
    assert "jira" in registered_providers()

    adapter = get_adapter("jira")
    assert isinstance(adapter, _FakeAdapter)

    _clear_registry_for_tests()
    assert registered_providers() == []


def test_registry_get_sem_adapter_levanta_config_error():
    _clear_registry_for_tests()
    with pytest.raises(IssueTrackerConfigError) as exc:
        get_adapter("jira")
    assert "jira" in str(exc.value)


def test_registry_register_sem_provider_levanta_config_error():
    _clear_registry_for_tests()

    class _BadAdapter(_FakeAdapter):
        provider = ""  # inválido

    with pytest.raises(IssueTrackerConfigError):
        register_adapter(_BadAdapter())


def test_registry_register_substitui_idempotente():
    """Registrar 2x o mesmo provider substitui (útil em testes)."""
    _clear_registry_for_tests()

    class _V1(_FakeAdapter):
        pass

    class _V2(_FakeAdapter):
        pass

    register_adapter(_V1())
    register_adapter(_V2())
    assert isinstance(get_adapter("jira"), _V2)
    _clear_registry_for_tests()


# ===========================================================================
# Service — upsert_from_payload
# ===========================================================================

@pytest.mark.asyncio
async def test_upsert_cria_nova_issue(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    mod = await _make_module(db_session, project, user)

    payload = IssuePayload(
        external_id="PROJ-1", url="http://x",
        title="Login", status_canonical="todo", status_raw="To Do",
        priority="medium", provider_specific={"epic": "X-1"},
    )
    issue = await upsert_from_payload(
        db_session, project_id=project.id, provider="jira",
        module_candidate_id=mod.id, payload=payload, created_by=user.id,
    )
    assert issue.id is not None
    assert issue.external_id == "PROJ-1"
    assert issue.status_canonical == "todo"
    assert issue.module_candidate_id == mod.id
    assert issue.synced_at is not None
    assert issue.closed_at is None


@pytest.mark.asyncio
async def test_upsert_atualiza_issue_existente(db_session):
    """Chamada 2x com mesmo external_id atualiza, não duplica."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    p1 = IssuePayload(
        external_id="PROJ-9", url=None, title="v1",
        status_canonical="todo", status_raw="To Do",
    )
    first = await upsert_from_payload(
        db_session, project_id=project.id, provider="jira",
        module_candidate_id=None, payload=p1,
    )

    p2 = IssuePayload(
        external_id="PROJ-9", url="http://updated", title="v2",
        status_canonical="in_progress", status_raw="In Progress",
    )
    second = await upsert_from_payload(
        db_session, project_id=project.id, provider="jira",
        module_candidate_id=None, payload=p2,
    )

    # Mesma row, não duplicou.
    assert first.id == second.id
    assert second.title == "v2"
    assert second.url == "http://updated"
    assert second.status_canonical == "in_progress"


@pytest.mark.asyncio
async def test_upsert_marca_closed_at_quando_done(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    payload = IssuePayload(
        external_id="PROJ-2", url=None, title="x",
        status_canonical="done", status_raw="Done",
    )
    issue = await upsert_from_payload(
        db_session, project_id=project.id, provider="jira",
        module_candidate_id=None, payload=payload,
    )
    assert issue.closed_at is not None


@pytest.mark.asyncio
async def test_upsert_cancelled_tambem_marca_closed_at(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    payload = IssuePayload(
        external_id="PROJ-3", url=None, title="x",
        status_canonical="cancelled", status_raw="Won't Do",
    )
    issue = await upsert_from_payload(
        db_session, project_id=project.id, provider="jira",
        module_candidate_id=None, payload=payload,
    )
    assert issue.closed_at is not None


# ===========================================================================
# Service — list_external_issues (compartimentalização)
# ===========================================================================

@pytest.mark.asyncio
async def test_list_filtra_por_project_id(db_session):
    """Issues do projeto A nunca aparecem em list(projeto B)."""
    user = await _make_user(db_session)
    proj_a = await _make_project(db_session, user)
    proj_b = await _make_project(db_session, user)

    for p in (proj_a, proj_b):
        await upsert_from_payload(
            db_session, project_id=p.id, provider="jira",
            module_candidate_id=None,
            payload=IssuePayload(
                external_id=f"EXT-{p.id.hex[:4]}", url=None,
                title=f"issue do {p.slug}",
                status_canonical="todo", status_raw="To Do",
            ),
        )

    a_list = await list_external_issues(db_session, proj_a.id)
    b_list = await list_external_issues(db_session, proj_b.id)
    assert len(a_list) == 1
    assert len(b_list) == 1
    assert a_list[0].project_id == proj_a.id
    assert b_list[0].project_id == proj_b.id


@pytest.mark.asyncio
async def test_list_filtra_por_status_canonical(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    for status in ("todo", "in_progress", "done"):
        await upsert_from_payload(
            db_session, project_id=project.id, provider="jira",
            module_candidate_id=None,
            payload=IssuePayload(
                external_id=f"S-{status}", url=None,
                title=f"issue {status}",
                status_canonical=status, status_raw=status,
            ),
        )

    todo = await list_external_issues(db_session, project.id, status="todo")
    done = await list_external_issues(db_session, project.id, status="done")
    assert len(todo) == 1
    assert len(done) == 1
    assert todo[0].status_canonical == "todo"
    assert done[0].status_canonical == "done"


# ===========================================================================
# Service — resolve_adapter
# ===========================================================================

def test_resolve_adapter_sem_registro_levanta_erro_descritivo():
    _clear_registry_for_tests()
    with pytest.raises(IssueTrackerConfigError) as exc:
        resolve_adapter("jira")
    assert "jira" in str(exc.value).lower()
    assert "registrados" in str(exc.value).lower() or "disponíveis" in str(exc.value).lower()


def test_resolve_adapter_registrado_retorna_instancia():
    _clear_registry_for_tests()
    register_adapter(_FakeAdapter())
    adapter = resolve_adapter("jira")
    assert adapter.provider == "jira"
    _clear_registry_for_tests()


# ===========================================================================
# Service — métodos 20.1b/c/d ainda não implementados
# ===========================================================================

@pytest.mark.asyncio
async def test_create_issue_from_module_levanta_not_implemented_em_20_1a(db_session):
    """20.1a é foundation; implementação completa vem em 20.1b/d."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    mod = await _make_module(db_session, project, user)

    from app.services.issue_tracker_service import create_issue_from_module

    with pytest.raises(NotImplementedError) as exc:
        await create_issue_from_module(
            db_session,
            project_id=project.id,
            module_candidate_id=mod.id,
            provider="jira",
            actor_id=user.id,
        )
    # Mensagem deve citar as sub-fases pendentes.
    assert "20.1" in str(exc.value)


@pytest.mark.asyncio
async def test_apply_webhook_event_levanta_not_implemented_em_20_1a(db_session):
    from app.services.issue_tracker_service import apply_webhook_event

    with pytest.raises(NotImplementedError):
        await apply_webhook_event(
            db_session, provider="jira",
            headers={}, raw_body=b"", payload={},
        )
