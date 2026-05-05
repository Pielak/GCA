"""F4.2 — Divisão de documentos grandes em sub-ingestões.

Quando um documento ultrapassa CHUNK_THRESHOLD_CHARS (256k chars), este
serviço divide o texto em partes <= ao threshold e cria IngestedDocuments
filhos no banco. O pai assume arguider_stage='chunking_parent' e aguarda
todos os filhos terminarem.

Decisão arquitetural (CO-3):
  Opção A adotada — sub-docs NÃO entram na fila geral (WHERE parent_document_id
  IS NULL). O pai, ao ser marcado 'chunking_parent', despacha os filhos
  sequencialmente via este módulo. Filhos retornam ao pai via
  _maybe_resolve_parent (F4.2.4) quando todos terminam. Benefícios:
    - Fila geral não mistura pai e filhos (evita dispatch duplo).
    - Filhos herdam project_id e garantias de isolamento.
    - Simplicidade: dispatch_first_pending_for_project não precisa de
      lógica especial para sub-docs.

Limites:
  - Threshold: 256k chars (CHUNK_THRESHOLD_CHARS).
  - Máximo de partes: 10 (>2.56M chars → ValueError).
  - Quebra em "\n\n" (parágrafo), depois "\n" (linha). Nunca corta palavra.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import IngestedDocument
from app.utils.ingested_storage import write_ingested

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Limiar: documentos acima disso são divididos.
CHUNK_THRESHOLD_CHARS = 256_000
# Teto de partes: 10 * 256k = 2.56M chars. Acima disso → ValueError.
MAX_PARTS = 10


def _split_text(text: str, max_chars: int) -> list[str]:
    """Divide texto em partes <= max_chars sem cortar no meio de palavra.

    Tenta quebrar em parágrafo ("\n\n"), depois em linha ("\n").
    Se nenhum separador couber, faz split forçado no limite (caso excepcional
    com bloco de texto contínuo > max_chars).
    """
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        # Tenta parágrafo
        cut = remaining.rfind("\n\n", 0, max_chars)
        if cut == -1:
            # Tenta linha
            cut = remaining.rfind("\n", 0, max_chars)
        if cut == -1:
            # Último recurso: corte no limite
            cut = max_chars

        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip("\n")

    if remaining.strip():
        parts.append(remaining.strip())

    return [p for p in parts if p]


async def split_and_enqueue(
    db: AsyncSession,
    parent_doc: IngestedDocument,
    extracted_text: str,
    project_id: UUID,
) -> list[UUID]:
    """Divide texto em partes e cria IngestedDocuments filhos.

    Cada filho herda project_id, uploaded_by e recebe:
      - file_type='markdown' (conteúdo texto normalizado)
      - source_type='chunk_part'
      - parent_document_id apontando pro pai
      - filename único (uuid + '.md')
      - file_hash = SHA256 do conteúdo da parte

    O conteúdo de cada parte é salvo em disco via write_ingested.

    Args:
        db: sessão assíncrona ativa.
        parent_doc: IngestedDocument pai (deve existir no DB).
        extracted_text: texto extraído do doc pai (chars > CHUNK_THRESHOLD_CHARS).
        project_id: UUID do projeto (validação canônica).

    Returns:
        Lista de UUIDs dos filhos criados, na ordem das partes.

    Raises:
        ValueError: se o texto gera mais de MAX_PARTS partes (> 2.56M chars).
    """
    parts = _split_text(extracted_text, CHUNK_THRESHOLD_CHARS)

    if len(parts) > MAX_PARTS:
        raise ValueError(
            f"Documento excede o limite de {MAX_PARTS} partes "
            f"({len(parts)} geradas, {len(extracted_text):,} chars). "
            f"Reduza o documento para no máximo {MAX_PARTS * CHUNK_THRESHOLD_CHARS:,} chars "
            f"antes de ingerir."
        )

    logger.info(
        "sub_document_splitter.split_start",
        parent_document_id=str(parent_doc.id),
        project_id=str(project_id),
        total_chars=len(extracted_text),
        partes=len(parts),
    )

    sub_ids: list[UUID] = []
    now = datetime.now(timezone.utc)

    for idx, part_text in enumerate(parts):
        part_bytes = part_text.encode("utf-8")
        part_hash = hashlib.sha256(part_bytes).hexdigest()
        part_filename = f"{uuid4()}.md"
        part_id = uuid4()

        # Salva conteúdo em disco antes do INSERT para garantir que, se
        # flush falhar, não há arquivo órfão no banco sem conteúdo.
        write_ingested(project_id, part_filename, part_bytes)

        child = IngestedDocument(
            id=part_id,
            project_id=project_id,
            filename=part_filename,
            # Nome legível: original_filename do pai + sufixo de parte
            original_filename=(
                f"{parent_doc.original_filename or 'documento'}"
                f" [parte {idx + 1}/{len(parts)}]"
            ),
            file_type="markdown",
            source_type="chunk_part",
            file_hash=part_hash,
            file_size_bytes=len(part_bytes),
            uploaded_by=parent_doc.uploaded_by,
            arguider_status="pending",
            arguider_stage="queued",
            arguider_progress_percent=0,
            parent_document_id=parent_doc.id,
            content_status="available",
            is_canonical_decision=parent_doc.is_canonical_decision,
            created_at=now,
            updated_at=now,
        )
        db.add(child)
        sub_ids.append(part_id)

    await db.flush()

    logger.info(
        "sub_document_splitter.split_done",
        parent_document_id=str(parent_doc.id),
        project_id=str(project_id),
        filhos_criados=len(sub_ids),
    )

    return sub_ids
