"""MVP 24 Fase 24.2 — Detector + parser + aplicador de PDF respondido.

Contrato canônico (Fase 24.1):
  - Todo form field começa com `Q_`.
  - `Q_<uuid>` → resposta textual (text/dropdown).
  - `Q_<uuid>__cb_<idx>` → checkbox de opção; checked = opção em `options[idx]`.
  - `Q_<uuid>__cb_outros` + `Q_<uuid>__outros` → adiciona "Outros: <texto>".
  - `Q__COMPLEMENTS` → texto livre de complementos.

PDF sem nenhum field `Q_<uuid>` → não é questionário GCA (detector retorna False).

O aplicador:
  - Para cada UUID respondido, busca o `GatekeeperItem` do projeto e marca
    `status=resolved` com `resolution_note` = resposta canônica.
  - UUIDs inexistentes ou de outro projeto são ignorados (compartimentalização §2.2).
  - Campo Complementos vira `IngestedDocument` extra (file_type=txt) com
    `arguider_status=pending` — fluxo normal de análise.
  - Perguntas não respondidas ficam pending (dívida informacional; Fase 24.3
    promove à info_debt no backlog).
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import GatekeeperItem, IngestedDocument

logger = structlog.get_logger(__name__)


#: Padrão canônico do form field: Q_<uuid> (uuid v4 permissivo — aceita
#: qualquer string com letras/dígitos/hífens que o reportlab aceitou).
_FIELD_ID_RE = re.compile(r"^Q_([A-Za-z0-9\-]+)(?:__(cb_\d+|cb_outros|outros))?$")
_COMPLEMENTS_FIELD = "Q__COMPLEMENTS"
_OFFERED_IDS_FIELD = "Q__OFFERED_IDS"  # Fase 24.3

#: Valores "checado" canônicos que pypdf devolve (varia por PDF writer).
_CHECKED = {"/Yes", "Yes", "yes", "true", "1", "On", "/On"}


@dataclass(frozen=True)
class ItemAnswer:
    """Resposta canônica de um GatekeeperItem."""
    item_id: str                # UUID (string) do GatekeeperItem
    text: Optional[str] = None
    selected: tuple[str, ...] = ()      # opções marcadas (via índice)
    outros: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return (
            not (self.text or "").strip()
            and not self.selected
            and not (self.outros or "").strip()
        )

    def to_note(self) -> str:
        """Serialização canônica pra `resolution_note`."""
        parts: list[str] = []
        if self.text and self.text.strip():
            parts.append(self.text.strip())
        if self.selected:
            parts.append("Opções: " + ", ".join(self.selected))
        if self.outros and self.outros.strip():
            parts.append(f"Outros: {self.outros.strip()}")
        return " · ".join(parts)


@dataclass(frozen=True)
class ParsedQuestionnaire:
    answers: tuple[ItemAnswer, ...] = ()
    complements: Optional[str] = None
    offered_ids: tuple[str, ...] = ()

    @property
    def answered_ids(self) -> set[str]:
        return {a.item_id for a in self.answers if not a.is_empty}

    @property
    def skipped_ids(self) -> set[str]:
        """IDs oferecidos no PDF mas deixados em branco pelo GP."""
        return set(self.offered_ids) - self.answered_ids


# ─── Detector ─────────────────────────────────────────────────────────


def is_gca_questionnaire_pdf(file_bytes: bytes) -> bool:
    """True se o PDF carrega pelo menos um field Q_<uuid> canônico.

    Não consome nem falha em PDFs sem AcroForm — retorna False. Qualquer
    erro de parsing é tratado como "não é questionário GCA".
    """
    try:
        raw = _load_fields(file_bytes)
    except Exception as exc:
        logger.debug("arguider_parser.detect_failed", error=str(exc))
        return False
    for name in raw.keys():
        m = _FIELD_ID_RE.match(name)
        if m and m.group(1):
            return True
    return False


# ─── Parser ───────────────────────────────────────────────────────────


def parse_questionnaire_pdf(file_bytes: bytes) -> ParsedQuestionnaire:
    """Extrai respostas canônicas + complementos. Sempre retorna ParsedQuestionnaire."""
    raw = _load_fields(file_bytes)

    # Indexa por UUID → buckets {text, checkboxes{idx:bool}, outros_cb, outros_text}
    by_uuid: dict[str, dict[str, Any]] = {}
    complements: Optional[str] = None
    offered_ids: tuple[str, ...] = ()

    for name, value in raw.items():
        if name == _COMPLEMENTS_FIELD:
            v = _normalize_text(value)
            if v:
                complements = v
            continue
        if name == _OFFERED_IDS_FIELD:
            v = _normalize_text(value)
            if v:
                offered_ids = tuple(x.strip() for x in v.split(",") if x.strip())
            continue

        m = _FIELD_ID_RE.match(name)
        if not m:
            continue
        uid, suffix = m.group(1), m.group(2)
        bucket = by_uuid.setdefault(uid, {
            "text": None, "checked": [], "outros_cb": False, "outros_text": None,
        })

        if suffix is None:
            # Q_<uuid> — text ou dropdown
            v = _normalize_text(value)
            if v and v != "Selecione...":
                bucket["text"] = v
        elif suffix.startswith("cb_") and suffix != "cb_outros":
            # Q_<uuid>__cb_<idx>
            try:
                idx = int(suffix.split("_", 1)[1])
            except (ValueError, IndexError):
                continue
            if _is_checked(value):
                bucket["checked"].append(idx)
        elif suffix == "cb_outros":
            if _is_checked(value):
                bucket["outros_cb"] = True
        elif suffix == "outros":
            v = _normalize_text(value)
            if v:
                bucket["outros_text"] = v

    # Para reconstruir labels do checkbox, precisamos consultar o template — o
    # aplicador tem acesso ao item_data. Aqui passamos os ÍNDICES; aplicador
    # mapeia pra label no item_data.options. Esse é o contrato: o parser é
    # puramente sintático; a semântica fica na aplicação.
    answers = tuple(
        ItemAnswer(
            item_id=uid,
            text=b["text"],
            selected=tuple(f"__index__{i}" for i in sorted(set(b["checked"]))),
            outros=b["outros_text"] if b["outros_cb"] else None,
        )
        for uid, b in by_uuid.items()
    )
    return ParsedQuestionnaire(
        answers=answers, complements=complements, offered_ids=offered_ids,
    )


# ─── Aplicador ────────────────────────────────────────────────────────


@dataclass
class ApplicationReport:
    applied: int = 0
    skipped_blank: int = 0
    skipped_not_found: int = 0
    complements_document_id: Optional[str] = None
    resolved_codes: list[str] = field(default_factory=list)
    info_debt_promoted: list[str] = field(default_factory=list)  # Fase 24.3

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "skipped_blank": self.skipped_blank,
            "skipped_not_found": self.skipped_not_found,
            "complements_document_id": self.complements_document_id,
            "resolved_codes": self.resolved_codes,
            "info_debt_promoted": self.info_debt_promoted,
        }


async def apply_parsed_responses(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    parsed: ParsedQuestionnaire,
) -> ApplicationReport:
    """Aplica respostas parseadas nos GatekeeperItem do projeto.

    - Compartimentalização §2.2: item precisa pertencer ao `project_id`
      solicitado. Cross-project → skipped silenciosamente + log warning.
    - UUID malformado → skipped_not_found.
    - Item já resolved → skipped_blank (não sobrescreve; idempotente).
    - Complementos (se houver) → cria IngestedDocument txt separado; o
      pipeline normal de ingestão processa depois.
    """
    report = ApplicationReport()

    for answer in parsed.answers:
        if answer.is_empty:
            report.skipped_blank += 1
            continue
        try:
            item_uuid = UUID(answer.item_id)
        except (ValueError, AttributeError):
            report.skipped_not_found += 1
            continue

        item = await db.get(GatekeeperItem, item_uuid)
        if item is None or item.project_id != project_id:
            report.skipped_not_found += 1
            continue
        if item.status != "pending":
            # já resolvido antes — idempotente
            report.skipped_blank += 1
            continue

        # Materializa opções pelo item_data.options (ou suggestions).
        try:
            data = json.loads(item.item_data) if item.item_data else {}
        except (TypeError, ValueError):
            data = {}
        options_pool = data.get("options") if isinstance(data.get("options"), list) else (
            data.get("suggestions") if isinstance(data.get("suggestions"), list) else []
        )
        resolved_selected: list[str] = []
        for token in answer.selected:
            if token.startswith("__index__"):
                try:
                    idx = int(token.removeprefix("__index__"))
                except ValueError:
                    continue
                if 0 <= idx < len(options_pool):
                    resolved_selected.append(str(options_pool[idx]))
            else:
                resolved_selected.append(token)

        final_answer = ItemAnswer(
            item_id=answer.item_id,
            text=answer.text,
            selected=tuple(resolved_selected),
            outros=answer.outros,
        )

        item.status = "resolved"
        item.resolved_by = actor_id
        item.resolved_at = datetime.now(timezone.utc)
        item.resolution_note = final_answer.to_note()
        db.add(item)

        report.applied += 1
        report.resolved_codes.append(item.item_id_in_analysis or "")

    # Fase 24.3 — Dívida informacional: items oferecidos mas não respondidos
    # neste round recebem bump de skip_count; se cruzar o threshold, viram
    # BacklogItem category=info_debt priority=critical.
    if parsed.skipped_ids:
        from app.services.info_debt_service import bump_skipped
        promoted = await bump_skipped(db, project_id, parsed.skipped_ids)
        report.info_debt_promoted = [str(u) for u in promoted]

    # Complementos → novo IngestedDocument (o pipeline Arguidor pega depois)
    if parsed.complements:
        compl_doc = IngestedDocument(
            project_id=project_id,
            filename=f"complements_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt",
            original_filename="complementos_questionario.txt",
            file_type="txt",
            document_category="arguider_complements",
            file_hash=_hash_text(parsed.complements),
            file_size_bytes=len(parsed.complements.encode("utf-8")),
            uploaded_by=actor_id,
            arguider_status="pending",
        )
        db.add(compl_doc)
        await db.flush()
        report.complements_document_id = str(compl_doc.id)

    await db.flush()

    # Fase 24.4 — cascateamento ativo: audit canônico + Celery task.
    # Disparo só quando de fato houve aplicação OU promoção de dívida;
    # questionário vazio não entope a fila.
    if report.applied > 0 or report.info_debt_promoted or report.complements_document_id:
        from app.services.audit_service import AuditEvents, AuditService
        try:
            await AuditService(db).log_event(
                event_type=AuditEvents.RNF_QUESTIONNAIRE_APPLIED,
                resource_type="project",
                actor_id=actor_id,
                resource_id=project_id,
                details={
                    "project_id": str(project_id),
                    **report.to_dict(),
                },
            )
            await db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "arguider_questionnaire.audit_failed",
                project_id=str(project_id), error=str(exc)[:300],
            )

        try:
            from app.tasks.pipeline import propagate_questionnaire_impact_task
            propagate_questionnaire_impact_task.delay(
                str(project_id), report.to_dict(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "arguider_questionnaire.cascade_enqueue_failed",
                project_id=str(project_id), error=str(exc)[:300],
            )

    logger.info(
        "arguider_questionnaire.applied",
        project_id=str(project_id),
        **report.to_dict(),
    )
    return report


# ─── Internals ────────────────────────────────────────────────────────


def _load_fields(file_bytes: bytes) -> dict[str, Any]:
    """Carrega todos os fields AcroForm como dict {name: raw_value}."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    raw_fields = reader.get_fields() or {}

    flat: dict[str, Any] = {}
    for name, field_obj in raw_fields.items():
        val: Any = None
        if hasattr(field_obj, "value"):
            val = field_obj.value
        elif isinstance(field_obj, dict):
            val = field_obj.get("/V")
        flat[name] = val

    # Também os text fields via API dedicada (algumas combinações de writer)
    text_fields = reader.get_form_text_fields() or {}
    for name, val in text_fields.items():
        if val and (name not in flat or not flat.get(name)):
            flat[name] = val

    return flat


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _is_checked(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    return s in _CHECKED or s.lower() in {"yes", "true", "1", "on"}


def _hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
