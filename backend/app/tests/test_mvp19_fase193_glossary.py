"""MVP 19 Fase 19.3 — testes do glossário vivo.

Valida:
- Migration 034: tabela + UNIQUE(project_id, LOWER(term)) + indexes.
- Heurísticas de extração: padrão `Expansão (SIGLA)`, `SIGLA: definição`,
  `X é Y`, siglas soltas; stopwords canônicas.
- Extração é idempotente: rodar 2x não duplica.
- CRUD: approve / reject / update_definition / create_manual_term.
- `list_approved_for_ers` retorna só aprovados ordenados.
- Integração ERS: seção 1.3 renderiza tabela com termos aprovados;
  rejeitados não aparecem; placeholder quando vazio.
"""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis,
    GatekeeperItem,
    IngestedDocument,
    ModuleCandidate,
    OCG,
    Organization,
    Project,
    ProjectGlossaryTerm,
    Questionnaire,
    User,
)
from app.services.ers_doc_generator_service import build_ers_markdown
from app.services.glossary_service import (
    SOURCE_ARGUIDER_RESPONSE,
    SOURCE_MANUAL,
    SOURCE_MODULE_DESCRIPTION,
    SOURCE_OCG_PROFILE,
    STATUS_APPROVED,
    STATUS_CANDIDATE,
    STATUS_REJECTED,
    _extract_candidates_from_text,
    approve_term,
    create_manual_term,
    extract_glossary_candidates,
    list_approved_for_ers,
    list_terms,
    reject_term,
    update_term_definition,
)


# ===========================================================================
# Helpers
# ===========================================================================

async def _make_user(db) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        email=f"gloss-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="Gloss Tester",
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
        slug=f"org-gloss-{uuid4().hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="Projeto Glossário",
        slug=f"glossary-{uuid4().hex[:6]}",
        description="Projeto de teste para glossário.",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


# ===========================================================================
# Migration 034
# ===========================================================================

@pytest.mark.asyncio
async def test_migration_034_tabela_existe(db_session):
    result = await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'project_glossary_terms' ORDER BY ordinal_position"
    ))
    cols = [r[0] for r in result.fetchall()]
    for required in [
        "id", "project_id", "term", "definition", "source", "status",
        "source_reference", "created_at", "created_by",
        "approved_by", "approved_at", "rejected_by", "rejected_at",
    ]:
        assert required in cols, f"Coluna {required} ausente"


@pytest.mark.asyncio
async def test_migration_034_uniq_project_lower_term(db_session):
    result = await db_session.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'project_glossary_terms'"
    ))
    idx_names = [r[0] for r in result.fetchall()]
    assert "uniq_glossary_project_term" in idx_names
    assert "idx_glossary_project_status" in idx_names


