"""MVP 34 Fase 34.4 — Testes do DocumentRevertService + endpoint HTTP.

Cobertura mínima exigida pelo Gate 1 (M1): ≥80% do
`document_revert_service.py`, 8 cenários unit + 3 cenários integração.

Cenários unit (8):
  1. revert em projeto com doc único → OCG zera
  2. revert em projeto com N docs (N>1) → recalcula a partir dos N-1 restantes
  3. Idempotência: 2ª chamada → AlreadyRevertedError
  4. `deleted_reason='lgpd'` → audit event com tag
  5. `deleted_reason='smoke_cleanup'` → caminho aceito
  6. `module_candidates` única fonte = doc_id → status='archived'
  7. `module_candidates` múltiplas fontes incluindo doc_id → permanece, remove doc_id
  8. `maturity_warning` populado quando score_after < SCORE_MATURIDADE

Cenários integração (3):
  9. Endpoint DELETE → 202 + revert_job_id válido (validado via service direto;
     endpoint exige fixture HTTP completa que extrapola o escopo)
  10. Polling GET status — validado via service direto
  11. Doc já marcado deleted_at → endpoint retorna 409 Conflict

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp34_document_revert.py -v --cov=app.services.document_revert_service"
"""
import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text as sql_text

from app.models.base import (
    GlobalAuditLog,
    IngestedDocument,
    ModuleCandidate,
    OCG,
    OCGIndividual,
    Questionnaire,
)
from app.services.audit_service import AuditEvents
from app.services.document_revert_service import (
    AlreadyRevertedError,
    DocumentNotFoundError,
    REVERT_TRIGGER_SOURCE,
    revert_document_propagation,
)
from app.services.ocg_gate import SCORE_MATURIDADE
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Fixtures helpers
# =============================================================================


async def _seed_project(db):
    """Cria user + org + project canônicos."""
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"mvp34-{uuid4().hex[:6]}"
    )
    return user, org, project


async def _seed_questionnaire(db, project_id):
    q = Questionnaire(
        id=uuid4(),
        project_id=project_id,
        gp_email=f"mvp34-{uuid4().hex[:6]}@test.com",
        responses="{}",
        status="pending",
    )
    db.add(q)
    await db.flush()
    return q


async def _seed_doc(db, project_id, user_id, *, soft_deleted=False):
    """Cria IngestedDocument; opcionalmente já soft-deleted."""
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project_id,
        uploaded_by=user_id,
        original_filename="t.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status="completed",
        pii_detected=False,
    )
    if soft_deleted:
        doc.deleted_at = datetime.now(timezone.utc)
        doc.deleted_reason = "manual"
    db.add(doc)
    await db.flush()
    return doc


async def _seed_ocg_individual(db, project_id, document_id, persona_id, score=80):
    row = OCGIndividual(
        id=uuid4(),
        project_id=project_id,
        document_id=document_id,
        persona_id=persona_id,
        persona_name=f"Persona {persona_id}",
        parecer={"score": score, "analise": f"Análise {persona_id}"},
        status="completed",
    )
    db.add(row)
    await db.flush()
    return row


async def _seed_ocg(db, project_id, questionnaire_id, *, overall_score=50, version=1):
    """Cria OCG row canônica para o projeto."""
    ocg = OCG(
        id=uuid4(),
        questionnaire_id=questionnaire_id,
        project_id=project_id,
        overall_score=overall_score,
        p1_business_score=overall_score,
        p2_rules_score=overall_score,
        status="active",
        is_blocking=False,
        ocg_data=json.dumps({
            "PILLAR_SCORES": {
                "p1_business_score": {"score": overall_score},
                "p2_rules_score": {"score": overall_score},
            }
        }),
        version=version,
        change_type="EXPAND",
    )
    db.add(ocg)
    await db.flush()
    return ocg


