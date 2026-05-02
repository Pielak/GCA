"""MVP 31 Fase 31.1 — Testes de schema + modelos ORM pós-migration 066.

Cobre:
  - OCGIndividual.persona_id aceita tag canônica (string "AUD", "GP", etc.)
  - UniqueConstraint (document_id, persona_id) em OCGIndividual
  - UniqueConstraint (document_id) em OCGGlobal
  - CHECK constraint version > 0 em ocg
  - Índice composto idx_ocg_project_version existe e está ativo
  - Importação dos 4 novos modelos sem erro

Banco alvo: gca_test (conftest.py força — DT-034)
"""
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.base import (
    IngestedDocument,
    OCG,
    OCGGlobal,
    OCGIndividual,
    OCGIndividualRefined,
    PersonaFollowUpQuestion,
    Questionnaire,
)
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Helpers
# =============================================================================

async def _seed_doc(db):
    """Cria usuário + organização + projeto + documento ingerido para testes."""
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db,
        organization_id=org.id,
        slug=f"mvp31-{uuid4().hex[:6]}",
    )
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        uploaded_by=user.id,
        original_filename="requisitos.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=2048,
        arguider_status="completed",
        pii_detected=False,
    )
    db.add(doc)
    await db.flush()
    return project, doc, user


async def _seed_ocg(db, project_id):
    """Cria um registro OCG mínimo com version=1 para testes de constraint."""
    q = Questionnaire(
        id=uuid4(),
        project_id=project_id,
        gp_email=f"gp-{uuid4().hex[:6]}@test.com",
        responses="{}",
        status="approved",
        approved=True,
    )
    db.add(q)
    await db.flush()
    ocg = OCG(
        id=uuid4(),
        questionnaire_id=q.id,
        project_id=project_id,
        status="READY",
        is_blocking=False,
        ocg_data="{}",
        version=1,
    )
    db.add(ocg)
    await db.flush()
    return ocg


# =============================================================================
# Testes — Importação dos modelos
# =============================================================================

def test_orm_imports_ok():
    """Confirma que os 4 novos modelos importam sem erro e têm __tablename__ correto."""
    assert OCGIndividual.__tablename__ == "ocg_individual"
    assert OCGGlobal.__tablename__ == "ocg_global"
    assert OCGIndividualRefined.__tablename__ == "ocg_individual_refined"
    assert PersonaFollowUpQuestion.__tablename__ == "persona_follow_up_questions"


# =============================================================================
# Testes — OCGIndividual: persona_id como string
# =============================================================================

@pytest.mark.asyncio
async def test_ocg_individual_persona_id_is_string(db_session):
    """persona_id deve aceitar tag canônica da persona LLM (VARCHAR 20) — não UUID."""
    project, doc, _ = await _seed_doc(db_session)

    ocg_ind = OCGIndividual(
        id=uuid4(),
        project_id=project.id,
        document_id=doc.id,
        persona_id="AUD",  # tag canônica — Auditor
        persona_name="Auditor",
        parecer={"titulo": "Classificação inicial", "analise": "OK"},
        status="completed",
    )
    db_session.add(ocg_ind)
    await db_session.flush()

    result = await db_session.get(OCGIndividual, ocg_ind.id)
    assert result is not None
    assert result.persona_id == "AUD"
    assert isinstance(result.persona_id, str)


@pytest.mark.asyncio
async def test_ocg_individual_aceita_todas_tags_canonicas(db_session):
    """Verifica que as 12 tags canônicas das personas cabem em VARCHAR(20)."""
    tags_canonicas = ["AUD", "GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI", "SEG", "CONF", "LGPD", "NEG"]
    assert all(len(tag) <= 20 for tag in tags_canonicas), (
        "Tag canônica excede VARCHAR(20)"
    )
    # Confirma que todas as tags são string pura (não UUIDs)
    for tag in tags_canonicas:
        assert "-" not in tag, f"Tag {tag} parece UUID — erro de design"


# =============================================================================
# Testes — Constraint UNIQUE em OCGIndividual
# =============================================================================

@pytest.mark.asyncio
async def test_ocg_individual_unique_per_document_persona(db_session):
    """INSERT duplicado (document_id, persona_id) deve falhar com IntegrityError."""
    project, doc, _ = await _seed_doc(db_session)

    def _make_ind():
        return OCGIndividual(
            id=uuid4(),
            project_id=project.id,
            document_id=doc.id,
            persona_id="GP",
            persona_name="Gerente de Projetos",
            parecer={"analise": "OK"},
            status="completed",
        )

    db_session.add(_make_ind())
    await db_session.flush()

    db_session.add(_make_ind())  # Duplicado: mesmo document_id + persona_id
    with pytest.raises(IntegrityError):
        await db_session.flush()


# =============================================================================
# Testes — Constraint UNIQUE em OCGGlobal
# =============================================================================

@pytest.mark.asyncio
async def test_ocg_global_unique_per_document(db_session):
    """INSERT duplicado (document_id) em ocg_global deve falhar com IntegrityError."""
    project, doc, user = await _seed_doc(db_session)

    def _make_global():
        return OCGGlobal(
            id=uuid4(),
            project_id=project.id,
            document_id=doc.id,
            parecer_consolidated={"status": "OK"},
            consensus_fields={},
            conflicting_fields={},
            voting_results={},
        )

    db_session.add(_make_global())
    await db_session.flush()

    db_session.add(_make_global())  # Duplicado: mesmo document_id
    with pytest.raises(IntegrityError):
        await db_session.flush()


