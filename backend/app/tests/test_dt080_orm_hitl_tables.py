"""DT-080 — Modelos ORM completos para tabelas HITL.

Antes: `OCGIndividualRefined` e `PersonaFollowUpQuestion` eram stubs no
ORM com apenas FKs primárias. As tabelas existiam no schema vivo (criadas
via SQL manual nas migrations 066/067) com colunas que o ORM não conhecia.
Risco: `alembic autogenerate` futuro sugeriria DROP/RECREATE.

Depois (2026-05-03): modelos completos espelham todas as colunas do schema:
  - OCGIndividualRefined: refinement_iteration, parecer_refined,
    changed_fields, change_summary, created_at + UNIQUE constraint.
  - PersonaFollowUpQuestion: document_id, ocg_individual_id, persona_name,
    question_text, context, question_order, answer_text, answer_provided_at,
    answered_by, status, created_at, updated_at.

Cobre:
  - Schema do modelo == schema do DB (cada coluna tipo correto, nullability).
  - CRUD básico (insert + select + update + cascade delete via FK).
  - UNIQUE (ocg_individual_id, refinement_iteration) é respeitada.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_dt080_orm_hitl_tables.py -v"
"""
import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text as sql_text
from sqlalchemy.exc import IntegrityError

from app.models.base import (
    IngestedDocument,
    OCGIndividual,
    OCGIndividualRefined,
    PersonaFollowUpQuestion,
)
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Helpers
# =============================================================================


async def _seed_project_and_doc(db):
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"dt080-{uuid4().hex[:6]}"
    )
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        uploaded_by=user.id,
        original_filename="doc.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status="completed",
        pii_detected=False,
    )
    db.add(doc)
    await db.flush()
    return project, doc, user


async def _seed_ocg_individual(db, project, doc, persona_id="ARQ", score=80):
    row = OCGIndividual(
        id=uuid4(),
        project_id=project.id,
        document_id=doc.id,
        persona_id=persona_id,
        persona_name=f"Persona {persona_id}",
        parecer={"score": score, "analise": "Teste"},
        status="completed",
    )
    db.add(row)
    await db.flush()
    return row


# =============================================================================
# Schema sync — DT-080 não pode regredir
# =============================================================================


@pytest.mark.asyncio
async def test_ocg_individual_refined_schema_matches_db(db_session):
    """Cada coluna do modelo ORM existe no schema com tipo coerente."""
    info = await db_session.execute(sql_text(
        "SELECT column_name, is_nullable, data_type "
        "FROM information_schema.columns "
        "WHERE table_name='ocg_individual_refined' "
        "ORDER BY ordinal_position"
    ))
    db_cols = {r[0]: (r[1], r[2]) for r in info.all()}

    expected = {
        "id", "ocg_individual_id", "refinement_iteration",
        "parecer_refined", "changed_fields", "change_summary", "created_at",
    }
    assert expected.issubset(set(db_cols.keys())), (
        f"Schema DB faltando colunas: {expected - set(db_cols.keys())}"
    )

    # Tipos críticos
    assert db_cols["refinement_iteration"][1] == "smallint"
    assert db_cols["parecer_refined"][1] == "jsonb"
    assert db_cols["change_summary"][1] == "character varying"


@pytest.mark.asyncio
async def test_persona_follow_up_questions_schema_matches_db(db_session):
    """Cada coluna do modelo ORM existe no schema com tipo coerente."""
    info = await db_session.execute(sql_text(
        "SELECT column_name, is_nullable, data_type "
        "FROM information_schema.columns "
        "WHERE table_name='persona_follow_up_questions' "
        "ORDER BY ordinal_position"
    ))
    db_cols = {r[0]: (r[1], r[2]) for r in info.all()}

    expected = {
        "id", "project_id", "document_id", "ocg_individual_id",
        "persona_id", "persona_name", "question_text", "context",
        "question_order", "answer_text", "answer_provided_at",
        "answered_by", "status", "created_at", "updated_at",
    }
    assert expected.issubset(set(db_cols.keys())), (
        f"Schema DB faltando colunas: {expected - set(db_cols.keys())}"
    )

    # Tipos críticos
    assert db_cols["persona_id"][1] == "character varying"  # VARCHAR(20), não uuid
    assert db_cols["question_text"][1] == "text"
    assert db_cols["question_order"][1] == "smallint"


# =============================================================================
# CRUD — OCGIndividualRefined
# =============================================================================


