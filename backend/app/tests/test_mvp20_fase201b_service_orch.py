"""MVP 20 Fase 20.1b — testes de orquestração do service com JiraAdapter.

Valida:
- create_issue_from_module: monta título/descrição canônicos, chama
  adapter, faz upsert, emite audit.
- apply_webhook_event: valida assinatura, parse, upsert idempotente,
  emite audit; issue_deleted marca cancelled; assinatura inválida
  retorna None.
- Compartimentalização: módulo de outro projeto é rejeitado.
"""
import hashlib
import hmac
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis,
    ExternalIssue,
    GlobalAuditLog,
    IngestedDocument,
    ModuleCandidate,
    Organization,
    Project,
    User,
)
from app.services.adapters.jira_adapter import JiraAdapter
from app.services.issue_tracker_service import (
    apply_webhook_event,
    create_issue_from_module,
)
from app.services.ports.issue_tracker_port import (
    ProviderConfig,
    _clear_registry_for_tests,
    register_adapter,
)


# ===========================================================================
# Helpers
# ===========================================================================


async def _make_user(db):
    uid = uuid4()
    user = User(
        id=uid, email=f"svc-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="Svc Tester", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db, user):
    org = Organization(
        id=uuid4(), name=f"Org {uuid4().hex[:6]}",
        slug=f"org-svc-{uuid4().hex[:6]}",
        owner_id=user.id, is_active=True, created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id, name="Svc Proj",
        slug=f"svc-{uuid4().hex[:6]}", description="t",
        deliverable_type="web_app", status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


async def _make_module(db, project, user):
    doc = IngestedDocument(
        id=uuid4(), project_id=project.id,
        filename=f"{uuid4().hex}.pdf", original_filename="r.pdf",
        file_type="pdf", file_hash="0" * 64, file_size_bytes=100,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=project.id,
        llm_model="claude-3-5-sonnet", tokens_used=500, latency_ms=200,
    )
    db.add(analysis)
    await db.flush()
    mod = ModuleCandidate(
        project_id=project.id, arguider_analysis_id=analysis.id,
        name="Login via SSO", description="Autenticação corporativa.",
        module_type="feature", priority="high",
        requirement_category="functional",
    )
    db.add(mod)
    await db.flush()
    return mod


def _config(
    *, webhook_secret=None, gca_project_id=None, status_mapping=None,
) -> ProviderConfig:
    return ProviderConfig(
        credentials={
            "email": "gca@example.com",
            "api_token": "t",
            **({"webhook_secret": webhook_secret} if webhook_secret else {}),
        },
        base_url="https://example.atlassian.net",
        default_project_key="PROJ",
        status_mapping=status_mapping or {},
        extra={"gca_project_id": str(gca_project_id)} if gca_project_id else {},
    )


def _jira_with(handler) -> JiraAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JiraAdapter(client=client)


@pytest.fixture(autouse=True)
def _clear_registry():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


# ===========================================================================
# create_issue_from_module
# ===========================================================================


@pytest.mark.asyncio
async def test_create_issue_from_module_fluxo_completo(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    mod = await _make_module(db_session, project, user)

    captured = {}

    def handler(request):
        if request.method == "POST" and request.url.path == "/rest/api/3/issue":
            import json as _json
            captured["create_body"] = _json.loads(request.content.decode())
            return httpx.Response(201, json={"key": "PROJ-77"})
        # follow-up get_issue
        return httpx.Response(200, json={
            "id": "1", "key": "PROJ-77",
            "fields": {
                "summary": captured["create_body"]["fields"]["summary"],
                "status": {"name": "To Do",
                           "statusCategory": {"key": "new"}},
                "priority": {"name": "High"},
                "labels": captured["create_body"]["fields"].get("labels", []),
                "issuetype": {"name": "Task"},
            },
        })

    register_adapter(_jira_with(handler))

    issue = await create_issue_from_module(
        db_session,
        project_id=project.id,
        module_candidate_id=mod.id,
        provider="jira",
        config=_config(),
        actor_id=user.id,
    )
    assert issue.external_id == "PROJ-77"
    assert issue.module_candidate_id == mod.id
    assert issue.title.startswith("RF-")  # categoria functional
    assert "Login via SSO" in issue.title
    assert issue.status_canonical == "todo"
    assert issue.priority == "high"

    # Audit registrado.
    audits = (await db_session.execute(
        select(GlobalAuditLog)
        .where(GlobalAuditLog.event_type == "external_issue_created")
        .where(GlobalAuditLog.resource_id == issue.id)
    )).scalars().all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_create_issue_from_module_rejeita_modulo_de_outro_projeto(db_session):
    user = await _make_user(db_session)
    proj_a = await _make_project(db_session, user)
    proj_b = await _make_project(db_session, user)
    mod_b = await _make_module(db_session, proj_b, user)

    # Adapter "no-op" registrado.
    register_adapter(_jira_with(lambda r: httpx.Response(201, json={"key": "X-1"})))

    # Tentamos criar issue no projeto A usando módulo do B → rejeita.
    with pytest.raises(ValueError) as exc:
        await create_issue_from_module(
            db_session,
            project_id=proj_a.id,  # errado
            module_candidate_id=mod_b.id,
            provider="jira",
            config=_config(),
        )
    assert "não pertence" in str(exc.value).lower() or "não existe" in str(exc.value).lower()


# ===========================================================================
# apply_webhook_event
# ===========================================================================


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_apply_webhook_issue_updated_faz_upsert(db_session):
    import json as _json
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    def handler(request):
        # Adapter faz get_issue pra pegar estado completo.
        return httpx.Response(200, json={
            "id": "1", "key": "PROJ-5",
            "fields": {
                "summary": "título final",
                "status": {"name": "Done",
                           "statusCategory": {"key": "done"}},
            },
        })

    register_adapter(_jira_with(handler))

    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {"key": "PROJ-5",
                  "fields": {"summary": "título parcial",
                             "status": {"name": "Done",
                                        "statusCategory": {"key": "done"}}}},
        "changelog": {"items": [{"field": "status",
                                  "fromString": "In Progress",
                                  "toString": "Done"}]},
    }
    raw = _json.dumps(payload).encode()
    config = _config(webhook_secret="s3cret", gca_project_id=project.id)
    headers = {"X-Hub-Signature-256": _sign("s3cret", raw)}

    issue = await apply_webhook_event(
        db_session, provider="jira", config=config,
        headers=headers, raw_body=raw, payload=payload,
    )
    assert issue is not None
    assert issue.external_id == "PROJ-5"
    assert issue.status_canonical == "done"
    assert issue.title == "título final"
    assert issue.closed_at is not None

    # Audit EXTERNAL_ISSUE_STATUS_SYNCED emitido.
    audits = (await db_session.execute(
        select(GlobalAuditLog)
        .where(GlobalAuditLog.event_type == "external_issue_status_synced")
        .where(GlobalAuditLog.resource_id == issue.id)
    )).scalars().all()
    assert len(audits) >= 1


@pytest.mark.asyncio
async def test_apply_webhook_assinatura_invalida_retorna_none(db_session):
    import json as _json
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    register_adapter(_jira_with(lambda r: httpx.Response(200, json={})))

    payload = {"webhookEvent": "jira:issue_updated", "issue": {"key": "X"}}
    raw = _json.dumps(payload).encode()
    config = _config(webhook_secret="correct", gca_project_id=project.id)
    bad_headers = {"X-Hub-Signature-256": "sha256=" + "0" * 64}

    result = await apply_webhook_event(
        db_session, provider="jira", config=config,
        headers=bad_headers, raw_body=raw, payload=payload,
    )
    assert result is None


@pytest.mark.asyncio
async def test_apply_webhook_issue_deleted_marca_cancelled(db_session):
    import json as _json
    from app.services.issue_tracker_service import upsert_from_payload
    from app.services.ports.issue_tracker_port import IssuePayload

    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Pré-insere issue existente.
    await upsert_from_payload(
        db_session, project_id=project.id, provider="jira",
        module_candidate_id=None,
        payload=IssuePayload(
            external_id="PROJ-D", url=None, title="Existente",
            status_canonical="in_progress", status_raw="In Progress",
        ),
    )

    register_adapter(_jira_with(lambda r: httpx.Response(200, json={})))

    payload = {
        "webhookEvent": "jira:issue_deleted",
        "issue": {"key": "PROJ-D", "fields": {}},
    }
    raw = _json.dumps(payload).encode()
    config = _config(webhook_secret="s", gca_project_id=project.id)
    headers = {"X-Hub-Signature-256": _sign("s", raw)}

    issue = await apply_webhook_event(
        db_session, provider="jira", config=config,
        headers=headers, raw_body=raw, payload=payload,
    )
    assert issue is not None
    assert issue.status_canonical == "cancelled"
    assert issue.closed_at is not None


@pytest.mark.asyncio
async def test_apply_webhook_evento_irrelevante_retorna_none(db_session):
    import json as _json
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    register_adapter(_jira_with(lambda r: httpx.Response(200, json={})))

    payload = {"webhookEvent": "jira:user_created"}
    raw = _json.dumps(payload).encode()
    config = _config(webhook_secret="s", gca_project_id=project.id)
    headers = {"X-Hub-Signature-256": _sign("s", raw)}

    result = await apply_webhook_event(
        db_session, provider="jira", config=config,
        headers=headers, raw_body=raw, payload=payload,
    )
    assert result is None
