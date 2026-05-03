"""Testes da Fase 31.2 do MVP 31 — handler n8n delega ao OCGUpdaterService.

Cobre:
  - POST /webhooks/ingestion-complete insere 9 rows em ocg_individual
  - POST /webhooks/ingestion-complete insere 1 row em ocg_global
  - Upsert idempotente: segundo POST não duplica rows
  - OCGUpdaterService.update_ocg_from_arguider é chamado com trigger_source=TRIGGER_N8N
  - Maioria de personas falhou → updater NÃO é chamado, doc fica 'partial'
  - Persona em personas_failed → ocg_individual.status='failed'

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp31_phase2_ocg_cumulative.py -v"

Banco alvo: gca_test (conftest.py força — DT-034)

Nota sobre event loop:
  Testes usam httpx.AsyncClient + ASGITransport com dependency_overrides no
  app. Isso evita o problema de "Future attached to a different loop" que
  ocorre com TestClient (sync) + handlers async que fazem await na sessão.
"""
import hashlib
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.db.database import get_db
from app.main import app
from app.models.base import (
    IngestedDocument,
    OCG,
    OCGGlobal,
    OCGIndividual,
    Questionnaire,
)
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Constantes de teste
# =============================================================================

# 9 tags canônicas simuladas — subset das 12 personas reais
_TAGS = ["AUD", "GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI", "SEG"]

_API_BASE = "http://test"
_ENDPOINT = "/api/v1/webhooks/ingestion-complete"


def _build_payload(
    doc_id: str,
    project_id: str,
    personas_failed: list | None = None,
    override_executed: list | None = None,
) -> dict:
    """Monta payload IngestionCompletePayload compatível com o handler."""
    executed = override_executed if override_executed is not None else _TAGS
    failed = personas_failed or []

    ocg_individual: dict = {}
    for tag in executed:
        is_failed = tag in failed
        ocg_individual[tag] = {
            "persona_name": f"Persona {tag}",
            "titulo": f"Análise {tag}",
            "analise": f"Resultado da persona {tag}",
            "score": 75 if not is_failed else None,
            **({"error_message": "Timeout na chamada LLM"} if is_failed else {}),
        }

    return {
        "ingestion_id": doc_id,
        "project_id": project_id,
        "status": "completed",
        "overall_score": 78,
        "blocked": False,
        "blocking_reason": None,
        "personas_executed": executed,
        "personas_failed": failed,
        "ocg_individual": ocg_individual,
        "ocg_global_delta": {"delta_key": "valor_delta"},
        "conflicts_resolved": [],
        "consolidated_findings": [
            {"type": "gap", "descricao": "Falta documentação de API"},
            {"type": "blocker", "descricao": "Sem política de backup"},
        ],
        "consolidated_recommendations": [
            {"recomendacao": "Adotar OpenAPI 3.0"}
        ],
        "execution_summary": {"duracao_total_ms": 5200},
    }


# =============================================================================
# Helpers de seed
# =============================================================================

async def _seed_environment(db):
    """Cria usuário + organização + projeto + OCG + documento ingerido."""
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db,
        organization_id=org.id,
        slug=f"ph2-{uuid4().hex[:6]}",
    )

    # OCG mínimo — necessário para o OCGUpdaterService não retornar awaiting_ocg
    q = Questionnaire(
        id=uuid4(),
        project_id=project.id,
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
        project_id=project.id,
        status="READY",
        is_blocking=False,
        ocg_data=json.dumps({
            "PILLAR_SCORES": {
                f"P{i}_pilar": {"score": 75.0} for i in range(1, 8)
            }
        }),
        version=1,
    )
    db.add(ocg)
    await db.flush()

    file_hash = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        uploaded_by=user.id,
        original_filename="spec.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=file_hash,
        file_size_bytes=4096,
        arguider_status="processing",
        pii_detected=False,
    )
    db.add(doc)
    await db.flush()

    return project, doc, user, ocg