@pytest.mark.asyncio
async def test_uniq_rejeita_duplicata_case_insensitive(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    db_session.add(ProjectGlossaryTerm(
        project_id=project.id, term="API", definition="Application Programming Interface",
    ))
    await db_session.flush()

    db_session.add(ProjectGlossaryTerm(
        project_id=project.id, term="api", definition="Duplicata em lowercase",
    ))
    with pytest.raises(Exception):
        # A violação de UNIQUE acontece no flush.
        await db_session.flush()
    await db_session.rollback()


# ===========================================================================
# Heurísticas de extração (funções puras)
# ===========================================================================

def test_extract_padrao_expansao_parens():
    """'Especificação de Requisitos de Software (ERS)' → ERS com definição."""
    text = "Este documento é uma Especificação de Requisitos de Software (ERS) canônica."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    by_key = {c.term: c for c in cands}
    assert "ERS" in by_key
    assert "Especificação de Requisitos de Software" in by_key["ERS"].definition


def test_extract_padrao_sigla_colon_definicao():
    """'ERP: sistema de gestão' → ERP com definição inline."""
    text = "ERP: sistema de gestão empresarial integrado para médias empresas."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    by_key = {c.term: c for c in cands}
    assert "ERP" in by_key
    assert "sistema de gestão" in by_key["ERP"].definition


def test_extract_padrao_sigla_dash_definicao():
    text = "SLA — acordo de nível de serviço entre fornecedor e cliente."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    by_key = {c.term: c for c in cands}
    assert "SLA" in by_key
    assert "acordo de nível de serviço" in by_key["SLA"].definition


def test_extract_padrao_x_e_y():
    text = "Pedido é o registro canônico de uma solicitação de compra no sistema."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    terms = [c.term for c in cands]
    assert "Pedido" in terms
    # E a definição foi capturada
    pedido = [c for c in cands if c.term == "Pedido"][0]
    assert "registro canônico" in pedido.definition


def test_extract_x_significa_y():
    text = "CRM significa gestão do relacionamento com o cliente."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    by_key = {c.term: c for c in cands}
    assert "CRM" in by_key
    assert "gestão do relacionamento" in by_key["CRM"].definition


def test_extract_sigla_solta_sem_definicao():
    """Siglas soltas entram como candidatos com definition vazia."""
    text = "O sistema integra com OMS e WMS via webhooks."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    terms = [c.term for c in cands]
    assert "OMS" in terms
    assert "WMS" in terms
    for t in ("OMS", "WMS"):
        cand = [c for c in cands if c.term == t][0]
        assert cand.definition == ""


def test_extract_stopwords_ignoradas():
    """Siglas-stopword ('DE', 'DO', 'DA', 'EM', 'NO', 'NA', 'OU', etc) não viram termos."""
    text = "O módulo DE compras integra com DO estoque EM tempo real."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    terms = {c.term for c in cands}
    for stopword in ("DE", "DO", "EM"):
        assert stopword not in terms


def test_extract_dedup_interno_prefere_definicao():
    """Se o mesmo termo aparece com e sem definição, a versão com
    definição vence."""
    text = "O ERP é usado. ERP: sistema integrado para empresas."
    cands = list(_extract_candidates_from_text(text, "test", "ref"))
    erp = [c for c in cands if c.term == "ERP"]
    assert len(erp) == 1
    assert "sistema integrado" in erp[0].definition


def test_extract_texto_vazio_retorna_vazio():
    assert list(_extract_candidates_from_text("", "s", "r")) == []
    assert list(_extract_candidates_from_text(None, "s", "r")) == []  # type: ignore


# ===========================================================================
# Idempotência end-to-end
# ===========================================================================

@pytest.mark.asyncio
async def test_extract_glossary_candidates_idempotente(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Corpus: um módulo com texto rico em candidatos.
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        filename=f"{uuid4().hex}.pdf",
        original_filename="test.pdf",
        file_type="pdf",
        file_hash="0" * 64,
        file_size_bytes=100,
        uploaded_by=user.id,
    )
    db_session.add(doc)
    await db_session.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        llm_model="claude",
        tokens_used=100,
        latency_ms=100,
    )
    db_session.add(analysis)

    m = ModuleCandidate(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name="Integração ERP",
        description=(
            "Integração com ERP (sistema de gestão). API REST usada via HTTPS. "
            "OMS: orquestrador de pedidos. SLA — acordo de nível de serviço."
        ),
        module_type="feature",
        priority="high",
    )
    db_session.add(m)
    await db_session.flush()

    # 1ª execução — insere.
    r1 = await extract_glossary_candidates(db_session, project.id, actor_id=user.id)
    assert r1.inserted > 0
    terms_after_1 = (await db_session.execute(
        select(ProjectGlossaryTerm).where(ProjectGlossaryTerm.project_id == project.id)
    )).scalars().all()
    count_1 = len(terms_after_1)
    assert count_1 > 0

    # Pega chaves normalizadas (case-insensitive).
    keys_1 = {t.term.lower() for t in terms_after_1}
    assert "erp" in keys_1
    assert "oms" in keys_1
    assert "sla" in keys_1

    # 2ª execução — zero novos.
    r2 = await extract_glossary_candidates(db_session, project.id, actor_id=user.id)
    assert r2.inserted == 0
    assert r2.skipped_existing > 0

    count_2 = (await db_session.execute(
        select(func.count(ProjectGlossaryTerm.id)).where(ProjectGlossaryTerm.project_id == project.id)
    )).scalar_one()
    assert count_2 == count_1, "Extração duplicou termos"