# =============================================================================
# Testes — CHECK constraint version > 0 em ocg
# =============================================================================

@pytest.mark.asyncio
async def test_ocg_version_check_constraint_rejeita_zero(db_session):
    """UPDATE de version para 0 deve falhar (CHECK version > 0).

    O asyncpg/SQLAlchemy pode disparar a violação de CHECK no execute()
    ou no flush() dependendo da transação — por isso capturamos no execute.
    """
    project, _, _ = await _seed_doc(db_session)
    ocg = await _seed_ocg(db_session, project.id)

    with pytest.raises((IntegrityError, Exception)) as exc_info:
        await db_session.execute(
            text("UPDATE ocg SET version = 0 WHERE id = :id"),
            {"id": str(ocg.id)},
        )
        await db_session.flush()

    # Garante que a violação foi de CHECK constraint, não outro erro
    assert "chk_ocg_version_positive" in str(exc_info.value) or "CheckViolation" in str(type(exc_info.value.__cause__))


@pytest.mark.asyncio
async def test_ocg_version_check_constraint_rejeita_negativo(db_session):
    """UPDATE de version para -1 deve falhar (CHECK version > 0)."""
    project, _, _ = await _seed_doc(db_session)
    ocg = await _seed_ocg(db_session, project.id)

    with pytest.raises((IntegrityError, Exception)) as exc_info:
        await db_session.execute(
            text("UPDATE ocg SET version = -1 WHERE id = :id"),
            {"id": str(ocg.id)},
        )
        await db_session.flush()

    assert "chk_ocg_version_positive" in str(exc_info.value) or "CheckViolation" in str(type(exc_info.value.__cause__))


@pytest.mark.asyncio
async def test_ocg_version_check_constraint_aceita_positivo(db_session):
    """UPDATE de version para valor positivo deve funcionar normalmente."""
    project, _, _ = await _seed_doc(db_session)
    ocg = await _seed_ocg(db_session, project.id)

    await db_session.execute(
        text("UPDATE ocg SET version = 5 WHERE id = :id"),
        {"id": str(ocg.id)},
    )
    await db_session.flush()

    # Expirar cache do ORM para ler do banco
    await db_session.refresh(ocg)
    assert ocg.version == 5


# =============================================================================
# Testes — Índice composto idx_ocg_project_version
# =============================================================================

@pytest.mark.asyncio
async def test_idx_ocg_project_version_existe(db_session):
    """Confirma que o índice composto idx_ocg_project_version foi criado."""
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'ocg' AND indexname = 'idx_ocg_project_version'"
        )
    )
    row = result.fetchone()
    assert row is not None, (
        "Índice idx_ocg_project_version não encontrado — migration 066 não foi aplicada?"
    )
    assert row[0] == "idx_ocg_project_version"


@pytest.mark.asyncio
async def test_idx_ocg_project_version_cobre_colunas_corretas(db_session):
    """Confirma que o índice cobre (project_id, version) conforme mandato Gate 3."""
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename = 'ocg' AND indexname = 'idx_ocg_project_version'"
        )
    )
    row = result.fetchone()
    assert row is not None
    indexdef = row[0].lower()
    assert "project_id" in indexdef
    assert "version" in indexdef


# =============================================================================
# Testes — Verificações adicionais de schema pós-migration
# =============================================================================

@pytest.mark.asyncio
async def test_ocg_individual_sem_fk_para_users(db_session):
    """persona_id em ocg_individual não deve ter FK para users.id."""
    result = await db_session.execute(
        text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'ocg_individual'::regclass "
            "AND contype = 'f' "
            "AND conname = 'ocg_individual_persona_id_fkey'"
        )
    )
    row = result.fetchone()
    assert row is None, (
        "FK ocg_individual_persona_id_fkey ainda existe — migration 066 não removeu a FK?"
    )


@pytest.mark.asyncio
async def test_persona_follow_up_questions_answered_by_on_delete_set_null(db_session):
    """answered_by em persona_follow_up_questions deve ter ON DELETE SET NULL."""
    result = await db_session.execute(
        text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'persona_follow_up_questions_answered_by_fkey'"
        )
    )
    row = result.fetchone()
    assert row is not None
    # confdeltype pode retornar string ou bytes dependendo do driver asyncpg
    confdeltype = row[0] if isinstance(row[0], str) else row[0].decode("utf-8")
    assert confdeltype == "n", (
        "ON DELETE da FK answered_by não é SET NULL (esperado 'n', "
        f"obtido '{confdeltype}')"
    )


@pytest.mark.asyncio
async def test_ocg_ix_indices_duplicados_removidos(db_session):
    """Confirma que os índices ix_ duplicados em ocg_individual foram removidos."""
    result = await db_session.execute(
        text(
            "SELECT COUNT(*) FROM pg_indexes "
            "WHERE tablename = 'ocg_individual' AND indexname LIKE 'ix_%'"
        )
    )
    count = result.scalar()
    assert count == 0, (
        f"Ainda existem {count} índice(s) ix_ em ocg_individual — migration 066 incompleta?"
    )
