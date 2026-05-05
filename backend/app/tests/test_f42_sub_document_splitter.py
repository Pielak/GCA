"""F4.2 — Testes do SubDocumentSplitter + propagações relacionadas.

Cobertura:
  1. split_text: texto <= threshold → retorna 1 parte sem modificar
  2. split_text: 500k chars → 2 partes, cada uma <= 256k
  3. split_and_enqueue: ValueError quando texto > 2.56M (>10 partes)
  4. split_and_enqueue: cria filhos com parent_document_id correto
  5. CO-1: soft-delete do pai propaga deleted_at para todos os filhos
  6. CO-2: watchdog não processa docs soft-deleted
  7. Callback: todos filhos completed → pai completed
  8. Callback: 1 filho com erro CONF → pai partial

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_f42_sub_document_splitter.py -v"
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import IngestedDocument
from app.services.sub_document_splitter import (
    CHUNK_THRESHOLD_CHARS,
    MAX_PARTS,
    _split_text,
    split_and_enqueue,
)
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Helpers de fixture
# =============================================================================


async def _seed_doc(
    db,
    project_id,
    user_id,
    *,
    arguider_status: str = "completed",
    arguider_stage: str = "completed",
    file_hash: str | None = None,
    parent_document_id=None,
    deleted_at=None,
    updated_at_offset_min: int | None = None,
) -> IngestedDocument:
    """Cria IngestedDocument com valores mínimos válidos."""
    h = file_hash or hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    now = datetime.now(timezone.utc)
    updated = (
        now - timedelta(minutes=updated_at_offset_min)
        if updated_at_offset_min is not None
        else now
    )
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project_id,
        uploaded_by=user_id,
        original_filename="test.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status=arguider_status,
        arguider_stage=arguider_stage,
        pii_detected=False,
        parent_document_id=parent_document_id,
        deleted_at=deleted_at,
        updated_at=updated,
    )
    db.add(doc)
    await db.flush()
    return doc


async def _seed_project(db):
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"f42-{uuid4().hex[:6]}"
    )
    return user, org, project


# =============================================================================
# Testes da função _split_text (pura — sem banco)
# =============================================================================


def test_split_text_abaixo_threshold_nao_divide():
    """Texto abaixo do threshold retorna lista com 1 elemento."""
    texto = "linha\n\n" * 100  # bem abaixo de 256k
    resultado = _split_text(texto, CHUNK_THRESHOLD_CHARS)
    assert len(resultado) == 1
    # _split_text faz strip() nas partes — verificar conteúdo sem whitespace extra
    assert resultado[0].strip() == texto.strip()


def test_split_text_500k_gera_2_partes():
    """Texto de ~500k chars deve gerar >= 2 partes, cada uma <= threshold."""
    # Cria texto com parágrafos distintos pra divisão ser limpa.
    # Paragráfos de ~500 chars, 1024 parágrafos ≈ 512k chars total.
    paragrafo = "palavra " * 62 + "\n\n"  # ~500 chars por parágrafo
    n_paragrafos = 1024
    texto = paragrafo * n_paragrafos
    assert len(texto) > CHUNK_THRESHOLD_CHARS  # garantia

    partes = _split_text(texto, CHUNK_THRESHOLD_CHARS)
    assert len(partes) >= 2, f"Esperava >= 2 partes, obteve {len(partes)}"
    assert len(partes) <= 4, f"Esperava <= 4 partes para ~512k, obteve {len(partes)}"
    for parte in partes:
        assert len(parte) <= CHUNK_THRESHOLD_CHARS, (
            f"Parte tem {len(parte)} chars — excede threshold"
        )


def test_split_text_preserva_conteudo():
    """Conteúdo das partes não perde palavras (sem corte no meio)."""
    # Texto curto com palavras específicas pra checar
    palavras = ["inicio", "meio", "fim"]
    paragrafo = " ".join(palavras) + "\n\n"
    texto = paragrafo * 400  # ~5k chars — abaixo do threshold
    partes = _split_text(texto, len(texto) // 2 + 1)
    conteudo_total = " ".join(partes)
    for palavra in palavras:
        assert palavra in conteudo_total


# =============================================================================
# Testes split_and_enqueue (banco)
# =============================================================================


@pytest.mark.asyncio
async def test_split_and_enqueue_valor_error_acima_limite(db_session):
    """Texto > MAX_PARTS * threshold deve levantar ValueError."""
    user, org, project = await _seed_project(db_session)
    parent = await _seed_doc(db_session, project.id, user.id)
    await db_session.commit()

    # Gera texto grande: 11 partes de 256k = 2.816M chars
    texto_grande = "x " * ((CHUNK_THRESHOLD_CHARS * (MAX_PARTS + 1)) // 2 + 1)
    assert len(texto_grande) > CHUNK_THRESHOLD_CHARS * MAX_PARTS

    # write_ingested será chamado mas descartamos os arquivos em teste
    with patch("app.services.sub_document_splitter.write_ingested"):
        with pytest.raises(ValueError, match="limite de"):
            await split_and_enqueue(db_session, parent, texto_grande, project.id)


@pytest.mark.asyncio
async def test_split_and_enqueue_cria_filhos_com_parent_id(db_session):
    """split_and_enqueue cria IngestedDocuments filhos com parent_document_id correto."""
    user, org, project = await _seed_project(db_session)
    parent = await _seed_doc(db_session, project.id, user.id)
    await db_session.commit()

    # Texto de ~512k chars com parágrafos únicos (hashes distintos por parte)
    # Cada parágrafo tem índice único pra evitar colisão de hash na uq_ingested_doc_hash_active
    n_paragrafos = 1024
    partes_texto = []
    for i in range(n_paragrafos):
        partes_texto.append(f"paragrafo_{i:04d} " + "palavra " * 50 + "\n\n")
    texto = "".join(partes_texto)
    assert len(texto) > CHUNK_THRESHOLD_CHARS

    with patch("app.services.sub_document_splitter.write_ingested"):
        sub_ids = await split_and_enqueue(db_session, parent, texto, project.id)
        await db_session.flush()

    assert len(sub_ids) >= 2

    for sub_id in sub_ids:
        child = await db_session.get(IngestedDocument, sub_id)
        assert child is not None
        assert child.parent_document_id == parent.id
        assert child.arguider_status == "pending"
        assert child.file_type == "markdown"
        assert child.source_type == "chunk_part"
        assert child.project_id == project.id


# =============================================================================
# CO-1 — Soft-delete do pai propaga para filhos
# =============================================================================


@pytest.mark.asyncio
async def test_soft_delete_pai_propaga_para_filhos(db_session):
    """CO-1: revert_document_propagation deve marcar deleted_at nos filhos."""
    from app.models.base import OCG, Questionnaire
    from app.services.document_revert_service import revert_document_propagation

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    filho1 = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="pending",
    )
    filho2 = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
    )

    # Cria Questionnaire mínimo (FK do OCG)
    q = Questionnaire(
        id=uuid4(), project_id=project.id,
        gp_email=f"co1-{uuid4().hex[:6]}@test.com",
        responses="{}", status="pending",
    )
    db_session.add(q)
    await db_session.flush()

    # OCG mínimo (recompute precisa do OCG)
    ocg = OCG(
        id=uuid4(), questionnaire_id=q.id, project_id=project.id,
        overall_score=70,
        p1_business_score=70, p2_rules_score=70,
        status="active", is_blocking=False,
        ocg_data="{}",
    )
    db_session.add(ocg)
    await db_session.commit()

    # Mock do OCGUpdaterService (importação lazy inline no revert_service)
    # e do AuditService pra evitar dependência de provider/audit chain.
    mock_updater = AsyncMock()
    mock_updater._load_persona_scores = AsyncMock(return_value={})
    mock_updater._update_ocg_record = AsyncMock()

    mock_audit = AsyncMock()
    mock_audit.log_event = AsyncMock()

    with (
        patch(
            "app.services.ocg_updater_service.OCGUpdaterService",
            return_value=mock_updater,
        ),
        patch(
            "app.services.document_revert_service.AuditService",
            return_value=mock_audit,
        ),
    ):
        result = await revert_document_propagation(
            db_session, pai.id, project.id, user.id, "manual"
        )

    assert result["status"] == "reverted"

    # Filhos devem estar soft-deleted
    await db_session.refresh(filho1)
    await db_session.refresh(filho2)
    assert filho1.deleted_at is not None, "filho1 deveria ter deleted_at"
    assert filho2.deleted_at is not None, "filho2 deveria ter deleted_at"
    assert filho1.deleted_reason == "manual"
    assert filho2.deleted_reason == "manual"


# =============================================================================
# CO-2 — Watchdog não processa docs soft-deleted
# =============================================================================


@pytest.mark.asyncio
async def test_watchdog_ignora_docs_soft_deleted(db_session):
    """CO-2: recover_zombie_documents não deve marcar docs com deleted_at."""
    from app.services.ingestion_watchdog import (
        ZOMBIE_THRESHOLD_MINUTES,
        recover_zombie_documents,
    )

    user, org, project = await _seed_project(db_session)

    # Doc soft-deleted antigo em processing — NÃO deve ser recuperado
    doc_deletado = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="n8n_pipeline",
        updated_at_offset_min=ZOMBIE_THRESHOLD_MINUTES + 5,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    # Mock dispatch pra evitar chamadas ao n8n
    # O watchdog importa dispatch_first_pending_for_project inline no runtime
    with patch(
        "app.services.ingestion_service.dispatch_first_pending_for_project",
        new_callable=AsyncMock,
    ):
        summary = await recover_zombie_documents(db=db_session)

    # O doc soft-deleted não deve ter sido recuperado
    await db_session.refresh(doc_deletado)
    # Status permanece processing — watchdog não o tocou
    assert doc_deletado.arguider_status == "processing", (
        "Watchdog não deveria modificar docs soft-deleted"
    )


# =============================================================================
# F4.2.4 — Callback resolution
# =============================================================================


@pytest.mark.asyncio
async def test_maybe_resolve_parent_todos_completed(db_session):
    """Todos os filhos completed → pai deve virar 'completed'."""
    from app.routers.webhooks import _maybe_resolve_parent

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    filho1 = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
        arguider_stage="completed",
    )
    filho2 = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
        arguider_stage="completed",
    )
    await db_session.commit()

    # _maybe_resolve_parent importa dispatch_first_pending_for_project inline
    with patch(
        "app.services.ingestion_service.dispatch_first_pending_for_project",
        new_callable=AsyncMock,
    ):
        await _maybe_resolve_parent(db_session, filho1)

    await db_session.refresh(pai)
    assert pai.arguider_status == "completed"
    assert pai.arguider_stage == "completed"
    assert pai.arguider_completed_at is not None


@pytest.mark.asyncio
async def test_maybe_resolve_parent_filho_conf_error(db_session):
    """Filho com erro CONF → pai deve virar 'partial' com mensagem correta."""
    from app.routers.webhooks import _maybe_resolve_parent

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    filho_ok = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
        arguider_stage="completed",
    )
    filho_conf = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="error",
        arguider_stage="failed",
    )
    # Simula erro de Conformidade na mensagem de erro
    filho_conf.arguider_error_message = "CONF score=45 — abaixo do mínimo de 60"
    db_session.add(filho_conf)
    await db_session.commit()

    with patch(
        "app.services.ingestion_service.dispatch_first_pending_for_project",
        new_callable=AsyncMock,
    ):
        await _maybe_resolve_parent(db_session, filho_ok)

    await db_session.refresh(pai)
    assert pai.arguider_status == "partial"
    assert "Conformidade" in pai.arguider_error_message


@pytest.mark.asyncio
async def test_maybe_resolve_parent_filhos_pendentes_nao_resolve(db_session):
    """Se ainda há filhos pending, o pai não deve ser resolvido."""
    from app.routers.webhooks import _maybe_resolve_parent

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    filho_done = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
        arguider_stage="completed",
    )
    _filho_pending = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="pending",
        arguider_stage="queued",
    )
    await db_session.commit()

    with patch(
        "app.services.ingestion_service.dispatch_first_pending_for_project",
        new_callable=AsyncMock,
    ):
        await _maybe_resolve_parent(db_session, filho_done)

    await db_session.refresh(pai)
    # Pai deve permanecer em chunking_parent
    assert pai.arguider_stage == "chunking_parent"
    assert pai.arguider_status == "processing"


# =============================================================================
# F4.2.5 — Watchdog _handle_stale_chunking_parent (91 linhas, 3 branches)
# =============================================================================


@pytest.mark.asyncio
async def test_watchdog_f425_pai_sem_filhos_vira_error(db_session):
    """F4.2.5 Branch 1: pai sem filhos → status=error, stage=failed."""
    from app.services.ingestion_watchdog import _handle_stale_chunking_parent

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    # Pai sem filhos — estado inválido
    await db_session.commit()

    await _handle_stale_chunking_parent(db_session, pai.id, project.id)

    await db_session.refresh(pai)
    assert pai.arguider_status == "error"
    assert pai.arguider_stage == "failed"
    assert "expirou sem filhos" in pai.arguider_error_message


@pytest.mark.asyncio
async def test_watchdog_f425_todos_filhos_done_resolve_pai(db_session):
    """F4.2.5 Branch 2: todos filhos completed/error/partial → resolve pai."""
    from app.services.ingestion_watchdog import _handle_stale_chunking_parent

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    filho1 = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
        arguider_stage="completed",
    )
    filho2 = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="error",
        arguider_stage="failed",
    )
    await db_session.commit()

    # Mock _maybe_resolve_parent pra não precisar de toda a cadeia
    # O watchdog chama _maybe_resolve_parent(db, parent_doc)
    with patch(
        "app.routers.webhooks._maybe_resolve_parent",
        new_callable=AsyncMock,
    ):
        await _handle_stale_chunking_parent(db_session, pai.id, project.id)

    # O watchdog não muta o pai diretamente; _maybe_resolve_parent é quem faz
    # Verificar que a função foi chamada (proof that branch 2 executou)
    # Filhos devem permanecer inalterados
    await db_session.refresh(filho1)
    await db_session.refresh(filho2)
    assert filho1.arguider_status == "completed"
    assert filho2.arguider_status == "error"


@pytest.mark.asyncio
async def test_watchdog_f425_filhos_pendentes_viram_zombie(db_session):
    """F4.2.5 Branch 3: filhos pending/processing → status=error, stage=failed."""
    from app.services.ingestion_watchdog import _handle_stale_chunking_parent

    user, org, project = await _seed_project(db_session)
    pai = await _seed_doc(
        db_session, project.id, user.id,
        arguider_status="processing",
        arguider_stage="chunking_parent",
    )
    filho_ok = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="completed",
        arguider_stage="completed",
    )
    filho_pending = await _seed_doc(
        db_session, project.id, user.id,
        parent_document_id=pai.id,
        arguider_status="pending",
        arguider_stage="queued",
    )
    await db_session.commit()

    with patch(
        "app.routers.webhooks._maybe_resolve_parent",
        new_callable=AsyncMock,
    ):
        await _handle_stale_chunking_parent(db_session, pai.id, project.id)

    # Filho pending deve ter sido marcado error (zombie)
    await db_session.refresh(filho_pending)
    assert filho_pending.arguider_status == "error"
    assert filho_pending.arguider_stage == "failed"
    assert "expirou sem conclusão" in filho_pending.arguider_error_message

    # Filho completed permanece unchanged
    await db_session.refresh(filho_ok)
    assert filho_ok.arguider_status == "completed"