@pytest.mark.asyncio
async def test_extract_puxa_multiplas_fontes(db_session):
    """Verifica que as 4 fontes (módulo, análise, gatekeeper, OCG) são varridas."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Fonte 1: ModuleCandidate
    doc = IngestedDocument(
        id=uuid4(), project_id=project.id, filename=f"{uuid4().hex}.pdf",
        original_filename="d.pdf", file_type="pdf", file_hash="0"*64,
        file_size_bytes=100, uploaded_by=user.id,
    )
    db_session.add(doc)
    await db_session.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=project.id,
        llm_model="c", tokens_used=1, latency_ms=1,
        gaps='[{"description": "Falta definir NFE — nota fiscal eletrônica."}]',
    )
    db_session.add(analysis)
    m = ModuleCandidate(
        project_id=project.id, arguider_analysis_id=analysis.id,
        name="Módulo X",
        description="Integra com ERP (Enterprise Resource Planning).",
        module_type="feature", priority="medium",
    )
    db_session.add(m)
    # Fonte 2: GatekeeperItem
    gi = GatekeeperItem(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type="gap",
        item_id_in_analysis="G001",
        item_data='{"description": "Documentar integração B2B."}',
        status="pending",
    )
    db_session.add(gi)
    # Fonte 3: OCG
    quest = Questionnaire(
        id=uuid4(), project_id=project.id, gp_email=user.email,
        responses="{}", status="ok", approved=True,
    )
    db_session.add(quest)
    await db_session.flush()
    ocg_payload = {"PROJECT_PROFILE": {"description": "Sistema OMS para varejo."}}
    import json
    ocg = OCG(
        project_id=project.id, questionnaire_id=quest.id, version=1,
        ocg_data=json.dumps(ocg_payload),
    )
    db_session.add(ocg)
    await db_session.flush()

    result = await extract_glossary_candidates(db_session, project.id, actor_id=user.id)

    terms = (await db_session.execute(
        select(ProjectGlossaryTerm).where(ProjectGlossaryTerm.project_id == project.id)
    )).scalars().all()
    keys = {t.term.lower() for t in terms}

    # ModuleCandidate
    assert "erp" in keys
    # ArguiderAnalysis
    assert "nfe" in keys
    # GatekeeperItem
    assert "b2b" in keys
    # OCG
    assert "oms" in keys

    assert result.scanned_sources >= 4


# ===========================================================================
# CRUD de termos
# ===========================================================================

@pytest.mark.asyncio
async def test_approve_term_muda_status_e_grava_actor(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    term = ProjectGlossaryTerm(
        project_id=project.id, term="NFE", definition="Nota fiscal eletrônica",
    )
    db_session.add(term)
    await db_session.flush()

    approved = await approve_term(db_session, term.id, actor_id=user.id)

    assert approved.status == STATUS_APPROVED
    assert approved.approved_by == user.id
    assert approved.approved_at is not None
    assert approved.rejected_by is None
    assert approved.rejected_at is None


@pytest.mark.asyncio
async def test_reject_term_muda_status(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    term = ProjectGlossaryTerm(project_id=project.id, term="ABC", definition="")
    db_session.add(term)
    await db_session.flush()

    rejected = await reject_term(db_session, term.id, actor_id=user.id)

    assert rejected.status == STATUS_REJECTED
    assert rejected.rejected_by == user.id
    assert rejected.rejected_at is not None


@pytest.mark.asyncio
async def test_approve_depois_reject_volta_status(db_session):
    """GP pode alternar entre aprovado e rejeitado; campos seguem o
    último estado."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    term = ProjectGlossaryTerm(project_id=project.id, term="FOO", definition="")
    db_session.add(term)
    await db_session.flush()

    await approve_term(db_session, term.id, actor_id=user.id)
    final = await reject_term(db_session, term.id, actor_id=user.id)

    assert final.status == STATUS_REJECTED
    # Aprovado-antes foi limpo ao rejeitar.
    assert final.approved_by is None
    assert final.approved_at is None


