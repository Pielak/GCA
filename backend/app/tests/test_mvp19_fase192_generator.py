"""MVP 19 Fase 19.2 — testes do generator ERS + freshness.

Valida:
- `build_ers_markdown` produz markdown IEEE 830 bem-formado com as 4
  seções canônicas + placeholders nas seções 1.3 (glossário) e 4 (matriz).
- Módulos classificados (functional/non_functional/business_rule) aparecem
  nas seções certas (3.1, 3.2, 3.3).
- Módulos não-classificados aparecem na seção "3.5 pendentes".
- OCG vazio não quebra — emite placeholders explícitos.
- `BUSINESS_RULES` do OCG aparece em 3.3.
- `external_repos` aparecem em 1.4 (Referências) e 3.4 (Interfaces Externas).
- `get_ers_freshness` reporta `ever_generated=False` quando nunca gerou.
- Freshness: evento OCG_UPDATED depois do último regen → stale_reasons.
- Freshness: sem eventos após regen → is_stale=False.
- `generate_and_commit_ers` levanta ValueError quando projeto não tem repo.
- Testes de isolamento: commit é mockado para não exigir token Git real.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis,
    GlobalAuditLog,
    IngestedDocument,
    ModuleCandidate,
    OCG,
    Organization,
    Project,
    ProjectExternalRepo,
    ProjectGitConfig,
    Questionnaire,
    User,
)
from app.core.security import hash_password
from app.services.audit_service import AuditEvents
from app.services.ers_doc_generator_service import (
    ERS_FILE_PATH,
    build_ers_markdown,
    generate_and_commit_ers,
    get_ers_freshness,
)


# ===========================================================================
# Helpers de fixtures
# ===========================================================================

async def _make_user(db):
    uid = uuid4()
    user = User(
        id=uid,
        email=f"mvp19-gen-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="MVP 19 Gen",
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
        slug=f"org-mvp19-gen-{uuid4().hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="E-Commerce Plus",
        slug=f"ecommerce-plus-{uuid4().hex[:6]}",
        description="Plataforma de comércio eletrônico para varejo.",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


async def _make_ocg(
    db,
    project: Project,
    user: User,
    version: int = 1,
    ocg_payload: dict | None = None,
) -> OCG:
    quest = Questionnaire(
        id=uuid4(),
        project_id=project.id,
        gp_email=user.email,
        responses="{}",
        status="ok",
        approved=True,
    )
    db.add(quest)
    await db.flush()
    ocg = OCG(
        project_id=project.id,
        questionnaire_id=quest.id,
        version=version,
        ocg_data=json.dumps(ocg_payload or {}),
    )
    db.add(ocg)
    await db.flush()
    return ocg


async def _make_module(
    db,
    project: Project,
    analysis: ArguiderAnalysis,
    *,
    name: str,
    category: str | None = None,
    priority: str = "medium",
) -> ModuleCandidate:
    m = ModuleCandidate(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name=name,
        description=f"Descrição do módulo {name}",
        module_type="feature",
        priority=priority,
        requirement_category=category,
    )
    db.add(m)
    await db.flush()
    return m


async def _make_analysis(db, project: Project) -> ArguiderAnalysis:
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        filename=f"{uuid4().hex}.pdf",
        original_filename="test.pdf",
        file_type="pdf",
        file_hash="0" * 64,
        file_size_bytes=100,
        uploaded_by=(await db.execute(select(User).limit(1))).scalar_one().id,
    )
    db.add(doc)
    await db.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        llm_model="claude-sonnet",
        tokens_used=100,
        latency_ms=100,
    )
    db.add(analysis)
    await db.flush()
    return analysis


# ===========================================================================
# build_ers_markdown — estrutura IEEE 830
# ===========================================================================

@pytest.mark.asyncio
async def test_markdown_ocg_vazio_emite_placeholders(db_session):
    """Projeto sem OCG: generator não quebra; todas as seções vêm com placeholder."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    md = await build_ers_markdown(db_session, project.id)

    # Header canônico.
    assert "# ERS — Especificação de Requisitos de Software" in md
    assert f"**Projeto**: {project.name}" in md
    assert "**Padrão**: IEEE 830-1998" in md

    # 4 seções + matriz + histórico.
    assert "## 1. Introdução" in md
    assert "### 1.1 Propósito" in md
    assert "### 1.2 Escopo" in md
    assert "### 1.3 Definições, Siglas e Abreviaturas" in md
    assert "### 1.4 Referências" in md
    assert "## 2. Descrição Geral" in md
    assert "### 2.1 Perspectiva do Produto" in md
    assert "### 2.2 Funcionalidades do Produto" in md
    assert "### 2.3 Características dos Usuários" in md
    assert "### 2.4 Restrições" in md
    assert "### 2.5 Suposições e Dependências" in md
    assert "## 3. Requisitos Específicos" in md
    assert "### 3.1 Requisitos Funcionais" in md
    assert "### 3.2 Requisitos Não-Funcionais" in md
    assert "### 3.3 Regras de Negócio" in md
    assert "### 3.4 Interfaces Externas" in md
    assert "## 4. Matriz de Rastreabilidade" in md
    assert "## Histórico de Revisão" in md

    # Seção 1.3 — placeholder do glossário agora aponta para a aba
    # (após Fase 19.3, o texto não cita mais "Fase 19.3" — é funcional).
    assert "Nenhum termo aprovado ainda" in md
    # Placeholder da Fase 19.4 (matriz de rastreabilidade).
    assert "Fase 19.4" in md