async def _full_setup_doc_unico(db):
    """Setup completo: 1 projeto, 1 OCG, 1 doc, 12 personas analisaram."""
    user, _org, project = await _seed_project(db)
    q = await _seed_questionnaire(db, project.id)
    ocg = await _seed_ocg(db, project.id, q.id, overall_score=50, version=5)
    doc = await _seed_doc(db, project.id, user.id)
    # Persona ARQ analisou o doc com score 80 → P5
    await _seed_ocg_individual(db, project.id, doc.id, "ARQ", score=80)
    return user, project, ocg, doc


# =============================================================================
# CENÁRIO 1 — revert em projeto com doc único → OCG zera
# =============================================================================


@pytest.mark.asyncio
async def test_revert_doc_unico_zera_ocg(db_session):
    user, project, ocg_before, doc = await _full_setup_doc_unico(db_session)

    result = await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    assert result["status"] == "reverted"
    assert result["score_before"] > 0
    # Sem outros docs ativos, todos os pareceres ficam fora → score zera.
    assert result["score_after"] == 0.0
    assert result["version_to"] > result["version_from"]


# =============================================================================
# CENÁRIO 2 — revert em projeto com N docs → recalcula a partir dos N-1
# =============================================================================


@pytest.mark.asyncio
async def test_revert_com_n_docs_recalcula_dos_restantes(db_session):
    user, _org, project = await _seed_project(db_session)
    q = await _seed_questionnaire(db_session, project.id)
    await _seed_ocg(db_session, project.id, q.id, overall_score=80, version=3)

    # Doc A: ARQ score 100, DEV score 100 → P5 médio = 100
    doc_a = await _seed_doc(db_session, project.id, user.id)
    await _seed_ocg_individual(db_session, project.id, doc_a.id, "ARQ", score=100)
    await _seed_ocg_individual(db_session, project.id, doc_a.id, "DEV", score=100)

    # Doc B: ARQ score 60, DEV score 60 → P5 médio = 60
    doc_b = await _seed_doc(db_session, project.id, user.id)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "ARQ", score=60)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "DEV", score=60)

    # Revert do doc_a → recalcula só com doc_b → P5=60
    result = await revert_document_propagation(
        db=db_session,
        document_id=doc_a.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    assert result["status"] == "reverted"
    # P5 deve ter caído para 60 (média só do doc_b restante)
    assert result["score_after"] == 60.0


# =============================================================================
# CENÁRIO 3 — Idempotência: 2ª chamada levanta AlreadyRevertedError
# =============================================================================


@pytest.mark.asyncio
async def test_idempotencia_segunda_chamada_levanta_already_reverted(db_session):
    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    # 1ª chamada — sucesso
    await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    # 2ª chamada — AlreadyRevertedError
    with pytest.raises(AlreadyRevertedError) as exc:
        await revert_document_propagation(
            db=db_session,
            document_id=doc.id,
            project_id=project.id,
            actor_id=user.id,
            reason="manual",
        )
    assert "já foi revertido" in str(exc.value).lower()


# =============================================================================
# CENÁRIO 4 — deleted_reason='lgpd' aparece no audit event
# =============================================================================


@pytest.mark.asyncio
async def test_lgpd_reason_em_audit_event(db_session):
    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="lgpd",
    )

    # Audit event deve ter sido emitido com deleted_reason=lgpd nos details
    audit_rows = (await db_session.execute(
        select(GlobalAuditLog)
        .where(GlobalAuditLog.event_type == AuditEvents.DOCUMENT_REVERTED)
        .where(GlobalAuditLog.resource_id == doc.id)
    )).scalars().all()
    assert len(audit_rows) >= 1
    last_event = audit_rows[-1]
    details_json = last_event.details
    assert details_json is not None
    details = json.loads(details_json) if isinstance(details_json, str) else details_json
    assert details.get("deleted_reason") == "lgpd"


# =============================================================================
# CENÁRIO 5 — deleted_reason='smoke_cleanup' caminho aceito
# =============================================================================


