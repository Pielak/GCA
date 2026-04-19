"""MVP 9 Fase 9.5.2 — Extração de module_id de PDF de template GCA.

Quando o GP faz upload de um PDF preenchido na aba Ingestão, o backend
precisa identificar a qual item do Roadmap o doc se refere para
disparar a transição `aguardando_resposta` → `adicionado` (Fase 9.5.2)
e criar row em `project_deliverables`.

A Fase 9.5.1 embute `module_id` em **3 lugares** pra robustez. Este
módulo tenta extrair na ordem:

  1. Hidden AcroForm field `_gca_module_id` — formato canônico, mais
     confiável (resiste a edição do PDF em qualquer leitor PDF).
  2. Metadata `Subject` no formato `gca-module:{uuid}` — backup quando
     o leitor PDF stripa AcroForm na hora de salvar.
  3. Footer visual `gca-module-id={uuid}` — last resort via regex em
     texto extraído (cobre cenário de PDF re-impresso/digitalizado e
     re-OCR'd).

Retorna `None` quando o PDF não é template GCA (sem nenhum dos 3
sinais). Caller deve tratar como "documento ad-hoc, sem vínculo".
"""
from __future__ import annotations

import io
import re
from typing import Optional
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

HIDDEN_FIELD_NAME = "_gca_module_id"
SUBJECT_PREFIX = "gca-module:"
FOOTER_PATTERN = re.compile(
    r"gca-module-id\s*=\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def extract_module_id(pdf_bytes: bytes) -> Optional[UUID]:
    """Tenta extrair o module_id do PDF nas 3 estratégias.

    Retorna `None` se nenhum sinal for encontrado ou se UUID for inválido.
    Não levanta — failure é silencioso pra não bloquear upload de PDFs
    normais (não-template).
    """
    if not pdf_bytes:
        return None

    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pdf_module_id.pypdf_missing")
        return None

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.debug("pdf_module_id.open_failed", error=str(exc))
        return None

    # Estratégia 1: hidden AcroForm field
    extracted = _from_acroform(reader)
    if extracted:
        return extracted

    # Estratégia 2: metadata Subject
    extracted = _from_metadata(reader)
    if extracted:
        return extracted

    # Estratégia 3: regex em texto extraído (footer)
    extracted = _from_text(reader)
    if extracted:
        return extracted

    return None


def _from_acroform(reader) -> Optional[UUID]:
    try:
        fields = reader.get_form_text_fields() or {}
    except Exception:
        fields = {}
    raw = fields.get(HIDDEN_FIELD_NAME)
    if not raw:
        return None
    return _parse_uuid(str(raw).strip())


def _from_metadata(reader) -> Optional[UUID]:
    try:
        meta = reader.metadata
    except Exception:
        return None
    if not meta:
        return None
    subject = str(meta.subject or "").strip()
    if not subject.lower().startswith(SUBJECT_PREFIX):
        return None
    return _parse_uuid(subject[len(SUBJECT_PREFIX):].strip())


def _from_text(reader) -> Optional[UUID]:
    """Regex sobre o texto extraído da última página (onde o footer mora)."""
    try:
        pages = reader.pages
    except Exception:
        return None
    if not pages:
        return None
    # Footer está na última página — varre só ela pra economizar
    try:
        text = pages[-1].extract_text() or ""
    except Exception:
        return None
    match = FOOTER_PATTERN.search(text)
    if not match:
        return None
    return _parse_uuid(match.group(1))


def _parse_uuid(value: str) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(value)
    except (ValueError, TypeError):
        logger.debug("pdf_module_id.invalid_uuid", value=value[:50])
        return None