@asynccontextmanager
async def _async_client_with_db(db_session):
    """Cria httpx.AsyncClient com ASGITransport injetando a sessão de teste."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=_API_BASE
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


# =============================================================================
# Caso 1 — Insere 9 rows em ocg_individual
# =============================================================================

@pytest.mark.asyncio
async def test_ingestion_complete_inserts_ocg_individual(db_session):
    """POST /ingestion-complete com 9 personas → 9 rows em ocg_individual."""
    project, doc, _, _ = await _seed_environment(db_session)
    payload = _build_payload(str(doc.id), str(project.id))

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(
            return_value={"status": "ok", "version_to": 2}
        )

        async with _async_client_with_db(db_session) as client:
            resp = await client.post(_ENDPOINT, json=payload)

    assert resp.status_code == 200, (
        f"Esperado 200, recebido {resp.status_code}: {resp.text}"
    )

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM ocg_individual WHERE document_id = :doc_id"),
        {"doc_id": str(doc.id)},
    )
    count = result.scalar()
    assert count == 9, f"Esperado 9 rows em ocg_individual, encontrado {count}"


# =============================================================================
# Caso 2 — Insere 1 row em ocg_global
# =============================================================================

@pytest.mark.asyncio
async def test_ingestion_complete_inserts_ocg_global(db_session):
    """POST /ingestion-complete → 1 row em ocg_global."""
    project, doc, _, _ = await _seed_environment(db_session)
    payload = _build_payload(str(doc.id), str(project.id))

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(
            return_value={"status": "ok", "version_to": 2}
        )

        async with _async_client_with_db(db_session) as client:
            resp = await client.post(_ENDPOINT, json=payload)

    assert resp.status_code == 200

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM ocg_global WHERE document_id = :doc_id"),
        {"doc_id": str(doc.id)},
    )
    count = result.scalar()
    assert count == 1, f"Esperado 1 row em ocg_global, encontrado {count}"


# =============================================================================
# Caso 3 — Idempotência: segundo POST não duplica
# =============================================================================

@pytest.mark.asyncio
async def test_ingestion_complete_idempotent_on_retry(db_session):
    """Dois POSTs idênticos → ainda 9 rows em ocg_individual e 1 em ocg_global (upsert)."""
    project, doc, _, _ = await _seed_environment(db_session)
    payload = _build_payload(str(doc.id), str(project.id))

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(
            return_value={"status": "ok", "version_to": 2}
        )

        async with _async_client_with_db(db_session) as client:
            resp1 = await client.post(_ENDPOINT, json=payload)
            resp2 = await client.post(_ENDPOINT, json=payload)

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    ind_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM ocg_individual WHERE document_id = :doc_id"),
        {"doc_id": str(doc.id)},
    )).scalar()
    glo_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM ocg_global WHERE document_id = :doc_id"),
        {"doc_id": str(doc.id)},
    )).scalar()

    assert ind_count == 9, f"Esperado 9 (upsert), encontrado {ind_count}"
    assert glo_count == 1, f"Esperado 1 (upsert), encontrado {glo_count}"


# =============================================================================
# Caso 4 — OCGUpdaterService chamado com trigger_source=TRIGGER_N8N
# =============================================================================

@pytest.mark.asyncio
async def test_ingestion_complete_calls_ocg_updater(db_session):
    """Handler deve chamar OCGUpdaterService com trigger_source=TRIGGER_N8N
    e arguider_analysis contendo as chaves esperadas."""
    from app.services.ocg_updater_service import TRIGGER_N8N

    project, doc, _, _ = await _seed_environment(db_session)
    payload = _build_payload(str(doc.id), str(project.id))

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(
            return_value={"status": "ok", "version_to": 2}
        )

        async with _async_client_with_db(db_session) as client:
            resp = await client.post(_ENDPOINT, json=payload)

    assert resp.status_code == 200

    # Confirmar que o updater foi chamado
    mock_instance.update_ocg_from_arguider.assert_awaited_once()
    call_kwargs = mock_instance.update_ocg_from_arguider.call_args.kwargs

    # Verificar trigger_source
    assert call_kwargs.get("trigger_source") == TRIGGER_N8N, (
        f"trigger_source esperado '{TRIGGER_N8N}', "
        f"recebido '{call_kwargs.get('trigger_source')}'"
    )

    # Verificar chaves obrigatórias no arguider_analysis
    analysis = call_kwargs.get("arguider_analysis", {})
    chaves_obrigatorias = [
        "overall_score", "blocked", "personas_executed", "personas_failed",
        "ocg_individual", "ocg_global_delta", "gaps", "show_stoppers",
        "recommendations",
    ]
    for chave in chaves_obrigatorias:
        assert chave in analysis, (
            f"Chave '{chave}' ausente em arguider_analysis"
        )

    # gaps e show_stoppers devem estar mapeados a partir de consolidated_findings
    assert len(analysis["gaps"]) == 1, "Esperado 1 gap mapeado"
    assert len(analysis["show_stoppers"]) == 1, "Esperado 1 blocker mapeado"


# =============================================================================
# Caso 5 — Maioria falhou: updater NÃO é chamado, doc fica 'partial'
# =============================================================================

@pytest.mark.asyncio
async def test_ingestion_complete_skips_updater_when_majority_failed(db_session):
    """5/9 personas em personas_failed → updater NÃO chamado, doc fica 'partial',
    ocg_individual populado mesmo assim."""
    project, doc, _, _ = await _seed_environment(db_session)

    # 5 de 9 falharam (≥50%)
    failed = _TAGS[:5]  # ["AUD", "GP", "ARQ", "DBA", "DEV"]
    payload = _build_payload(
        str(doc.id),
        str(project.id),
        personas_failed=failed,
    )

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(
            return_value={"status": "ok", "version_to": 2}
        )

        async with _async_client_with_db(db_session) as client:
            resp = await client.post(_ENDPOINT, json=payload)

    assert resp.status_code == 200

    # Updater NÃO deve ter sido chamado
    mock_instance.update_ocg_from_arguider.assert_not_awaited()

    # ocg_individual deve ter sido populado (para auditoria)
    ind_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM ocg_individual WHERE document_id = :doc_id"),
        {"doc_id": str(doc.id)},
    )).scalar()
    assert ind_count == 9, f"Esperado 9 rows em ocg_individual, encontrado {ind_count}"

    # Status do documento deve ser 'partial'
    doc_result = await db_session.execute(
        text(
            "SELECT arguider_status FROM ingested_documents WHERE id = :doc_id"
        ),
        {"doc_id": str(doc.id)},
    )
    doc_status = doc_result.scalar()
    assert doc_status == "partial", f"Esperado 'partial', encontrado '{doc_status}'"


# =============================================================================
# Caso 6 — Persona em personas_failed → status='failed' em ocg_individual
# =============================================================================

@pytest.mark.asyncio
async def test_ingestion_complete_persists_failed_personas_with_status(db_session):
    """Persona em personas_failed → row em ocg_individual com status='failed'."""
    project, doc, _, _ = await _seed_environment(db_session)

    # Apenas AUD falhou (1/9 — minoria, updater é chamado)
    failed = ["AUD"]
    payload = _build_payload(
        str(doc.id),
        str(project.id),
        personas_failed=failed,
    )

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(
            return_value={"status": "ok", "version_to": 2}
        )

        async with _async_client_with_db(db_session) as client:
            resp = await client.post(_ENDPOINT, json=payload)

    assert resp.status_code == 200

    # Verificar que AUD ficou 'failed'
    result = await db_session.execute(
        text(
            "SELECT status, error_message FROM ocg_individual "
            "WHERE document_id = :doc_id AND persona_id = :persona_id"
        ),
        {"doc_id": str(doc.id), "persona_id": "AUD"},
    )
    row = result.first()
    assert row is not None, "Row da persona AUD não encontrada"
    assert row[0] == "failed", f"Status esperado 'failed', encontrado '{row[0]}'"
    assert row[1] is not None, "error_message deve estar preenchido para persona falha"

    # Demais personas devem estar 'completed'
    result_ok = await db_session.execute(
        text(
            "SELECT COUNT(*) FROM ocg_individual "
            "WHERE document_id = :doc_id AND status = 'completed'"
        ),
        {"doc_id": str(doc.id)},
    )
    count_ok = result_ok.scalar()
    assert count_ok == 8, f"Esperado 8 'completed', encontrado {count_ok}"