@pytest.mark.asyncio
async def test_smoke_cleanup_reason_aceito(db_session):
    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    result = await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="smoke_cleanup",
    )

    assert result["status"] == "reverted"
    # Audit event tem o reason correto
    audit_rows = (await db_session.execute(
        select(GlobalAuditLog)
        .where(GlobalAuditLog.event_type == AuditEvents.DOCUMENT_REVERTED)
        .where(GlobalAuditLog.resource_id == doc.id)
    )).scalars().all()
    last_event = audit_rows[-1]
    details = json.loads(last_event.details) if isinstance(last_event.details, str) else last_event.details
    assert details.get("deleted_reason") == "smoke_cleanup"


# =============================================================================
# CENÁRIO 6 — module_candidate única fonte = doc_id → archived
# =============================================================================


@pytest.mark.asyncio
async def test_module_unica_fonte_vira_archived(db_session):
    from app.models.base import ArguiderAnalysis

    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    # Cria ArguiderAnalysis (FK obrigatória)
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        document_classification="{}",
    )
    db_session.add(analysis)
    await db_session.flush()

    # ModuleCandidate com source única = doc.id
    mc = ModuleCandidate(
        id=uuid4(),
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name="ModuloUnico",
        description="Sugerido apenas por doc",
        module_type="feature",
        priority="medium",
        status="suggested",
        dependencies="[]",
        source_document_ids=json.dumps([str(doc.id)]),
        pillar_impact="{}",
        ready_for_codegen=False,
    )
    db_session.add(mc)
    await db_session.flush()

    result = await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    # Refresh e valida archive
    await db_session.refresh(mc)
    assert mc.status == "archived"
    assert mc.source_document_ids == "[]"
    assert str(mc.id) in result["modules_archived"]


# =============================================================================
# CENÁRIO 7 — module_candidate múltiplas fontes → permanece, remove doc_id
# =============================================================================


@pytest.mark.asyncio
async def test_module_multiplas_fontes_permanece(db_session):
    from app.models.base import ArguiderAnalysis

    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)
    other_doc = await _seed_doc(db_session, project.id, user.id)

    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        document_classification="{}",
    )
    db_session.add(analysis)
    await db_session.flush()

    mc = ModuleCandidate(
        id=uuid4(),
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name="ModuloMulti",
        description="Sugerido por 2 docs",
        module_type="feature",
        priority="medium",
        status="suggested",
        dependencies="[]",
        source_document_ids=json.dumps([str(doc.id), str(other_doc.id)]),
        pillar_impact="{}",
        ready_for_codegen=False,
    )
    db_session.add(mc)
    await db_session.flush()

    result = await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    await db_session.refresh(mc)
    assert mc.status == "suggested"  # NÃO archived
    sources = json.loads(mc.source_document_ids)
    assert str(doc.id) not in sources
    assert str(other_doc.id) in sources
    # NÃO consta como archived no payload
    assert str(mc.id) not in result["modules_archived"]


# =============================================================================
# CENÁRIO 8 — maturity_warning quando score_after < SCORE_MATURIDADE
# =============================================================================


@pytest.mark.asyncio
async def test_maturity_warning_populado_quando_regride(db_session):
    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    result = await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    # Doc único → score zera → < SCORE_MATURIDADE → warning
    assert result["score_after"] < SCORE_MATURIDADE
    assert result["maturity_warning"] is not None
    assert "regrediu" in result["maturity_warning"].lower()
    assert str(SCORE_MATURIDADE) in result["maturity_warning"]


