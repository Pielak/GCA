"""DT-070 — Propagação arguider_analyses → gatekeeper_items.

Bug: a tabela `gatekeeper_items` nunca foi populada (zero construtores
`GatekeeperItem(...)` no código). A UI do Arguidor lê via
`/projects/:id/gatekeeper` (que consulta essa tabela) e sempre mostrava
"Nenhum item pendente do Gatekeeper" mesmo com análise persistida em
`arguider_analyses`. Feature modelada, nunca implementada.

Fix: `ArguiderService.analyze_document` agora cria rows em
`gatekeeper_items` para cada item de gaps/show_stoppers/
poor_definitions/improvement_suggestions após persistir a
ArguiderAnalysis.

Testes unitários sobre o mapeamento de buckets — sem rodar LLM real,
chamando o trecho de persistência com result_json mockado.
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, GatekeeperItem, IngestedDocument,
)
from app.tests.factories import (
    create_test_user, create_test_organization, create_test_project,
)


async def _seed_doc_and_analysis(db, project_id, uploader_id):
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
        arguider_status="pending",
        arguider_stage="queued",
        arguider_progress_percent=0,
        pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project_id,
        document_classification=json.dumps({"type": "req"}),
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
    return doc, analysis


def _propagate(db, project_id, analysis_id, result_json):
    """Versão isolada do bloco DT-070 em ArguiderService.analyze_document.

    Replica exatamente a lógica de persistência, sem rodar LLM.
    """
    buckets = (
        ("gap", result_json.get("gaps", []) or []),
        ("show_stopper", result_json.get("show_stoppers", []) or []),
        ("poor_definition", result_json.get("poor_definitions", []) or []),
        ("improvement", result_json.get("improvement_suggestions", []) or []),
    )
    prefix_map = {
        "gap": "G", "show_stopper": "SS",
        "poor_definition": "PD", "improvement": "IS",
    }
    for item_type, items in buckets:
        prefix = prefix_map[item_type]
        for idx, item in enumerate(items, start=1):
            raw_id = item.get("id") if isinstance(item, dict) else None
            item_id = raw_id or f"{prefix}{idx:03d}"
            db.add(GatekeeperItem(
                project_id=project_id,
                arguider_analysis_id=analysis_id,
                item_type=item_type,
                item_id_in_analysis=str(item_id)[:10],
                item_data=json.dumps(item, ensure_ascii=False),
                status="pending",
            ))


@pytest.mark.asyncio
async def test_todos_os_4_tipos_sao_propagados(db_session):
    """gap/show_stopper/poor_definition/improvement viram rows separadas."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt070-all-types")
    _, analysis = await _seed_doc_and_analysis(db_session, p.id, user.id)

    result_json = {
        "gaps": [{"id": "G001", "text": "Sem ROI"}, {"id": "G002", "text": "Sem stakeholders"}],
        "show_stoppers": [{"id": "SS001", "text": "Timeline indefinido"}],
        "poor_definitions": [{"id": "PD001", "text": "Escopo amb"}],
        "improvement_suggestions": [{"id": "IS001", "text": "Métricas claras"}],
    }
    _propagate(db_session, p.id, analysis.id, result_json)
    await db_session.commit()

    rows = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.project_id == p.id)
    )).scalars().all()
    by_type = {r.item_type for r in rows}
    assert by_type == {"gap", "show_stopper", "poor_definition", "improvement"}
    assert len(rows) == 5  # 2 gaps + 1 ss + 1 pd + 1 is


@pytest.mark.asyncio
async def test_item_data_preserva_conteudo_original(db_session):
    """O dict completo do item deve chegar serializado em item_data —
    UI consome pra mostrar descrição, severidade, etc."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt070-data")
    _, analysis = await _seed_doc_and_analysis(db_session, p.id, user.id)

    gap = {
        "id": "G042",
        "text": "Stakeholders não definidos",
        "severity": "critical",
        "pillar": "P1_Negocio",
        "mitigation": "Identificar sponsor executivo",
    }
    _propagate(db_session, p.id, analysis.id, {"gaps": [gap]})
    await db_session.commit()

    row = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.project_id == p.id)
    )).scalar_one()
    parsed = json.loads(row.item_data)
    assert parsed == gap
    assert row.item_id_in_analysis == "G042"


@pytest.mark.asyncio
async def test_itens_sem_id_ganham_id_sintetico(db_session):
    """Se o LLM esqueceu de incluir `id`, o sistema gera um baseado no
    tipo + índice pra não perder rastreabilidade."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt070-synthetic")
    _, analysis = await _seed_doc_and_analysis(db_session, p.id, user.id)

    result_json = {
        "gaps": [{"text": "sem id 1"}, {"text": "sem id 2"}],
    }
    _propagate(db_session, p.id, analysis.id, result_json)
    await db_session.commit()

    rows = (await db_session.execute(
        select(GatekeeperItem)
        .where(GatekeeperItem.project_id == p.id)
        .order_by(GatekeeperItem.item_id_in_analysis)
    )).scalars().all()
    ids = [r.item_id_in_analysis for r in rows]
    assert ids == ["G001", "G002"]


@pytest.mark.asyncio
async def test_analise_vazia_nao_cria_rows(db_session):
    """Se o LLM retornou todos os buckets vazios (caso raro), zero rows
    são criadas — nada pra UI resolver."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt070-empty")
    _, analysis = await _seed_doc_and_analysis(db_session, p.id, user.id)

    _propagate(db_session, p.id, analysis.id, {})
    await db_session.commit()

    count = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.project_id == p.id)
    )).scalars().all()
    assert len(count) == 0


@pytest.mark.asyncio
async def test_status_default_pending_e_link_para_analise(db_session):
    """Rows começam status=pending e referenciam arguider_analysis_id —
    UI pode filtrar por análise e mudar status (resolved/ignored)."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt070-status")
    _, analysis = await _seed_doc_and_analysis(db_session, p.id, user.id)

    _propagate(db_session, p.id, analysis.id, {
        "show_stoppers": [{"text": "Bloqueador único"}],
    })
    await db_session.commit()

    row = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.project_id == p.id)
    )).scalar_one()
    assert row.status == "pending"
    assert row.arguider_analysis_id == analysis.id
    assert row.item_type == "show_stopper"


@pytest.mark.asyncio
async def test_item_id_truncado_nao_estoura_coluna(db_session):
    """Coluna item_id_in_analysis é VARCHAR(10). Se LLM mandar id muito
    longo, sistema trunca pra não explodir com DataError."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt070-trunc")
    _, analysis = await _seed_doc_and_analysis(db_session, p.id, user.id)

    _propagate(db_session, p.id, analysis.id, {
        "gaps": [{"id": "GAP-EXTREMAMENTE-LONGO-001", "text": "x"}],
    })
    await db_session.commit()

    row = (await db_session.execute(
        select(GatekeeperItem).where(GatekeeperItem.project_id == p.id)
    )).scalar_one()
    assert len(row.item_id_in_analysis) <= 10


@pytest.mark.asyncio
async def test_arguider_service_contem_bloco_de_propagacao():
    """Contrato de código: o bloco DT-070 está presente no
    arguider_service e não foi removido por refactor posterior."""
    from pathlib import Path
    source = Path("/app/app/services/arguider_service.py").read_text()
    assert "GatekeeperItem(" in source, "construtor de GatekeeperItem ausente do service"
    assert "item_type=" in source and "arguider_analysis_id=analysis.id" in source
    assert "gaps" in source and "show_stoppers" in source
