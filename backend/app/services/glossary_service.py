"""MVP 19 Fase 19.3 — Glossário vivo por projeto.

Extrai termos candidatos do corpus já processado pelo pipeline do projeto
(análises do Arguidor, itens do Gatekeeper, descrições de módulos, OCG
PROJECT_PROFILE). NÃO re-extrai arquivos do Git — opera só sobre texto
que já está no banco.

Ciclo de vida de um termo:
  candidate → approved → entra no ERS (seção 1.3)
  candidate → rejected → não aparece (nem volta a ser extraído)

Extração é idempotente: rodar 2x não cria duplicatas (UNIQUE no DB).
Classificação (aprovar/rejeitar/editar) é manual pelo GP.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    ArguiderAnalysis,
    GatekeeperItem,
    ModuleCandidate,
    OCG,
    ProjectGlossaryTerm,
)


logger = structlog.get_logger(__name__)


# ============================================================================
# Constantes canônicas
# ============================================================================

STATUS_CANDIDATE = "candidate"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
_ALLOWED_STATUSES = {STATUS_CANDIDATE, STATUS_APPROVED, STATUS_REJECTED}

SOURCE_INGESTED_DOC = "ingested_doc"
SOURCE_ARGUIDER_RESPONSE = "arguider_response"
SOURCE_MODULE_DESCRIPTION = "module_description"
SOURCE_OCG_PROFILE = "ocg_profile"
SOURCE_MANUAL = "manual"
_ALLOWED_SOURCES = {
    SOURCE_INGESTED_DOC,
    SOURCE_ARGUIDER_RESPONSE,
    SOURCE_MODULE_DESCRIPTION,
    SOURCE_OCG_PROFILE,
    SOURCE_MANUAL,
}


# Stopwords pra filtrar siglas que não são realmente termos de domínio.
# Palavras curtas comuns em pt-BR escritas em maiúsculas ocasionalmente
# batem no regex (ex: títulos, rótulos). Lista minimalista e canônica.
_SIGLA_STOPWORDS = {
    # Conjunções/preposições maiúsculas em títulos
    "DE", "DO", "DA", "DOS", "DAS", "EM", "NO", "NA", "NOS", "NAS",
    "OU", "SE", "EU", "TU", "ME", "TE", "MY", "OR", "IF", "IS", "AT",
    "IN", "ON", "OF", "TO", "BY", "IT", "AS", "BE", "AN", "AM", "ID",
    # Pronomes/abreviações comuns
    "PT", "EN", "BR", "US", "UK",
    # Siglas internas que já estão no help global (não vamos duplicar).
    # Nota: o generator do ERS referencia o help pra acrônimos do GCA.
    # Não listamos aqui pra permitir ao projeto glosar termos próprios
    # com mesma grafia (raro mas possível).
}

# Regex de siglas: começa com letra maiúscula, 2-5 caracteres total.
# Aceita dígitos depois do primeiro char (B2B, V2, K8S, I18N, S3). IDs
# puramente numéricos (404, 200) ficam fora por começar com dígito.
# Limite de 5 pra evitar palavras em CAPS-LOCK acidentais.
_RE_SIGLA = re.compile(r"\b([A-Z][A-Z0-9]{1,4})\b")

# Padrão "X (sigla Y)" — ex: "Especificação de Requisitos de Software (ERS)".
# Captura palavras 2-6 em Title Case OU maiúsculas antes de `(SIGLA)`.
_RE_DEF_PAREN = re.compile(
    r"([A-ZÁÂÃÀÉÊÍÓÔÕÚÇ][\wÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç]+(?:\s+[A-ZÁÂÃÀÉÊÍÓÔÕÚÇ]?[\wÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç]+){0,5})\s+\(([A-Z]{2,8})\)"
)

# Padrão "SIGLA: definição" OR "SIGLA — definição" (em-dash ou hífen).
_RE_DEF_INLINE = re.compile(
    r"\b([A-Z]{2,5})\s*[:—–-]\s+([A-Za-zÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç][^\n.]{5,150})"
)

# Padrão "X é Y" / "X significa Y". Captura X que comece com letra
# maiúscula (evita sentenças genéricas começando com pronomes).
_RE_DEF_E = re.compile(
    r"\b([A-ZÁÂÃÀÉÊÍÓÔÕÚÇ][\wÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç]{2,30}(?:\s+[A-ZÁÂÃÀÉÊÍÓÔÕÚÇ]?[\wÁÂÃÀÉÊÍÓÔÕÚÇáâãàéêíóôõúç]+){0,2})\s+(?:é|significa|corresponde a)\s+([^\n.]{5,200})"
)


@dataclass
class ExtractionResult:
    """Resultado agregado de uma rodada de extração."""
    project_id: UUID
    scanned_sources: int  # quantas fontes de texto foram varridas
    candidates_found: int  # termos únicos candidatos encontrados
    inserted: int          # termos que realmente foram criados no DB
    skipped_existing: int  # já existiam (aprovados/rejeitados/candidatos anteriores)

    def as_dict(self) -> dict:
        return {
            "project_id": str(self.project_id),
            "scanned_sources": self.scanned_sources,
            "candidates_found": self.candidates_found,
            "inserted": self.inserted,
            "skipped_existing": self.skipped_existing,
        }


# ============================================================================
# Coleta de corpus (texto já persistido no DB — sem I/O de arquivo)
# ============================================================================

async def _collect_corpus(db: AsyncSession, project_id: UUID) -> list[tuple[str, str, str]]:
    """Retorna lista de (text, source, source_reference).

    Fontes canônicas (em ordem de prioridade):
    - ModuleCandidate.description
    - ArguiderAnalysis.document_classification + gaps + show_stoppers +
      poor_definitions + improvement_suggestions (JSON com descrições)
    - GatekeeperItem.item_data (JSON) + resolution_note
    - OCG.ocg_data → PROJECT_PROFILE.description + business_description
    """
    corpus: list[tuple[str, str, str]] = []

    # ModuleCandidate descriptions
    mods = (await db.execute(
        select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
    )).scalars().all()
    for m in mods:
        if m.description:
            corpus.append((m.description, SOURCE_MODULE_DESCRIPTION, f"Módulo: {m.name}"))

    # ArguiderAnalysis — concatena todos os campos JSON relevantes
    analyses = (await db.execute(
        select(ArguiderAnalysis).where(ArguiderAnalysis.project_id == project_id)
    )).scalars().all()
    for a in analyses:
        # Cada campo é string JSON; flatten pra texto pesquisável.
        for field_name in (
            "document_classification",
            "gaps",
            "show_stoppers",
            "poor_definitions",
            "improvement_suggestions",
        ):
            raw = getattr(a, field_name, None)
            if not raw:
                continue
            flat = _flatten_json_for_text(raw)
            if flat:
                corpus.append((flat, SOURCE_ARGUIDER_RESPONSE, f"Análise ({field_name})"))

    # GatekeeperItem — item_data + resolution_note
    items = (await db.execute(
        select(GatekeeperItem).where(GatekeeperItem.project_id == project_id)
    )).scalars().all()
    for it in items:
        if it.item_data:
            flat = _flatten_json_for_text(it.item_data)
            if flat:
                corpus.append((flat, SOURCE_INGESTED_DOC, f"Gatekeeper {it.item_type} {it.item_id_in_analysis}"))
        if it.resolution_note:
            corpus.append((it.resolution_note, SOURCE_ARGUIDER_RESPONSE, f"Resposta do GP em {it.item_id_in_analysis}"))

    # OCG.PROJECT_PROFILE
    ocg = (await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(desc(OCG.version))
        .limit(1)
    )).scalar_one_or_none()
    if ocg and ocg.ocg_data:
        try:
            data = json.loads(ocg.ocg_data)
        except (TypeError, ValueError):
            data = {}
        profile = data.get("PROJECT_PROFILE") or {}
        for key in ("description", "business_description", "problem_statement"):
            val = profile.get(key)
            if isinstance(val, str) and val.strip():
                corpus.append((val, SOURCE_OCG_PROFILE, f"OCG.PROJECT_PROFILE.{key}"))

    return corpus


def _flatten_json_for_text(raw) -> str:
    """Transforma JSON string/dict/list em texto plano pesquisável.

    Extrai só campos descritivos relevantes (`description`, `title`,
    `text`, `content`, `name`) — ignora IDs, timestamps e campos
    estruturais.
    """
    if not raw:
        return ""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return raw if isinstance(raw, str) else ""

    parts: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("description", "title", "text", "content", "name", "label", "message", "detail"):
                    if isinstance(v, str):
                        parts.append(v)
                elif isinstance(v, (dict, list)):
                    walk(v)
                elif isinstance(v, str) and len(v) > 20:
                    # Campos longos que não se encaixam acima — inclui assim mesmo.
                    parts.append(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return "\n".join(parts)


# ============================================================================
# Heurísticas de extração
# ============================================================================

@dataclass
class _Candidate:
    term: str
    definition: str
    source: str
    source_reference: str

    def key(self) -> str:
        """Chave de deduplicação (case-insensitive)."""
        return self.term.strip().lower()


def _extract_candidates_from_text(
    text: str,
    source: str,
    source_reference: str,
) -> Iterable[_Candidate]:
    """Aplica as 3 heurísticas sobre um bloco de texto e emite candidatos."""
    if not text or not isinstance(text, str):
        return []

    results: dict[str, _Candidate] = {}

    # 1. Padrão "Expansão (SIGLA)"
    for match in _RE_DEF_PAREN.finditer(text):
        expansion = match.group(1).strip()
        sigla = match.group(2).strip()
        if sigla in _SIGLA_STOPWORDS:
            continue
        cand = _Candidate(
            term=sigla,
            definition=expansion,
            source=source,
            source_reference=source_reference,
        )
        # Sobrescreve candidato anterior sem definição se esta tiver.
        if cand.key() not in results or not results[cand.key()].definition:
            results[cand.key()] = cand

    # 2. Padrão "SIGLA: definição" / "SIGLA — definição"
    for match in _RE_DEF_INLINE.finditer(text):
        sigla = match.group(1).strip()
        definition = match.group(2).strip()
        if sigla in _SIGLA_STOPWORDS:
            continue
        cand = _Candidate(
            term=sigla,
            definition=definition[:200].rstrip(),
            source=source,
            source_reference=source_reference,
        )
        if cand.key() not in results or not results[cand.key()].definition:
            results[cand.key()] = cand

    # 3. Padrão "X é Y" / "X significa Y"
    for match in _RE_DEF_E.finditer(text):
        term = match.group(1).strip()
        definition = match.group(2).strip()
        # Descartar termos começando com palavras comuns de frase
        first_word = term.split()[0].lower() if term else ""
        if first_word in {"o", "a", "os", "as", "um", "uma", "este", "esta", "esse", "essa", "aquele", "aquela"}:
            continue
        cand = _Candidate(
            term=term,
            definition=definition[:200].rstrip(),
            source=source,
            source_reference=source_reference,
        )
        if cand.key() not in results or not results[cand.key()].definition:
            results[cand.key()] = cand

    # 4. Siglas soltas (sem definição explícita). Entra como candidato,
    #    GP define manualmente depois. Só processa se ainda não foi capturada
    #    por padrões 1/2 (que já trariam definição).
    for match in _RE_SIGLA.finditer(text):
        sigla = match.group(1)
        if sigla in _SIGLA_STOPWORDS:
            continue
        key = sigla.lower()
        if key in results:
            continue
        results[key] = _Candidate(
            term=sigla,
            definition="",
            source=source,
            source_reference=source_reference,
        )

    return results.values()


# ============================================================================
# API pública
# ============================================================================

async def extract_glossary_candidates(
    db: AsyncSession,
    project_id: UUID,
    actor_id: Optional[UUID] = None,
) -> ExtractionResult:
    """Varre o corpus do projeto e insere candidatos novos no glossário.

    Idempotente: termos já existentes (em qualquer status) são pulados
    graças ao UNIQUE (project_id, LOWER(term)). `ON CONFLICT DO NOTHING`
    garante que chamadas repetidas não levantam nem sobrescrevem.

    Retorna `ExtractionResult` com estatísticas para o caller exibir no UI.
    """
    corpus = await _collect_corpus(db, project_id)

    # Dedup global dentro desta execução.
    deduped: dict[str, _Candidate] = {}
    for text, source, ref in corpus:
        for cand in _extract_candidates_from_text(text, source, ref):
            key = cand.key()
            if key not in deduped or (cand.definition and not deduped[key].definition):
                deduped[key] = cand

    inserted_count = 0
    skipped_existing = 0

    for cand in deduped.values():
        # Tenta inserir; se já existe (mesma key por UNIQUE), retorna 0 rows.
        stmt = pg_insert(ProjectGlossaryTerm).values(
            project_id=project_id,
            term=cand.term,
            definition=cand.definition,
            source=cand.source,
            source_reference=cand.source_reference,
            status=STATUS_CANDIDATE,
            created_by=actor_id,
        ).on_conflict_do_nothing(
            index_elements=[ProjectGlossaryTerm.project_id, func.lower(ProjectGlossaryTerm.term)]
        )
        result = await db.execute(stmt)
        # rowcount==0 significa que já existia; ==1 que foi inserido.
        if result.rowcount and result.rowcount > 0:
            inserted_count += 1
        else:
            skipped_existing += 1

    await db.commit()

    result = ExtractionResult(
        project_id=project_id,
        scanned_sources=len(corpus),
        candidates_found=len(deduped),
        inserted=inserted_count,
        skipped_existing=skipped_existing,
    )

    logger.info(
        "glossary.extraction_complete",
        project_id=str(project_id),
        scanned=result.scanned_sources,
        candidates=result.candidates_found,
        inserted=result.inserted,
        skipped=result.skipped_existing,
    )

    return result


async def list_terms(
    db: AsyncSession,
    project_id: UUID,
    status_filter: Optional[str] = None,
) -> list[ProjectGlossaryTerm]:
    """Lista termos do projeto. `status_filter` opcional
    ('candidate', 'approved', 'rejected')."""
    query = select(ProjectGlossaryTerm).where(
        ProjectGlossaryTerm.project_id == project_id
    )
    if status_filter:
        if status_filter not in _ALLOWED_STATUSES:
            raise ValueError(f"status inválido: {status_filter!r}")
        query = query.where(ProjectGlossaryTerm.status == status_filter)
    query = query.order_by(ProjectGlossaryTerm.term.asc())
    return list((await db.execute(query)).scalars().all())


async def list_approved_for_ers(
    db: AsyncSession,
    project_id: UUID,
) -> list[ProjectGlossaryTerm]:
    """Atalho canônico: apenas termos aprovados, ordem alfabética.

    Usado por `ers_doc_generator_service` para popular a seção 1.3 do ERS.
    """
    return await list_terms(db, project_id, status_filter=STATUS_APPROVED)


async def approve_term(
    db: AsyncSession,
    project_id: UUID,
    term_id: UUID,
    actor_id: UUID,
) -> ProjectGlossaryTerm:
    term = await _get_term_or_raise(db, project_id, term_id)
    term.status = STATUS_APPROVED
    term.approved_by = actor_id
    term.approved_at = datetime.now(timezone.utc)
    # Se estava rejeitado, limpa os campos de rejeição.
    term.rejected_by = None
    term.rejected_at = None
    await db.commit()
    await db.refresh(term)
    logger.info("glossary.term_approved", term_id=str(term_id), actor=str(actor_id))
    return term


async def reject_term(
    db: AsyncSession,
    project_id: UUID,
    term_id: UUID,
    actor_id: UUID,
) -> ProjectGlossaryTerm:
    term = await _get_term_or_raise(db, project_id, term_id)
    term.status = STATUS_REJECTED
    term.rejected_by = actor_id
    term.rejected_at = datetime.now(timezone.utc)
    term.approved_by = None
    term.approved_at = None
    await db.commit()
    await db.refresh(term)
    logger.info("glossary.term_rejected", term_id=str(term_id), actor=str(actor_id))
    return term


async def update_term_definition(
    db: AsyncSession,
    project_id: UUID,
    term_id: UUID,
    definition: str,
    actor_id: UUID,
) -> ProjectGlossaryTerm:
    """GP edita a definição do termo. Não muda status."""
    term = await _get_term_or_raise(db, project_id, term_id)
    term.definition = (definition or "").strip()[:2000]
    await db.commit()
    await db.refresh(term)
    logger.info("glossary.term_definition_updated", term_id=str(term_id), actor=str(actor_id))
    return term


async def create_manual_term(
    db: AsyncSession,
    project_id: UUID,
    term: str,
    definition: str,
    actor_id: UUID,
) -> ProjectGlossaryTerm:
    """Cria termo manualmente — default status `approved` (GP decidiu cadastrar)."""
    term = (term or "").strip()
    if not term:
        raise ValueError("term obrigatório")
    if len(term) > 200:
        raise ValueError("term limite de 200 caracteres")
    now = datetime.now(timezone.utc)

    stmt = pg_insert(ProjectGlossaryTerm).values(
        project_id=project_id,
        term=term,
        definition=(definition or "").strip()[:2000],
        source=SOURCE_MANUAL,
        status=STATUS_APPROVED,
        created_by=actor_id,
        approved_by=actor_id,
        approved_at=now,
    ).on_conflict_do_update(
        index_elements=[ProjectGlossaryTerm.project_id, func.lower(ProjectGlossaryTerm.term)],
        set_={
            "definition": (definition or "").strip()[:2000],
            "status": STATUS_APPROVED,
            "approved_by": actor_id,
            "approved_at": now,
            "rejected_by": None,
            "rejected_at": None,
            "updated_at": now,
        },
    ).returning(ProjectGlossaryTerm.id)

    result = await db.execute(stmt)
    new_id = result.scalar_one()
    await db.commit()

    fresh = (await db.execute(
        select(ProjectGlossaryTerm).where(ProjectGlossaryTerm.id == new_id)
    )).scalar_one()
    logger.info("glossary.manual_term_created", project_id=str(project_id), term=term)
    return fresh


async def _get_term_or_raise(db: AsyncSession, project_id: UUID, term_id: UUID) -> ProjectGlossaryTerm:
    term = (await db.execute(
        select(ProjectGlossaryTerm).where(
            (ProjectGlossaryTerm.id == term_id) &
            (ProjectGlossaryTerm.project_id == project_id)
        )
    )).scalar_one_or_none()
    if term is None:
        raise ValueError(f"Termo {term_id} não encontrado")
    return term