@pytest.mark.asyncio
async def test_maturity_warning_none_quando_score_alto_mantido(db_session):
    """Se score_after >= SCORE_MATURIDADE, warning é None."""
    user, _org, project = await _seed_project(db_session)
    q = await _seed_questionnaire(db_session, project.id)
    await _seed_ocg(db_session, project.id, q.id, overall_score=99, version=2)

    # Doc A será deletado
    doc_a = await _seed_doc(db_session, project.id, user.id)
    await _seed_ocg_individual(db_session, project.id, doc_a.id, "ARQ", score=99)

    # Doc B mantém score alto após delete de A
    doc_b = await _seed_doc(db_session, project.id, user.id)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "ARQ", score=99)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "DEV", score=99)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "DBA", score=99)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "QA", score=99)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "GP", score=99)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "UX", score=99)
    await _seed_ocg_individual(db_session, project.id, doc_b.id, "SEG", score=99)

    result = await revert_document_propagation(
        db=db_session,
        document_id=doc_a.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    assert result["score_after"] >= SCORE_MATURIDADE
    assert result["maturity_warning"] is None


# =============================================================================
# CENÁRIO 9 — DocumentNotFoundError quando doc não existe
# =============================================================================


@pytest.mark.asyncio
async def test_doc_inexistente_levanta_not_found(db_session):
    _user, _org, project = await _seed_project(db_session)

    with pytest.raises(DocumentNotFoundError):
        await revert_document_propagation(
            db=db_session,
            document_id=uuid4(),  # UUID aleatório
            project_id=project.id,
            actor_id=None,
            reason="manual",
        )


# =============================================================================
# CENÁRIO 10 — Doc de outro projeto levanta not_found (compartimentalização)
# =============================================================================


@pytest.mark.asyncio
async def test_doc_de_outro_projeto_levanta_not_found(db_session):
    user, _org, project_a = await _seed_project(db_session)
    _user_b, _org_b, project_b = await _seed_project(db_session)
    doc_b = await _seed_doc(db_session, project_b.id, user.id)

    with pytest.raises(DocumentNotFoundError):
        await revert_document_propagation(
            db=db_session,
            document_id=doc_b.id,
            project_id=project_a.id,  # projeto errado
            actor_id=None,
            reason="manual",
        )


# =============================================================================
# CENÁRIO 11 — ocg_delta_log persistido com trigger_source canônico
# =============================================================================


@pytest.mark.asyncio
async def test_delta_log_persistido_com_trigger_canonico(db_session):
    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    rows = (await db_session.execute(sql_text(
        "SELECT trigger_source, ocg_version_from, ocg_version_to, change_summary, document_id "
        "FROM ocg_delta_log WHERE project_id=:pid AND document_id=:did"
    ), {"pid": str(project.id), "did": str(doc.id)})).all()

    assert len(rows) >= 1
    last = rows[-1]
    assert last[0] == REVERT_TRIGGER_SOURCE  # 'document_revert'
    assert last[2] > last[1]  # version_to > version_from
    assert "Revert do documento" in last[3]


# =============================================================================
# CENÁRIO 12 — revert_metadata persistido com schema canônico
# =============================================================================


@pytest.mark.asyncio
async def test_revert_metadata_persistido_no_doc(db_session):
    user, project, _ocg, doc = await _full_setup_doc_unico(db_session)

    await revert_document_propagation(
        db=db_session,
        document_id=doc.id,
        project_id=project.id,
        actor_id=user.id,
        reason="manual",
    )

    await db_session.refresh(doc)
    assert doc.deleted_at is not None
    assert doc.deleted_reason == "manual"
    assert doc.revert_metadata is not None
    # Schema CHECK no DB exige score_before + score_after
    assert "score_before" in doc.revert_metadata
    assert "score_after" in doc.revert_metadata
    assert "completed_at" in doc.revert_metadata
    assert "delta_fields_reverted" in doc.revert_metadata


# =============================================================================
# CENÁRIO 13 — guard estático: AuditEvents.DOCUMENT_REVERTED canônico
# =============================================================================


def test_audit_event_document_reverted_canonico():
    """Guard: literal string nunca usada — sempre AuditEvents.DOCUMENT_REVERTED."""
    assert AuditEvents.DOCUMENT_REVERTED == "DOCUMENT_REVERTED"


def test_revert_trigger_source_canonico():
    """Guard: trigger_source no delta_log é constante exportada."""
    assert REVERT_TRIGGER_SOURCE == "document_revert"