@pytest.mark.asyncio
async def test_update_definition_nao_muda_status(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    term = ProjectGlossaryTerm(
        project_id=project.id, term="X", definition="original",
        status=STATUS_APPROVED,
    )
    db_session.add(term)
    await db_session.flush()

    updated = await update_term_definition(
        db_session, term.id, "nova definição muito mais clara", actor_id=user.id
    )

    assert updated.definition == "nova definição muito mais clara"
    assert updated.status == STATUS_APPROVED


@pytest.mark.asyncio
async def test_create_manual_term_insere_approved(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    term = await create_manual_term(
        db_session,
        project_id=project.id,
        term="Cliente VIP",
        definition="Cliente com faturamento anual acima de X.",
        actor_id=user.id,
    )

    assert term.status == STATUS_APPROVED
    assert term.source == SOURCE_MANUAL
    assert term.approved_by == user.id
    assert term.approved_at is not None


@pytest.mark.asyncio
async def test_create_manual_term_upsert_em_duplicata(db_session):
    """Se GP tenta cadastrar termo que já existe como candidato,
    upsert promove para approved + atualiza definition."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    db_session.add(ProjectGlossaryTerm(
        project_id=project.id, term="API", definition="old",
        status=STATUS_CANDIDATE,
    ))
    await db_session.flush()

    result = await create_manual_term(
        db_session,
        project_id=project.id,
        term="API",  # mesmo termo
        definition="Application Programming Interface",
        actor_id=user.id,
    )

    assert result.status == STATUS_APPROVED
    assert result.definition == "Application Programming Interface"


# ===========================================================================
# list_terms + list_approved_for_ers
# ===========================================================================

@pytest.mark.asyncio
async def test_list_terms_filtra_por_status(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    for term_name, s in [("A", STATUS_CANDIDATE), ("B", STATUS_APPROVED), ("C", STATUS_REJECTED)]:
        db_session.add(ProjectGlossaryTerm(
            project_id=project.id, term=term_name, definition="d", status=s,
        ))
    await db_session.flush()

    all_ = await list_terms(db_session, project.id)
    approved = await list_terms(db_session, project.id, status_filter=STATUS_APPROVED)
    candidates = await list_terms(db_session, project.id, status_filter=STATUS_CANDIDATE)

    assert len(all_) == 3
    assert len(approved) == 1 and approved[0].term == "B"
    assert len(candidates) == 1 and candidates[0].term == "A"


@pytest.mark.asyncio
async def test_list_approved_for_ers_ordem_alfabetica(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    for t in ["Zeta", "Alpha", "Gama"]:
        db_session.add(ProjectGlossaryTerm(
            project_id=project.id, term=t, definition="d", status=STATUS_APPROVED,
        ))
    # Um rejeitado não deve aparecer.
    db_session.add(ProjectGlossaryTerm(
        project_id=project.id, term="Rejected", definition="d", status=STATUS_REJECTED,
    ))
    await db_session.flush()

    approved = await list_approved_for_ers(db_session, project.id)

    assert [t.term for t in approved] == ["Alpha", "Gama", "Zeta"]


# ===========================================================================
# Integração com ERS generator — seção 1.3
# ===========================================================================

@pytest.mark.asyncio
async def test_ers_secao_13_renderiza_termos_aprovados(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    db_session.add_all([
        ProjectGlossaryTerm(
            project_id=project.id, term="ERP",
            definition="Enterprise Resource Planning", status=STATUS_APPROVED,
        ),
        ProjectGlossaryTerm(
            project_id=project.id, term="CRM",
            definition="Customer Relationship Management", status=STATUS_APPROVED,
        ),
        ProjectGlossaryTerm(
            project_id=project.id, term="ABC",
            definition="só candidato, não entra", status=STATUS_CANDIDATE,
        ),
        ProjectGlossaryTerm(
            project_id=project.id, term="XYZ",
            definition="rejeitado, não entra", status=STATUS_REJECTED,
        ),
    ])
    await db_session.flush()

    md = await build_ers_markdown(db_session, project.id)

    # Tabela renderizada na seção 1.3.
    assert "### 1.3 Definições, Siglas e Abreviaturas" in md
    assert "| Termo | Definição |" in md
    assert "**ERP**" in md
    assert "Enterprise Resource Planning" in md
    assert "**CRM**" in md
    assert "Customer Relationship Management" in md
    # Candidato e rejeitado não entram.
    assert "ABC" not in md
    assert "XYZ" not in md
    assert "só candidato" not in md


@pytest.mark.asyncio
async def test_ers_secao_13_placeholder_quando_vazio(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    md = await build_ers_markdown(db_session, project.id)

    assert "### 1.3 Definições, Siglas e Abreviaturas" in md
    assert "_Nenhum termo aprovado ainda" in md


@pytest.mark.asyncio
async def test_ers_secao_13_escapa_pipe_na_definicao(db_session):
    """Se a definição contém '|' (quebra tabela), é escapado."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    db_session.add(ProjectGlossaryTerm(
        project_id=project.id, term="TBL",
        definition="Coluna | outra coluna",
        status=STATUS_APPROVED,
    ))
    await db_session.flush()

    md = await build_ers_markdown(db_session, project.id)
    # Pipe escapado com backslash.
    assert "Coluna \\| outra coluna" in md
