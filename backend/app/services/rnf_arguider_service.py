"""MVP 23 Fase 23.2 — Arguidor dirigido para Requisitos Não-Funcionais.

Quando o OCG tem `RNF_CONTRACTS` vazio ou parcialmente preenchido, o
Arguidor dispara perguntas canônicas (determinísticas, sem LLM) pra
popular os contratos por categoria. Respostas do GP alimentam o OCG
via merge estrutural.

Fluxo canônico:
  1. `seed_rnf_gaps(project_id)` detecta categorias vazias e registra
     `GatekeeperItem` tipo `gap` com `category=rnf_contract` pra cada uma.
  2. UI do Arguidor/Gatekeeper exibe o form estruturado (cada gap carrega
     schema de entrada canônico).
  3. GP responde — `apply_rnf_answer(project_id, category, payload)`
     valida, merge no OCG, bump de version + audit, e resolve o gap.

Decisão binária canônica #5 do MVP 23: Arguidor só **sugere** quando
faltar; GP pode preencher direto via `apply_rnf_answer` sem passar
pelo Arguidor.

Zero LLM no caminho crítico.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import GatekeeperItem, OCG
from app.services.rnf_contracts import (
    from_ocg_dict,
    validate_contract_dict,
)


logger = structlog.get_logger(__name__)


RnfCategory = Literal["performance", "security", "compliance", "availability"]


# ─── Templates canônicos de pergunta ─────────────────────────────────


@dataclass(frozen=True)
class RnfQuestionTemplate:
    """Pergunta canônica por categoria de RNF.

    Templates determinísticos pra cada categoria. O frontend renderiza
    baseado em `fields` — cada field tem tipo + label + help opcional.
    """
    category: RnfCategory
    title: str
    description: str
    fields: tuple[dict[str, Any], ...]


_PERFORMANCE_TEMPLATE = RnfQuestionTemplate(
    category="performance",
    title="Contratos de performance do projeto",
    description=(
        "Defina orçamentos de performance para o CodeGen respeitar ao gerar "
        "os módulos. Todos os campos são opcionais — preencha apenas o que "
        "faz sentido no contexto."
    ),
    fields=(
        {
            "key": "latency_p95_ms",
            "type": "int_ms",
            "label": "Latência P95 máxima (ms)",
            "help": "Endpoint-padrão deve responder no percentil 95 abaixo deste valor.",
            "example": 200,
        },
        {
            "key": "throughput_rps",
            "type": "int",
            "label": "Throughput esperado (req/s)",
            "help": "Carga sustentada que a infraestrutura precisa suportar.",
            "example": 500,
        },
        {
            "key": "per_operation",
            "type": "list_of_op_budget",
            "label": "Budgets por operação (opcional)",
            "help": "Lista de {op, budget_ms} pra operações críticas específicas.",
            "example": [{"op": "POST /orders", "budget_ms": 150}],
        },
    ),
)


_SECURITY_TEMPLATE = RnfQuestionTemplate(
    category="security",
    title="Contratos de segurança",
    description=(
        "Proteções obrigatórias que o código gerado DEVE incluir. "
        "Validação estática pós-geração verifica presença dos patterns "
        "canônicos (middleware de rate limit, ORM parametrizado, vault "
        "para secrets etc)."
    ),
    fields=(
        {
            "key": "required_cwe_protections",
            "type": "list_cwe",
            "label": "CWEs obrigatórios",
            "help": "Ex: CWE-89 (SQLi), CWE-79 (XSS), CWE-798 (hardcoded credentials).",
            "example": ["CWE-89", "CWE-798"],
            "suggestions": ["CWE-79", "CWE-89", "CWE-200", "CWE-287", "CWE-352", "CWE-798"],
        },
        {
            "key": "rate_limit_rpm_public",
            "type": "int",
            "label": "Rate limit público (req/min)",
            "help": "Aplicado a endpoints não autenticados. Middleware injetado automaticamente.",
            "example": 60,
        },
        {
            "key": "rate_limit_rpm_authenticated",
            "type": "int",
            "label": "Rate limit autenticado (req/min por usuário)",
            "example": 600,
        },
        {
            "key": "sensitive_data_categories",
            "type": "list_str",
            "label": "Categorias de dado sensível",
            "help": "Ex: PII, financial, health, credential. Afeta logging, encryption em repouso, audit.",
            "example": ["PII", "financial"],
            "suggestions": ["PII", "financial", "health", "credential", "location", "biometric"],
        },
    ),
)


_COMPLIANCE_TEMPLATE = RnfQuestionTemplate(
    category="compliance",
    title="Regulações aplicáveis",
    description=(
        "Lista de requisitos regulatórios que aplicam ao projeto. Cada "
        "item tem regulação + requirement_id + modo de enforcement "
        "(runtime / static / both)."
    ),
    fields=(
        {
            "key": "items",
            "type": "list_compliance_item",
            "label": "Itens de compliance",
            "help": "Cada item: {regulation, requirement_id, enforcement}.",
            "example": [
                {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "runtime"},
            ],
            "suggestions_regulation": [
                "LGPD", "GDPR", "SOX", "PCI-DSS", "HIPAA",
                "BACEN", "CVM", "ANS", "SOC2", "ISO-27001",
            ],
        },
    ),
)


_AVAILABILITY_TEMPLATE = RnfQuestionTemplate(
    category="availability",
    title="Contratos de disponibilidade",
    description="SLA de uptime + metas de recuperação (RPO/RTO).",
    fields=(
        {
            "key": "uptime_pct",
            "type": "float",
            "label": "SLA de uptime (%)",
            "example": 99.5,
        },
        {
            "key": "rpo_minutes",
            "type": "int",
            "label": "RPO — janela máxima de perda (minutos)",
            "example": 60,
        },
        {
            "key": "rto_minutes",
            "type": "int",
            "label": "RTO — tempo máximo de recuperação (minutos)",
            "example": 30,
        },
    ),
)


_TEMPLATES: dict[RnfCategory, RnfQuestionTemplate] = {
    "performance": _PERFORMANCE_TEMPLATE,
    "security": _SECURITY_TEMPLATE,
    "compliance": _COMPLIANCE_TEMPLATE,
    "availability": _AVAILABILITY_TEMPLATE,
}


def get_template(category: RnfCategory) -> RnfQuestionTemplate:
    if category not in _TEMPLATES:
        raise ValueError(f"Categoria RNF desconhecida: {category}")
    return _TEMPLATES[category]


def all_templates() -> dict[RnfCategory, RnfQuestionTemplate]:
    return dict(_TEMPLATES)


# ─── Detecção de gaps ─────────────────────────────────────────────────


def detect_missing_categories(ocg_data: dict) -> list[RnfCategory]:
    """Detecta quais categorias de RNF estão vazias no OCG atual.

    Regra canônica: categoria "vazia" = bloco ausente ou sem nenhum campo
    material preenchido. Quando GP já preencheu ao menos 1 campo, a
    categoria NÃO é mais considerada gap (evita spam de perguntas).
    """
    raw = ocg_data.get("RNF_CONTRACTS") if isinstance(ocg_data, dict) else {}
    rnf = from_ocg_dict(raw)

    missing: list[RnfCategory] = []
    if rnf.performance.is_empty:
        missing.append("performance")
    if rnf.security.is_empty:
        missing.append("security")
    if not rnf.compliance:
        missing.append("compliance")
    if rnf.availability.is_empty:
        missing.append("availability")
    return missing


# ─── Seeding de gaps no Gatekeeper ────────────────────────────────────


async def seed_rnf_gaps(
    db: AsyncSession,
    project_id: UUID,
) -> list[GatekeeperItem]:
    """Cria `GatekeeperItem` tipo `gap` pra cada categoria RNF faltante.

    Idempotente: se já existe gap RNF aberto pra categoria, não recria.
    Gap resolvido (status='resolved') **não** reabre — GP removeu conscientemente.

    Retorna lista dos items criados nesta chamada (não inclui preexistentes).
    """
    ocg = await _load_current_ocg(db, project_id)
    if ocg is None:
        logger.info("rnf_arguider.seed.no_ocg", project_id=str(project_id))
        return []

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}

    missing = detect_missing_categories(ocg_data)
    if not missing:
        logger.info("rnf_arguider.seed.no_gaps", project_id=str(project_id))
        return []

    # Verifica gaps RNF já existentes pra evitar duplicação.
    existing_result = await db.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project_id,
            GatekeeperItem.item_type == "gap",
        )
    )
    existing_items = existing_result.scalars().all()
    existing_categories: set[str] = set()
    for item in existing_items:
        try:
            data = json.loads(item.item_data) if item.item_data else {}
        except (TypeError, ValueError):
            continue
        if data.get("category") != "rnf_contract":
            continue
        rnf_cat = data.get("rnf_category")
        if rnf_cat:
            existing_categories.add(rnf_cat)

    # MVP 23 Fase 23.2 — GatekeeperItem exige `arguider_analysis_id` NOT NULL
    # no schema. Quando projeto ainda não tem nenhuma ingestão (Arguidor
    # nunca rodou), skip seed: GP pode responder direto via `apply_rnf_answer`
    # — templates canônicos ficam disponíveis por `all_templates()` mesmo
    # sem gap aberto no Gatekeeper.
    resolved_analysis_id = await _resolve_existing_analysis_id(db, project_id)
    if resolved_analysis_id is None:
        logger.info(
            "rnf_arguider.seed.no_arguider_analysis",
            project_id=str(project_id),
            missing_categories=missing,
        )
        return []

    # item_id_in_analysis é VARCHAR(10) no schema — formato canônico curto.
    _CATEGORY_CODE: dict[str, str] = {
        "performance": "P",
        "security": "S",
        "compliance": "C",
        "availability": "A",
    }

    created: list[GatekeeperItem] = []
    for idx, category in enumerate(missing):
        if category in existing_categories:
            continue
        template = _TEMPLATES[category]
        item_data = {
            "category": "rnf_contract",
            "rnf_category": category,
            "title": template.title,
            "description": template.description,
            "fields": list(template.fields),
            "seeded_by": "rnf_arguider_service",
        }
        code = _CATEGORY_CODE.get(category, "X")
        item = GatekeeperItem(
            project_id=project_id,
            arguider_analysis_id=resolved_analysis_id,
            item_type="gap",
            item_id_in_analysis=f"RNF-{code}-{idx + 1:03d}",  # RNF-P-001 (9 chars)
            item_data=json.dumps(item_data, ensure_ascii=False),
            status="pending",
        )
        db.add(item)
        created.append(item)

    await db.flush()
    logger.info(
        "rnf_arguider.seeded",
        project_id=str(project_id),
        created=len(created),
        categories=missing,
    )
    return created


# ─── Aplicação de resposta ────────────────────────────────────────────


async def apply_rnf_answer(
    db: AsyncSession,
    project_id: UUID,
    category: RnfCategory,
    payload: dict,
    *,
    resolved_by: Optional[UUID] = None,
) -> dict:
    """Aplica resposta do GP ao contrato RNF no OCG.

    Valida payload via `validate_contract_dict` (após wrap na estrutura
    canônica), faz merge no OCG existente, bump de version, e resolve
    o GatekeeperItem correspondente quando existir.

    Retorna:
        {
          "applied": bool,
          "errors": [list of {path, message}],
          "ocg_version_to": int | None,
        }

    Resposta canônica:
      - `applied=True` quando mudou e persistiu
      - `applied=False, errors=[...]` quando payload inválido
      - `applied=False, errors=[]` quando payload idêntico ao atual (noop)
    """
    if category not in _TEMPLATES:
        return {
            "applied": False,
            "errors": [{"path": "$.category", "message": f"categoria inválida: {category}"}],
            "ocg_version_to": None,
        }

    # Monta estrutura canônica pra validar como se fosse RNF_CONTRACTS completo.
    if category == "compliance":
        wrapped = {"compliance": payload.get("items", payload) if isinstance(payload, dict) else []}
    else:
        wrapped = {category: payload}

    errors = validate_contract_dict(wrapped)
    if errors:
        return {
            "applied": False,
            "errors": [{"path": e.path, "message": e.message} for e in errors],
            "ocg_version_to": None,
        }

    ocg = await _load_current_ocg(db, project_id)
    if ocg is None:
        return {
            "applied": False,
            "errors": [{"path": "$", "message": "OCG do projeto não encontrado"}],
            "ocg_version_to": None,
        }

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}

    current_rnf = ocg_data.get("RNF_CONTRACTS")
    if not isinstance(current_rnf, dict):
        current_rnf = {}

    # Merge por categoria.
    if category == "compliance":
        new_items = wrapped["compliance"]
        if current_rnf.get("compliance") == new_items:
            return {"applied": False, "errors": [], "ocg_version_to": ocg.version}
        current_rnf["compliance"] = new_items
    else:
        if current_rnf.get(category) == wrapped[category]:
            return {"applied": False, "errors": [], "ocg_version_to": ocg.version}
        current_rnf[category] = wrapped[category]

    ocg_data["RNF_CONTRACTS"] = current_rnf
    new_version = (ocg.version or 0) + 1
    ocg.ocg_data = json.dumps(ocg_data, ensure_ascii=False)
    ocg.version = new_version
    ocg.updated_at = datetime.now(timezone.utc)
    db.add(ocg)

    # Resolve GatekeeperItem correspondente (se existir).
    await _resolve_rnf_gap(db, project_id, category, resolved_by=resolved_by)

    # Emite audit canônico.
    from app.services.audit_service import AuditEvents, AuditService
    await AuditService(db).log_event(
        event_type=AuditEvents.OCG_UPDATED,
        resource_type="ocg",
        actor_id=resolved_by,
        resource_id=ocg.id,
        details={
            "project_id": str(project_id),
            "rnf_category": category,
            "version_from": new_version - 1,
            "version_to": new_version,
            "source": "rnf_arguider.apply_answer",
        },
    )

    await db.flush()
    logger.info(
        "rnf_arguider.applied",
        project_id=str(project_id),
        category=category,
        version=new_version,
    )
    return {"applied": True, "errors": [], "ocg_version_to": new_version}


# ─── Privates ─────────────────────────────────────────────────────────


async def _load_current_ocg(db: AsyncSession, project_id: UUID) -> Optional[OCG]:
    result = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(OCG.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _resolve_existing_analysis_id(
    db: AsyncSession, project_id: UUID,
) -> Optional[UUID]:
    """Retorna a última `ArguiderAnalysis` do projeto, ou None se não existe.

    GatekeeperItem exige FK NOT NULL; sem ingestão anterior, não dá pra
    registrar gap. Caller faz skip e log canônico.
    """
    from app.models.base import ArguiderAnalysis
    result = await db.execute(
        select(ArguiderAnalysis)
        .where(ArguiderAnalysis.project_id == project_id)
        .order_by(ArguiderAnalysis.created_at.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    return analysis.id if analysis else None


async def _resolve_rnf_gap(
    db: AsyncSession,
    project_id: UUID,
    category: RnfCategory,
    *,
    resolved_by: Optional[UUID],
) -> None:
    """Marca GatekeeperItem RNF da categoria como resolved (best-effort)."""
    result = await db.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project_id,
            GatekeeperItem.item_type == "gap",
            GatekeeperItem.status == "pending",
        )
    )
    for item in result.scalars().all():
        try:
            data = json.loads(item.item_data) if item.item_data else {}
        except (TypeError, ValueError):
            continue
        if data.get("category") != "rnf_contract":
            continue
        if data.get("rnf_category") != category:
            continue
        item.status = "resolved"
        item.resolved_by = resolved_by
        item.resolved_at = datetime.now(timezone.utc)
        item.resolution_note = f"RNF_CONTRACTS.{category} preenchido via Arguidor"
        db.add(item)