@pytest.mark.asyncio
async def test_markdown_ocg_preenchido_renderiza_secoes(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ocg_payload = {
        "PROJECT_PROFILE": {
            "description": "Sistema de gestão de pedidos online.",
            "assumptions": ["Banco PostgreSQL 16 disponível", "Rede latência <50ms"],
            "dependencies": ["API de pagamento", "Gateway de SMS"],
        },
        "DELIVERABLES": {
            "doc": ["Manual do usuário", "Guia de integração"],
            "code": ["Módulo de checkout", "Módulo de catálogo"],
        },
        "STACK_RECOMMENDATION": {
            "backend": {"language": "Python", "framework": "FastAPI"},
            "frontend": {"stack": "React + TypeScript"},
            "database": {"engine": "PostgreSQL"},
            "cache": {"enabled": True},
        },
        "ARCHITECTURE_OVERVIEW": {
            "style": "Microservices + API Gateway",
            "execution_model": ["Cloud", "Containerizado"],
        },
        "COMPLIANCE_CHECKLIST": ["LGPD", "PCI-DSS"],
        "BUSINESS_RULES": [
            {
                "id": "BR-GCA-001",
                "title": "Pedido cancelado não pode ser faturado",
                "description": "Regra de negócio da gestão de pedidos.",
                "source": "questionário",
            },
        ],
        "PILLAR_SCORES": {
            "P4": {"score": 82, "findings": [{"severity": "warning", "description": "Sem teste de carga definido", "recommendation": "Definir SLA"}]},
            "P7": {"score": 88, "findings": [{"severity": "info", "description": "MFA sugerido para admin"}]},
        },
    }
    await _make_ocg(db_session, project, user, version=3, ocg_payload=ocg_payload)

    md = await build_ers_markdown(db_session, project.id)

    # 1.1 Propósito usou a description do profile.
    assert "Sistema de gestão de pedidos online." in md
    # 1.2 Escopo listou deliverables.
    assert "[doc] Manual do usuário" in md
    assert "[code] Módulo de checkout" in md
    # 2.1 mostra estilo + execution model.
    assert "Microservices + API Gateway" in md
    assert "Cloud, Containerizado" in md
    # 2.4 Restrições lista stack.
    assert "**Linguagem backend**: Python" in md
    assert "**Frontend**: React + TypeScript" in md
    assert "**Banco**: PostgreSQL" in md
    assert "**Cache**: habilitado" in md
    # 2.5 suposições e dependências.
    assert "Banco PostgreSQL 16 disponível" in md
    assert "API de pagamento" in md
    # 3.2.1 pillar findings.
    assert "Sem teste de carga definido" in md
    # Compliance renderizou.
    assert "LGPD" in md
    # 3.3 Business Rules do OCG.
    assert "BR-GCA-001" in md
    assert "Pedido cancelado não pode ser faturado" in md
    # Versão no header.
    assert "**Versão do OCG**: 3" in md


@pytest.mark.asyncio
async def test_markdown_modulos_categorizados_aparecem_em_secoes_certas(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, user, version=1)
    analysis = await _make_analysis(db_session, project)

    await _make_module(db_session, project, analysis, name="Login por senha", category="functional")
    await _make_module(db_session, project, analysis, name="Recuperação de senha", category="functional")
    await _make_module(db_session, project, analysis, name="Latência P95 < 200ms", category="non_functional")
    await _make_module(db_session, project, analysis, name="Pedido só emite NF em até 24h", category="business_rule")
    await _make_module(db_session, project, analysis, name="Módulo sem categoria", category=None)

    md = await build_ers_markdown(db_session, project.id)

    # 3.1 RF
    assert "**RF-001 — Login por senha**" in md
    assert "**RF-002 — Recuperação de senha**" in md
    # 3.2 RNF
    assert "**RNF-001 — Latência P95 < 200ms**" in md
    # 3.3 BR (via módulo)
    assert "BR-001" in md
    assert "Pedido só emite NF em até 24h" in md
    # 3.5 pendentes
    assert "### 3.5 Requisitos pendentes de classificação" in md
    assert "Módulo sem categoria" in md


@pytest.mark.asyncio
async def test_markdown_external_repos_aparecem_em_14_e_34(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, user, version=1)

    repo = ProjectExternalRepo(
        project_id=project.id,
        repo_url="https://github.com/acme/legacy-erp",
        provider="github",
        branch="main",
        status="completed",
        added_by=user.id,
        compatibility_status="requer_adaptacao",
    )
    db_session.add(repo)
    await db_session.flush()

    md = await build_ers_markdown(db_session, project.id)

    # Seção 1.4 referências.
    assert "https://github.com/acme/legacy-erp" in md
    # Seção 3.4 com detalhes.
    assert "### 3.4 Interfaces Externas" in md
    assert "requer_adaptacao" in md


@pytest.mark.asyncio
async def test_markdown_termina_com_newline(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    md = await build_ers_markdown(db_session, project.id)
    assert md.endswith("\n")


# ===========================================================================
# Freshness via audit log (sem tabela dedicada)
# ===========================================================================

@pytest.mark.asyncio
async def test_freshness_nunca_gerado(db_session):
    """Projeto novo sem LIVEDOCS_UPDATED: ever_generated=False, is_stale=True."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    state = await get_ers_freshness(db_session, project.id)

    assert state["ever_generated"] is False
    assert state["is_stale"] is True
    assert state["last_generated_at"] is None
    assert state["last_commit_sha"] is None


@pytest.mark.asyncio
async def test_freshness_regen_recente_sem_eventos_novos(db_session):
    """LIVEDOCS_UPDATED recente + sem eventos stale depois → is_stale=False."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Insere LIVEDOCS_UPDATED manualmente simulando um regen.
    entry = GlobalAuditLog(
        event_type=AuditEvents.LIVEDOCS_UPDATED,
        actor_id=user.id,
        resource_type="live_doc",
        resource_id=project.id,
        details=json.dumps({
            "doc_type": "ers",
            "commit_sha": "abc123def",
            "version_to": 5,
        }),
        previous_hash=None,
        current_hash="hash-test",
    )
    db_session.add(entry)
    await db_session.flush()

    state = await get_ers_freshness(db_session, project.id)

    assert state["ever_generated"] is True
    assert state["is_stale"] is False
    assert state["last_commit_sha"] == "abc123def"
    assert state["last_ocg_version"] == 5
    assert state["stale_reasons"] == []


@pytest.mark.asyncio
async def test_freshness_evento_stale_posterior_marca_stale(db_session):
    """LIVEDOCS_UPDATED + OCG_UPDATED depois → is_stale=True com reason."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Regen do ERS.
    regen = GlobalAuditLog(
        event_type=AuditEvents.LIVEDOCS_UPDATED,
        actor_id=user.id,
        resource_type="live_doc",
        resource_id=project.id,
        details=json.dumps({"doc_type": "ers", "commit_sha": "x", "version_to": 1}),
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        previous_hash=None,
        current_hash="h1",
    )
    db_session.add(regen)
    await db_session.flush()

    # Evento stale posterior.
    stale_event = GlobalAuditLog(
        event_type=AuditEvents.OCG_UPDATED,
        actor_id=user.id,
        resource_type="ocg",
        resource_id=project.id,
        details=json.dumps({"trigger_source": "document_ingestion"}),
        previous_hash="h1",
        current_hash="h2",
    )
    db_session.add(stale_event)
    await db_session.flush()

    state = await get_ers_freshness(db_session, project.id)

    assert state["is_stale"] is True
    assert state["ever_generated"] is True
    assert len(state["stale_reasons"]) == 1
    assert state["stale_reasons"][0]["event_type"] == AuditEvents.OCG_UPDATED
    assert state["stale_reasons"][0]["count"] == 1
    assert state["stale_reasons"][0]["label"] == "OCG atualizado"


@pytest.mark.asyncio
async def test_freshness_agrupa_eventos_iguais(db_session):
    """Múltiplos OCG_UPDATED depois do regen → 1 reason com count agregado."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    regen = GlobalAuditLog(
        event_type=AuditEvents.LIVEDOCS_UPDATED,
        actor_id=user.id,
        resource_type="live_doc",
        resource_id=project.id,
        details=json.dumps({"doc_type": "ers", "commit_sha": "x", "version_to": 1}),
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        previous_hash=None,
        current_hash="h1",
    )
    db_session.add(regen)

    # 3 eventos OCG_UPDATED depois.
    prev = "h1"
    for i in range(3):
        e = GlobalAuditLog(
            event_type=AuditEvents.OCG_UPDATED,
            actor_id=user.id,
            resource_type="ocg",
            resource_id=project.id,
            details=json.dumps({"trigger_source": "test"}),
            previous_hash=prev,
            current_hash=f"ocg-h{i}",
        )
        db_session.add(e)
        prev = f"ocg-h{i}"
    await db_session.flush()

    state = await get_ers_freshness(db_session, project.id)

    assert len(state["stale_reasons"]) == 1
    assert state["stale_reasons"][0]["count"] == 3


@pytest.mark.asyncio
async def test_freshness_eventos_antes_do_regen_nao_contam(db_session):
    """Eventos com created_at anterior ao último LIVEDOCS_UPDATED ficam fora."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Evento OCG ANTES do regen (não deve aparecer em stale_reasons).
    old_event = GlobalAuditLog(
        event_type=AuditEvents.OCG_UPDATED,
        actor_id=user.id,
        resource_type="ocg",
        resource_id=project.id,
        details="{}",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
        previous_hash=None,
        current_hash="old-h",
    )
    db_session.add(old_event)

    # Regen depois.
    regen = GlobalAuditLog(
        event_type=AuditEvents.LIVEDOCS_UPDATED,
        actor_id=user.id,
        resource_type="live_doc",
        resource_id=project.id,
        details=json.dumps({"doc_type": "ers", "commit_sha": "y", "version_to": 2}),
        previous_hash="old-h",
        current_hash="regen-h",
    )
    db_session.add(regen)
    await db_session.flush()

    state = await get_ers_freshness(db_session, project.id)

    assert state["is_stale"] is False
    assert state["stale_reasons"] == []


# ===========================================================================
# generate_and_commit_ers — integração com git_service (mockado)
# ===========================================================================

@pytest.mark.asyncio
async def test_generate_and_commit_sucesso_mockado(db_session):
    """Com GitService.commit_file mockado, a função completa o fluxo:
    gera markdown, commita (mock), emite LIVEDOCS_UPDATED no audit."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, user, version=7)

    with patch(
        "app.services.ers_doc_generator_service.GitService"
    ) as MockGit:
        instance = MockGit.return_value
        async def _fake_commit(**kwargs):
            return {"success": True, "commit_sha": "deadbeef1234", "file_url": "fake"}
        instance.commit_file = _fake_commit

        result = await generate_and_commit_ers(
            db=db_session,
            project_id=project.id,
            actor_id=user.id,
        )

    assert result["success"] is True
    assert result["commit_sha"] == "deadbeef1234"
    assert result["path"] == ERS_FILE_PATH
    assert result["ocg_version"] == 7
    assert result["stale_reasons"] == []  # projeto novo, sem eventos anteriores

    # Audit LIVEDOCS_UPDATED gravado.
    audit_row = (await db_session.execute(
        select(GlobalAuditLog)
        .where(
            GlobalAuditLog.event_type == AuditEvents.LIVEDOCS_UPDATED,
            GlobalAuditLog.resource_id == project.id,
        )
    )).scalar_one()
    details = json.loads(audit_row.details)
    assert details["doc_type"] == "ers"
    assert details["commit_sha"] == "deadbeef1234"
    assert details["version_to"] == 7


@pytest.mark.asyncio
async def test_generate_sem_repo_levanta_value_error(db_session):
    """Projeto sem repositório Git configurado → GitService retorna failure;
    generate_and_commit_ers levanta ValueError com mensagem do git_service."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, user, version=1)

    with patch(
        "app.services.ers_doc_generator_service.GitService"
    ) as MockGit:
        instance = MockGit.return_value
        async def _fake_commit(**kwargs):
            return {"success": False, "message": "Repositório Git não configurado para este projeto"}
        instance.commit_file = _fake_commit

        with pytest.raises(ValueError, match="Repositório Git não configurado"):
            await generate_and_commit_ers(
                db=db_session,
                project_id=project.id,
                actor_id=user.id,
            )


@pytest.mark.asyncio
async def test_generate_propaga_stale_reasons_no_audit(db_session):
    """stale_reasons coletados antes do regen viram `details.stale_reasons`
    no audit LIVEDOCS_UPDATED."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, user, version=3)

    # Cria 2 eventos OCG_UPDATED + 1 DOCUMENT_INGESTED antes do regen.
    events = [
        (AuditEvents.OCG_UPDATED, "ocg"),
        (AuditEvents.OCG_UPDATED, "ocg"),
        (AuditEvents.DOCUMENT_INGESTED, "document"),
    ]
    prev = None
    for i, (et, rt) in enumerate(events):
        e = GlobalAuditLog(
            event_type=et,
            actor_id=user.id,
            resource_type=rt,
            resource_id=project.id,
            details="{}",
            previous_hash=prev,
            current_hash=f"pre-h-{i}",
        )
        db_session.add(e)
        prev = f"pre-h-{i}"
    await db_session.flush()

    with patch(
        "app.services.ers_doc_generator_service.GitService"
    ) as MockGit:
        instance = MockGit.return_value
        async def _fake_commit(**kwargs):
            return {"success": True, "commit_sha": "sha-stale-test"}
        instance.commit_file = _fake_commit

        result = await generate_and_commit_ers(
            db=db_session,
            project_id=project.id,
            actor_id=user.id,
        )

    assert set(result["stale_reasons"]) == {AuditEvents.OCG_UPDATED, AuditEvents.DOCUMENT_INGESTED}

    # Audit registra ambos no details.
    audit_row = (await db_session.execute(
        select(GlobalAuditLog)
        .where(
            GlobalAuditLog.event_type == AuditEvents.LIVEDOCS_UPDATED,
            GlobalAuditLog.resource_id == project.id,
        )
    )).scalar_one()
    details = json.loads(audit_row.details)
    assert AuditEvents.OCG_UPDATED in details["stale_reasons"]
    assert AuditEvents.DOCUMENT_INGESTED in details["stale_reasons"]


@pytest.mark.asyncio
async def test_generate_compose_mensagem_commit_canonica(db_session):
    """Mensagem do commit segue formato: `docs(ers): regen a partir do OCG vN — motivos`."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, user, version=9)

    captured: dict = {}

    async def _fake_commit(*, project_id, file_path, content, commit_message):
        captured["commit_message"] = commit_message
        captured["file_path"] = file_path
        captured["content_len"] = len(content)
        return {"success": True, "commit_sha": "abc"}

    with patch(
        "app.services.ers_doc_generator_service.GitService"
    ) as MockGit:
        MockGit.return_value.commit_file = _fake_commit

        await generate_and_commit_ers(
            db=db_session,
            project_id=project.id,
            actor_id=user.id,
        )

    assert captured["file_path"] == "docs/ERS.md"
    assert captured["commit_message"].startswith("docs(ers): regen a partir do OCG v9 —")
    assert captured["content_len"] > 500  # markdown real, não vazio
