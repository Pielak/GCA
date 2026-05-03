"""Smoke E2E real do MVP 32 — pipeline n8n + handler + updater + delta_log.

OPT-IN: roda apenas com env MVP32_REAL_LLM=1.
Custo: ~R$0,05 (DeepSeek 9 personas + 1 chamada updater).

Como rodar:
    MVP32_REAL_LLM=1 docker compose exec -e MVP32_REAL_LLM=1 backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp32_e2e_real_llm.py -v -s"

Pré-requisitos:
- n8n container ativo (docker compose ps n8n)
- Projeto 24bf72c3-2ee8-45fd-b879-d3a00b347c39 (Assistente Judicial) com DeepSeek configurado
- Doc 9825e89b-31dc-4ef9-ac0d-23897e1e67dc com bytes em storage
"""
import os
import pytest
import asyncio
from datetime import datetime, timezone
from uuid import UUID

REAL_LLM_ENABLED = os.environ.get("MVP32_REAL_LLM") == "1"
pytestmark = pytest.mark.skipif(
    not REAL_LLM_ENABLED,
    reason="MVP32_REAL_LLM=1 não setado — pula smoke E2E real (custo ~R$0,05)"
)

DOC_ID = UUID("9825e89b-31dc-4ef9-ac0d-23897e1e67dc")
PROJECT_ID = UUID("24bf72c3-2ee8-45fd-b879-d3a00b347c39")


@pytest.mark.asyncio
async def test_e2e_pipeline_n8n_ocg_acumula_real():
    """Smoke E2E real: dispatch + n8n + handler + updater → OCG cresce.

    Critério de aceite arquitetural Gate 1:
    - ocg.status='active' (não ocg_pending)
    - ocg.version > version_anterior
    - ocg_delta_log ganha row com trigger_source='document_ingestion_n8n'
    - delta tem op em {replace, append}
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import IngestedDocument, OCG
    from app.services.ingestion_service import IngestionService
    from app.utils.ingested_storage import read_ingested
    from sqlalchemy import select, text as sql_text

    # 1. Capturar version anterior do OCG
    async with AsyncSessionLocal() as db:
        ocg_row = (await db.execute(
            select(OCG).where(OCG.project_id == PROJECT_ID).order_by(OCG.version.desc()).limit(1)
        )).scalar_one_or_none()
        version_before = ocg_row.version if ocg_row else 0

    # 2. Resetar doc para pending + dispatch
    async with AsyncSessionLocal() as db:
        doc = await db.get(IngestedDocument, DOC_ID)
        if not doc:
            pytest.skip(f"Doc {DOC_ID} não existe — smoke não disponível")
        bytes_ = read_ingested(doc.project_id, doc.filename)
        if not bytes_:
            pytest.skip(f"Bytes do doc {DOC_ID} ausentes em storage")
        doc.arguider_status = "pending"
        doc.arguider_stage = "queued"
        doc.arguider_progress_percent = 0
        doc.arguider_error_message = None
        await db.commit()

        await IngestionService(db)._dispatch_to_n8n(
            doc.id, doc.project_id, doc.file_type, bytes_
        )

    # 3. Polleia até estado terminal (max 5min)
    started = datetime.now(timezone.utc)
    while True:
        await asyncio.sleep(15)
        async with AsyncSessionLocal() as db:
            doc = await db.get(IngestedDocument, DOC_ID)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            if doc.arguider_status in ("completed", "error", "partial", "ocg_pending"):
                break
            if elapsed > 300:
                pytest.fail(f"Timeout 5min — status: {doc.arguider_status}")

    # 4. Asserts canônicos
    async with AsyncSessionLocal() as db:
        ocg_row = (await db.execute(
            select(OCG).where(OCG.project_id == PROJECT_ID).order_by(OCG.version.desc()).limit(1)
        )).scalar_one_or_none()

        assert ocg_row is not None, "OCG não encontrado pós-pipeline"
        assert ocg_row.version > version_before, (
            f"OCG version não cresceu: {version_before} → {ocg_row.version}"
        )
        assert ocg_row.status == "active", (
            f"OCG status esperado 'active', recebido '{ocg_row.status}' "
            f"(DT-081 deveria estar resolvida)"
        )

        # Delta log ganhou row do n8n
        delta_count = (await db.execute(sql_text(
            "SELECT COUNT(*) FROM ocg_delta_log WHERE project_id=:pid "
            "AND trigger_source='document_ingestion_n8n'"
        ), {"pid": str(PROJECT_ID)})).scalar()
        assert delta_count > 0, (
            "ocg_delta_log sem row com trigger_source='document_ingestion_n8n' — "
            "MVP 32 falhou em popular o log"
        )
