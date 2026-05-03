"""Testes da Fase 31.3 do MVP 31 — Política "lixo descartado".

Garante que personas falhas NÃO contaminam:
  - o arguider_analysis entregue ao OCGUpdaterService (Tarefa 1)
  - o ocg_global.parecer_consolidated persistido no banco (Tarefa 2)

E que a auditoria permanece íntegra:
  - persona falha ainda tem row em ocg_individual com status='failed' (Tarefa 3 — regressão)

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp31_phase3_lixo_descartado.py -v"

Banco alvo: gca_test (conftest.py força — DT-034)
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
        slug=f"ph3-{uuid4().hex[:6]}",
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
# Caso 1 — Personas falhas excluídas do arguider_analysis (Tarefa 1)
# =============================================================================

@pytest.mark.asyncio
async def test_failed_persona_excluded_from_arguider_analysis(db_session):
    """9 personas + 2 em personas_failed → arguider_analysis.ocg_individual tem 7 chaves.

    Valida:
      - ocg_individual passado ao updater tem exatamente len(total) - len(failed) chaves
      - personas_excluded_count == 2 no arguider_analysis
      - as duas tags falhadas não aparecem em ocg_individual do updater
    """
    project, doc, _, _ = await _seed_environment(db_session)

    failed = ["AUD", "GP"]  # 2 de 9 falharam (minoria — updater é chamado)
    payload = _build_payload(
        str(doc.id),
        str(project.id),
        personas_failed=failed,
    )

    captured_analysis: dict = {}

    async def _capture_update(*args, **kwargs):
        captured_analysis.update(kwargs.get("arguider_analysis", {}))
        return {"status": "ok", "version_to": 2}

    with patch(
        "app.routers.webhooks.OCGUpdaterService",
        autospec=True,
    ) as MockUpdater:
        mock_instance = MockUpdater.return_value
        mock_instance.update_ocg_from_arguider = AsyncMock(side_effect=_capture_update)

        async with _async_client_with_db(db_session) as client:
            resp = await client.post(_ENDPOINT, json=payload)

    assert resp.status_code == 200, (
        f"Esperado 200, recebido {resp.status_code}: {resp.text}"
    )

    # Updater deve ter sido chamado (minoria falhou)
    mock_instance.update_ocg_from_arguider.assert_awaited_once()

    # ocg_individual filtrado: 9 - 2 = 7 chaves
    ocg_individual = captured_analysis.get("ocg_individual", {})
    assert len(ocg_individual) == 7, (
        f"Esperado 7 chaves em ocg_individual (9 - 2 falhas), "
        f"encontrado {len(ocg_individual)}: {list(ocg_individual.keys())}"
    )

    # personas_excluded_count deve ser 2
    assert captured_analysis.get("personas_excluded_count") == 2, (
        f"personas_excluded_count esperado 2, "
        f"recebido {captured_analysis.get('personas_excluded_count')}"
    )

    # Tags falhadas não devem aparecer
    for tag in failed:
        assert tag not in ocg_individual, (
            f"Tag '{tag}' deveria estar excluída de ocg_individual, mas ainda aparece"
        )

    # Tags ok devem aparecer
    for tag in _TAGS:
        if tag not in failed:
            assert tag in ocg_individual, (
                f"Tag '{tag}' deveria estar em ocg_individual mas está ausente"
            )


# =============================================================================
# Caso 2 — Personas falhas excluídas do ocg_global.parecer_consolidated (Tarefa 2)
# =============================================================================

@pytest.mark.asyncio
async def test_failed_persona_excluded_from_ocg_global_consensus(db_session):
    """9 personas + 2 falhas → parecer_consolidated.parecer_por_persona tem 7 chaves.

    Valida:
      - parecer_por_persona no banco tem exatamente 7 chaves (sem as 2 falhas)
      - personas_excluded_from_consensus lista as 2 tags falhadas
    """
    project, doc, _, _ = await _seed_environment(db_session)

    failed = ["DBA", "SEG"]  # 2 de 9 falharam (minoria)
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

    # Ler parecer_consolidated do banco
    result = await db_session.execute(
        text(
            "SELECT parecer_consolidated FROM ocg_global WHERE document_id = :doc_id"
        ),
        {"doc_id": str(doc.id)},
    )
    row = result.first()
    assert row is not None, "Row de ocg_global não encontrada"

    parecer = row[0]
    if isinstance(parecer, str):
        parecer = json.loads(parecer)

    # parecer_por_persona deve ter 7 chaves (9 - 2 falhas)
    parecer_por_persona = parecer.get("parecer_por_persona", {})
    assert len(parecer_por_persona) == 7, (
        f"Esperado 7 chaves em parecer_por_persona, "
        f"encontrado {len(parecer_por_persona)}: {list(parecer_por_persona.keys())}"
    )

    # Tags falhadas não devem aparecer em parecer_por_persona
    for tag in failed:
        assert tag not in parecer_por_persona, (
            f"Tag '{tag}' deveria estar excluída de parecer_por_persona, mas aparece"
        )

    # personas_excluded_from_consensus deve listar as tags falhadas
    excluidas = parecer.get("personas_excluded_from_consensus", [])
    assert sorted(excluidas) == sorted(failed), (
        f"personas_excluded_from_consensus esperado {sorted(failed)}, "
        f"recebido {sorted(excluidas)}"
    )


# =============================================================================
# Caso 3 — Auditoria: persona falha ainda tem row em ocg_individual (regressão)
# =============================================================================

@pytest.mark.asyncio
async def test_failed_persona_still_preserved_in_ocg_individual(db_session):
    """Persona falha é excluída do updater/consensus MAS preservada em ocg_individual.

    Valida que a política "lixo descartado" não elimina o histórico imutável de auditoria:
      - row em ocg_individual com status='failed' existe para a persona falha
      - error_message está preenchido
      - total de rows em ocg_individual = 9 (todas as personas, mesmo as falhas)
    """
    project, doc, _, _ = await _seed_environment(db_session)

    failed = ["ARQ"]  # 1 de 9 falharam
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

    # Total de rows: todas as 9 personas devem ter registro (inclusive falhas)
    total_count = (await db_session.execute(
        text("SELECT COUNT(*) FROM ocg_individual WHERE document_id = :doc_id"),
        {"doc_id": str(doc.id)},
    )).scalar()
    assert total_count == 9, (
        f"Esperado 9 rows em ocg_individual (inclui falhas), encontrado {total_count}"
    )

    # Row da persona falha deve existir com status='failed'
    result = await db_session.execute(
        text(
            "SELECT status, error_message FROM ocg_individual "
            "WHERE document_id = :doc_id AND persona_id = :persona_id"
        ),
        {"doc_id": str(doc.id), "persona_id": "ARQ"},
    )
    row = result.first()
    assert row is not None, "Row da persona ARQ não encontrada em ocg_individual"
    assert row[0] == "failed", (
        f"Status esperado 'failed' para ARQ, encontrado '{row[0]}'"
    )
    assert row[1] is not None, (
        "error_message deve estar preenchido para persona falha ARQ"
    )

    # Demais personas devem estar 'completed'
    count_ok = (await db_session.execute(
        text(
            "SELECT COUNT(*) FROM ocg_individual "
            "WHERE document_id = :doc_id AND status = 'completed'"
        ),
        {"doc_id": str(doc.id)},
    )).scalar()
    assert count_ok == 8, (
        f"Esperado 8 'completed' (as 8 que não falharam), encontrado {count_ok}"
    )
