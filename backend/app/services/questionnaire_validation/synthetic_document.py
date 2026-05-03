"""MVP 35 Fase 35.5 — IngestedDocument sintético para questionário submetido.

Quando GP submete o questionário técnico, criamos um IngestedDocument
correspondente para ele aparecer na aba Ingestão (decisão GP #2).
Comportamento canônico:

- file_type='questionnaire' (Arq-M3)
- file_hash = sha256(canonical(responses)) (Arq-M2 + DBA-M1 idempotência)
- arguider_status='completed' (NÃO entra no pipeline n8n/Celery — Arq-M1)
- arguider_stage='questionnaire_synthetic'
- filename='questionnaire-{questionnaire.id}.json' (sem arquivo físico)
- file_size_bytes = len(responses serializadas)
- original_filename = 'Questionário Técnico — {project.name}'

Idempotência (Arq-M2 + DBA-M1):
- Hash canônico: ordena chaves do dict + ordena valores de listas (multiselect).
  Re-submit com respostas idênticas (mesmo conteúdo, qualquer ordem) gera
  mesmo hash → dup-check encontra row existente → retorna ID existente.
- Dup-check: filtra `WHERE deleted_at IS NULL` (Arq-M2 + DBA-M1) — permite
  re-submit pós-soft-delete sem `UniqueViolationError`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import IngestedDocument

logger = structlog.get_logger(__name__)

QUESTIONNAIRE_FILE_TYPE = "questionnaire"
QUESTIONNAIRE_STAGE = "questionnaire_synthetic"


def canonical_responses(responses: dict[str, Any]) -> dict[str, Any]:
    """Normaliza responses para hash idempotente.

    Ordena valores de listas (multiselect Q5/Q6/Q13/Q15) — sem isso,
    `["Python","Go"]` e `["Go","Python"]` gerariam hashes diferentes
    para o mesmo conteúdo semântico.

    NÃO ordena chaves do dict aqui — `json.dumps(sort_keys=True)` cuida disso.
    """
    return {
        k: sorted(v, key=str) if isinstance(v, list) else v
        for k, v in responses.items()
    }


def compute_questionnaire_hash(responses: dict[str, Any]) -> str:
    """SHA256 canônico das respostas para idempotência (Arq-M2)."""
    payload = json.dumps(
        canonical_responses(responses),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def create_or_get_synthetic_document(
    db: AsyncSession,
    project_id: UUID,
    project_name: str,
    questionnaire_id: UUID,
    responses: dict[str, Any],
    uploaded_by: UUID,
) -> tuple[IngestedDocument, bool]:
    """Cria (ou retorna existente idempotente) IngestedDocument sintético do questionário.

    Args:
        db: AsyncSession ativa.
        project_id: UUID do projeto.
        project_name: nome para o original_filename.
        questionnaire_id: TechnicalQuestionnaire.id (vai no filename).
        responses: payload Q1-Q15.
        uploaded_by: UUID do GP que submeteu.

    Returns:
        (IngestedDocument, created): created=True se criou novo,
        False se idempotência detectou row ativa existente com mesmo hash.

    Raises:
        Nenhuma — método é idempotente. uq_ingested_doc_hash + filtro
        deleted_at IS NULL evitam UniqueViolation.
    """
    file_hash = compute_questionnaire_hash(responses)

    # DBA-M1: dup-check com filtro deleted_at IS NULL ANTES do INSERT.
    # uq_ingested_doc_hash é UNIQUE regular (não parcial) — sem este filtro,
    # re-submit pós-soft-delete bate na constraint mesmo com row deletada.
    existing = await db.execute(
        select(IngestedDocument).where(
            IngestedDocument.project_id == project_id,
            IngestedDocument.file_hash == file_hash,
            IngestedDocument.deleted_at.is_(None),
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        logger.info(
            "questionnaire.synthetic_doc_idempotent",
            project_id=str(project_id),
            existing_doc_id=str(found.id),
            file_hash=file_hash[:12],
        )
        return found, False

    # Cria novo IngestedDocument sintético
    payload_bytes = json.dumps(responses, ensure_ascii=False).encode("utf-8")
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project_id,
        uploaded_by=uploaded_by,
        original_filename=f"Questionário Técnico — {project_name}",
        filename=f"questionnaire-{questionnaire_id}.json",
        file_type=QUESTIONNAIRE_FILE_TYPE,
        file_hash=file_hash,
        file_size_bytes=len(payload_bytes),
        # NÃO entra no pipeline — já completed (Arq-M1)
        arguider_status="completed",
        arguider_stage=QUESTIONNAIRE_STAGE,
        arguider_progress_percent=100,
        ocg_updated=True,  # questionário gera OCG via fluxo separado (personas Celery)
        pii_detected=False,
    )
    db.add(doc)
    await db.flush()

    logger.info(
        "questionnaire.synthetic_doc_created",
        project_id=str(project_id),
        doc_id=str(doc.id),
        questionnaire_id=str(questionnaire_id),
        file_hash=file_hash[:12],
    )
    return doc, True