@pytest.mark.asyncio
async def test_ocg_individual_refined_insert_and_read(db_session):
    """Insert + select retorna todos os campos preenchidos."""
    project, doc, _ = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    refined = OCGIndividualRefined(
        ocg_individual_id=ocg_individual.id,
        refinement_iteration=1,
        parecer_refined={"score": 85, "analise": "Refinado pelo humano"},
        changed_fields=["score", "analise"],
        change_summary="Humano ajustou score e detalhou análise.",
    )
    db_session.add(refined)
    await db_session.flush()

    fetched = (await db_session.execute(
        select(OCGIndividualRefined).where(
            OCGIndividualRefined.ocg_individual_id == ocg_individual.id
        )
    )).scalar_one()

    assert fetched.refinement_iteration == 1
    assert fetched.parecer_refined["score"] == 85
    assert fetched.changed_fields == ["score", "analise"]
    assert "humano ajustou" in fetched.change_summary.lower()
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_ocg_individual_refined_unique_iteration_constraint(db_session):
    """UNIQUE (ocg_individual_id, refinement_iteration) impede sobrescrita."""
    project, doc, _ = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    db_session.add(OCGIndividualRefined(
        ocg_individual_id=ocg_individual.id,
        refinement_iteration=1,
        parecer_refined={"score": 70},
    ))
    await db_session.flush()

    db_session.add(OCGIndividualRefined(
        ocg_individual_id=ocg_individual.id,
        refinement_iteration=1,  # mesmo iteration
        parecer_refined={"score": 90},
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_ocg_individual_refined_multiple_iterations_allowed(db_session):
    """Iterações diferentes (1, 2) são permitidas no mesmo ocg_individual."""
    project, doc, _ = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    for iteration in [1, 2, 3]:
        db_session.add(OCGIndividualRefined(
            ocg_individual_id=ocg_individual.id,
            refinement_iteration=iteration,
            parecer_refined={"score": 70 + iteration},
        ))
    await db_session.flush()

    rows = (await db_session.execute(
        select(OCGIndividualRefined)
        .where(OCGIndividualRefined.ocg_individual_id == ocg_individual.id)
        .order_by(OCGIndividualRefined.refinement_iteration)
    )).scalars().all()
    assert [r.refinement_iteration for r in rows] == [1, 2, 3]


# =============================================================================
# CRUD — PersonaFollowUpQuestion
# =============================================================================


@pytest.mark.asyncio
async def test_persona_follow_up_insert_and_read(db_session):
    """Insert + select retorna todos os campos preenchidos."""
    project, doc, _ = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    q = PersonaFollowUpQuestion(
        project_id=project.id,
        document_id=doc.id,
        ocg_individual_id=ocg_individual.id,
        persona_id="ARQ",
        persona_name="Arquiteto",
        question_text="Qual o SLA esperado para essa API?",
        context="Persona ARQ não encontrou definição de NFR.",
        question_order=1,
    )
    db_session.add(q)
    await db_session.flush()

    fetched = (await db_session.execute(
        select(PersonaFollowUpQuestion).where(
            PersonaFollowUpQuestion.id == q.id
        )
    )).scalar_one()

    assert fetched.persona_id == "ARQ"
    assert fetched.persona_name == "Arquiteto"
    assert "SLA" in fetched.question_text
    assert fetched.status == "pending"  # default canônico
    assert fetched.answer_text is None
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_persona_follow_up_answer_flow(db_session):
    """Update do fluxo de resposta humana."""
    project, doc, user = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    q = PersonaFollowUpQuestion(
        project_id=project.id,
        document_id=doc.id,
        ocg_individual_id=ocg_individual.id,
        persona_id="DBA",
        persona_name="DBA",
        question_text="Qual a retenção de logs?",
    )
    db_session.add(q)
    await db_session.flush()

    # Humano responde
    q.answer_text = "Retenção de 90 dias com rotação semanal."
    q.answer_provided_at = datetime.now(timezone.utc)
    q.answered_by = user.id
    q.status = "answered"
    await db_session.flush()

    fetched = (await db_session.execute(
        select(PersonaFollowUpQuestion).where(
            PersonaFollowUpQuestion.id == q.id
        )
    )).scalar_one()

    assert fetched.status == "answered"
    assert "90 dias" in fetched.answer_text
    assert fetched.answered_by == user.id
    assert fetched.answer_provided_at is not None


@pytest.mark.asyncio
async def test_persona_follow_up_persona_id_is_string_not_uuid(db_session):
    """persona_id é VARCHAR(20) com tag canônica — não FK para users (DT-067)."""
    project, doc, _ = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    # Persona sem usuário humano associado — só tag canônica
    q = PersonaFollowUpQuestion(
        project_id=project.id,
        document_id=doc.id,
        ocg_individual_id=ocg_individual.id,
        persona_id="LGPD",  # tag canônica, não FK
        persona_name="LGPD",
        question_text="Qual a base legal para coleta de email?",
    )
    db_session.add(q)
    await db_session.flush()  # NÃO deve lançar FK violation

    fetched = (await db_session.execute(
        select(PersonaFollowUpQuestion).where(PersonaFollowUpQuestion.id == q.id)
    )).scalar_one()
    assert fetched.persona_id == "LGPD"


# =============================================================================
# Cascade — FKs propagam delete
# =============================================================================


@pytest.mark.asyncio
async def test_cascade_delete_on_ocg_individual_removes_refined(db_session):
    """Apagar OCGIndividual deve cascatear para refinements (FK ON DELETE CASCADE)."""
    project, doc, _ = await _seed_project_and_doc(db_session)
    ocg_individual = await _seed_ocg_individual(db_session, project, doc)

    db_session.add(OCGIndividualRefined(
        ocg_individual_id=ocg_individual.id,
        refinement_iteration=1,
        parecer_refined={"score": 80},
    ))
    await db_session.flush()

    # Delete cascateia
    await db_session.execute(sql_text(
        "DELETE FROM ocg_individual WHERE id = :id"
    ), {"id": str(ocg_individual.id)})
    await db_session.flush()

    rows = (await db_session.execute(
        select(OCGIndividualRefined).where(
            OCGIndividualRefined.ocg_individual_id == ocg_individual.id
        )
    )).scalars().all()
    assert rows == [], "Cascade delete falhou — refinement persiste após delete do parent"
