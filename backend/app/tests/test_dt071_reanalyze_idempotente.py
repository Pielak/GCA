"""DT-071 — Reanalise idempotente: limpa análise anterior + items derivados.

Dois bugs encadeados no endpoint /reanalyze:

1. **Checkpoint DT-065 sabotava o /reanalyze.** O pipeline `_analyze_async`
   detecta `arguider_analyses` existente pro document_id e pula o LLM,
   indo direto pra `updating_ocg`. Isso é correto no fallback entre
   providers (evita refazer trabalho), mas faz com que o endpoint
   /reanalyze **não reanalise** — simplesmente reusa a análise velha.

2. **Duplicação de items derivados.** Mesmo forçando uma análise nova,
   `gatekeeper_items` e `module_candidates` antigos (vinculados à
   análise anterior) ficam órfãos. Se o GP clicar reanalisar 2x, a
   UI passa a ver N × 2 items pro mesmo doc.

Fix: o endpoint /reanalyze agora deleta, na ordem de FK,
GatekeeperItem → ModuleCandidate → ArguiderAnalysis do document_id
antes de disparar a task async.

Testes de contrato sobre o código fonte + teste unitário simulando
o DELETE em sequência com fixtures isoladas (evita o event loop
issue do TestClient+asyncpg).
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.models.base import (
    ArguiderAnalysis, GatekeeperItem, IngestedDocument, ModuleCandidate,
)
from app.tests.factories import (
    create_test_user, create_test_organization, create_test_project,
)


async def _seed_full(db, project_id, uploader_id, *, num_items=3):
    """Cria doc + análise + N gatekeeper_items + N module_candidates."""
    import hashlib
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project_id,
        uploaded_by=uploader_id,
        original_filename="t.docx",
        filename=f"{uuid4()}.docx",
        file_type="docx",
        file_hash=h,
        file_size_bytes=100,
        arguider_status="completed",
        arguider_stage="completed",
        arguider_progress_percent=100,
        pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project_id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]),
        show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]),
        improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]),
        ocg_fields_to_update=json.dumps([]),
        llm_model="anthropic:claude-haiku-4-5-20251001",
        tokens_used=1000,
        latency_ms=1000,
    )
    db.add(analysis)
    await db.commit()
    for i in range(num_items):
        db.add(GatekeeperItem(
            project_id=project_id,
            arguider_analysis_id=analysis.id,
            item_type="gap",
            item_id_in_analysis=f"G{i+1:03d}",
            item_data=json.dumps({"text": f"gap {i}"}),
            status="pending",
        ))
        db.add(ModuleCandidate(
            project_id=project_id,
            arguider_analysis_id=analysis.id,
            name=f"Módulo {i}",
            description="",
            module_type="feature",
            priority="medium",
            dependencies=json.dumps([]),
            source_document_ids=json.dumps([str(doc.id)]),
            pillar_impact=json.dumps({}),
            ready_for_codegen=False,
        ))
    await db.commit()
    return doc, analysis


async def _simulate_reanalyze_cleanup(db, document_id):
    """Replica o bloco DT-071 do endpoint. Deletar na ordem certa."""
    analysis_ids_q = await db.execute(
        select(ArguiderAnalysis.id).where(ArguiderAnalysis.document_id == document_id)
    )
    analysis_ids = [row[0] for row in analysis_ids_q.all()]
    if analysis_ids:
        await db.execute(
            delete(GatekeeperItem).where(GatekeeperItem.arguider_analysis_id.in_(analysis_ids))
        )
        await db.execute(
            delete(ModuleCandidate).where(ModuleCandidate.arguider_analysis_id.in_(analysis_ids))
        )
        await db.execute(
            delete(ArguiderAnalysis).where(ArguiderAnalysis.id.in_(analysis_ids))
        )
    await db.commit()


@pytest.mark.asyncio
async def test_cleanup_remove_tudo_vinculado_ao_document_id(db_session):
    """Após o cleanup, nenhuma das 3 tabelas deve ter row pro doc."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt071-all")
    doc, analysis = await _seed_full(db_session, p.id, user.id, num_items=3)

    # Confirma baseline
    pre_gk = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.arguider_analysis_id == analysis.id)
    )).scalars().all()
    pre_mc = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.arguider_analysis_id == analysis.id)
    )).scalars().all()
    assert len(pre_gk) == 3
    assert len(pre_mc) == 3

    await _simulate_reanalyze_cleanup(db_session, doc.id)

    post_gk = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.arguider_analysis_id == analysis.id)
    )).scalars().all()
    post_mc = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.arguider_analysis_id == analysis.id)
    )).scalars().all()
    post_an = (await db_session.execute(
        select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == doc.id)
    )).scalars().all()
    assert post_gk == []
    assert post_mc == []
    assert post_an == []


@pytest.mark.asyncio
async def test_cleanup_preserva_items_de_outros_docs_do_mesmo_projeto(db_session):
    """Compartimentalização: deletar análise do doc A não pode afetar
    gatekeeper_items/module_candidates do doc B mesmo projeto."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt071-compart")

    doc_a, an_a = await _seed_full(db_session, p.id, user.id, num_items=2)
    doc_b, an_b = await _seed_full(db_session, p.id, user.id, num_items=4)

    await _simulate_reanalyze_cleanup(db_session, doc_a.id)

    b_gk = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.arguider_analysis_id == an_b.id)
    )).scalars().all()
    b_mc = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.arguider_analysis_id == an_b.id)
    )).scalars().all()
    assert len(b_gk) == 4
    assert len(b_mc) == 4

    # Análise do B permanece
    b_an = (await db_session.execute(
        select(ArguiderAnalysis).where(ArguiderAnalysis.id == an_b.id)
    )).scalar_one_or_none()
    assert b_an is not None


@pytest.mark.asyncio
async def test_cleanup_noop_quando_nao_tem_analise(db_session):
    """Primeira analise do doc — cleanup não encontra nada, não quebra."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt071-noop")
    doc_id = uuid4()

    # Não deve lançar exceção
    await _simulate_reanalyze_cleanup(db_session, doc_id)


def test_endpoint_reanalyze_contem_bloco_de_cleanup():
    """Contrato de código: o bloco DT-071 está no endpoint /reanalyze
    e não foi removido por refactor posterior. Sem ele, DT-065
    checkpoint volta a sabotar reanalise."""
    from pathlib import Path
    source = Path("/app/app/routers/ingestion_router.py").read_text()
    assert "DT-071" in source
    # Deve apagar as 3 tabelas na ordem certa
    idx_gk = source.find("GatekeeperItem)")
    idx_mc = source.find("ModuleCandidate)")
    idx_an = source.find("ArguiderAnalysis.id.in_(analysis_ids)")
    assert idx_gk > 0
    assert idx_mc > 0
    assert idx_an > 0
    assert idx_gk < idx_mc < idx_an, (
        "ordem de DELETE deve respeitar FKs: gatekeeper_items → module_candidates → arguider_analyses"
    )
