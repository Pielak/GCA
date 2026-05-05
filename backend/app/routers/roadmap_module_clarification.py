"""B5 (Decisão GP 3 — 2026-05-04): UX construtivo no Roadmap.

Quando GP clica em item do roadmap mas o módulo correspondente ainda
não existe como ModuleCandidate concreto, em vez de 404 cego mostrar:

1. Instruções de configuração (texto explicativo)
2. Persona(s) sugerida(s) pela heurística do nome/categoria
3. Botão "Gerar pergunta em Questões em Aberto" → POST aqui →
   cria PersonaFollowUpQuestion `pending` pra persona apropriada

Heurística determinística (alinha Decisão 8): substring match
case-insensitive em nome do item. NÃO LLM — comportamento previsível.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action

logger = logging.getLogger(__name__)
router = APIRouter()


# Mapping nome → personas sugeridas. Substring match case-insensitive.
# Ordem importa: primeiro match vence quando token é ambíguo.
_PERSONA_KEYWORDS: list[tuple[tuple[str, ...], list[str]]] = [
    # Testes
    (("teste", "test", "cobertura", "cover", "bdd", "regress", "unitario", "unit_"), ["QA"]),
    (("integracao", "integration", "e2e"), ["DEV", "QA"]),
    (("performance", "perform", "load", "carga", "scale", "throughput"), ["ARQ", "DEV"]),
    # Stack/arquitetura
    (("stack", "framework", "linguagem", "deploy", "infra", "kubernetes", "docker"), ["ARQ", "DEV", "DBA"]),
    (("arquitetura", "diagram", "padrao", "pattern"), ["ARQ"]),
    # Banco
    (("dba", "banco", "database", "sql", "schema", "migration", "indice"), ["DBA"]),
    # Segurança
    (("seguranca", "security", "owasp", "auth", "criptografia", "asvs"), ["SEG"]),
    # Compliance
    (("compliance", "conformidade", "iso", "audit", "27001"), ["CONF"]),
    # LGPD
    (("lgpd", "privac", "dado_pessoal", "dpo", "anpd", "titular"), ["LGPD"]),
    # Negócio
    (("negocio", "business", "babok", "requisito", "stakeholder"), ["NEG"]),
    # UX
    (("ux", "acessibilidade", "wcag", "emag", "jornada", "usabilidade"), ["UX"]),
    # UI
    (("ui_", "design_system", "componente", "wireframe", "responsiv"), ["UI"]),
    # API/Dev
    (("api", "endpoint", "rest", "graphql", "implement", "dev_", "codigo"), ["DEV"]),
]

_FALLBACK_PERSONAS = ["GP"]


def suggest_personas_for_name(name: str) -> list[str]:
    """Heurística determinística: nome → personas sugeridas.

    Lower-case substring match. Primeira regra que bate ganha.
    Sem match → ["GP"] (Decisão 8: não decidir ambíguo).
    """
    if not name:
        return _FALLBACK_PERSONAS
    n = name.lower()
    for tokens, personas in _PERSONA_KEYWORDS:
        if any(t in n for t in tokens):
            return personas
    return _FALLBACK_PERSONAS


async def suggest_personas_for_module_id(
    db: AsyncSession, module_id: UUID, project_id: UUID,
) -> dict[str, Any]:
    """Inferência completa: tenta achar nome/contexto do módulo,
    sugere personas + monta question_text padrão.
    """
    name_hint = ""
    try:
        from app.models.base import OCG
        ocg_row = (
            await db.execute(
                select(OCG.ocg_data).where(OCG.project_id == project_id)
                .order_by(OCG.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if ocg_row:
            import json as _json
            ocg = _json.loads(ocg_row) if isinstance(ocg_row, str) else ocg_row
            deliverables = ocg.get("DELIVERABLES") or {}
            if isinstance(deliverables, dict):
                for k, v in deliverables.items():
                    if isinstance(v, dict) and str(v.get("id", "")) == str(module_id):
                        name_hint = v.get("name") or k
                        break
    except Exception as exc:  # noqa: BLE001
        logger.warning("clarification.ocg_lookup_failed", extra={"error": str(exc)})

    personas = suggest_personas_for_name(name_hint) if name_hint else _FALLBACK_PERSONAS
    name_label = name_hint or f"módulo {str(module_id)[:8]}"
    return {
        "personas": personas,
        "question_text": (
            f"O item '{name_label}' aparece no roadmap mas ainda não está "
            f"configurado como módulo concreto do projeto. Por favor "
            f"esclareça o escopo: qual é o objetivo, quais são os critérios "
            f"de aceite, e qual stack/abordagem técnica deve ser usada?"
        ),
        "instructions": (
            f"Para configurar este item:\n"
            f"1. Preencher o questionário técnico se ainda não foi feito.\n"
            f"2. Subir documentação relevante na aba Ingestão.\n"
            f"3. Ou usar o botão abaixo pra gerar pergunta direcionada às "
            f"persona(s) sugerida(s) {', '.join(personas)} — elas vão "
            f"perguntar especificamente o que falta saber."
        ),
    }


# ─── Endpoint POST: criar PFQ pendente pra clarification ─────────────────

class ClarificationRequest(BaseModel):
    persona_id: str
    question_text: str
    context: str | None = None


@router.post("/projects/{project_id}/modules/{module_id}/clarification-request")
async def create_clarification_request(
    project_id: UUID,
    module_id: UUID,
    payload: ClarificationRequest,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """B5 — UX construtivo no Roadmap. Gera PersonaFollowUpQuestion
    pendente pra persona apropriada quando módulo não existe ainda.

    Não exige ModuleCandidate real. Cria PFQ com `document_id=NULL`
    e `ocg_individual_id=NULL` (são FKs com ondelete=CASCADE — null
    significa origem não vinculada a doc/individual específico).

    Política erro determinístico (Decisão 8): tag inválida → 422,
    texto vazio → 422, falha de DB → 500 com log estruturado.
    """
    _CANONICAL = {"AUD", "GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI", "SEG", "CONF", "LGPD", "NEG"}
    persona_norm = payload.persona_id.strip().upper()
    if persona_norm not in _CANONICAL:
        raise HTTPException(
            status_code=422,
            detail=f"persona_id inválido. Aceitos: {sorted(_CANONICAL)}",
        )
    qtext = (payload.question_text or "").strip()
    if not qtext:
        raise HTTPException(status_code=422, detail="question_text obrigatório")

    persona_name_map = {
        "AUD": "Auditor", "GP": "Gerente de Projetos", "ARQ": "Arquiteto",
        "DBA": "DBA", "DEV": "Dev Sênior", "QA": "QA",
        "UX": "UX Designer", "UI": "UI Designer",
        "SEG": "Segurança", "CONF": "Conformidade", "LGPD": "Proteção de Dados",
        "NEG": "Analista de Requisitos",
    }
    pfq_id = uuid4()
    try:
        await db.execute(
            _text("""
                INSERT INTO persona_follow_up_questions
                    (id, project_id, document_id, ocg_individual_id,
                     persona_id, persona_name, question_text, context,
                     question_order, status, created_at, updated_at)
                VALUES
                    (:id, :pid, NULL, NULL,
                     :persona_id, :persona_name, :qtext, :ctx,
                     0, 'pending', NOW(), NOW())
            """),
            {
                "id": pfq_id,
                "pid": project_id,
                "persona_id": persona_norm,
                "persona_name": persona_name_map.get(persona_norm, persona_norm),
                "qtext": qtext[:5000],
                "ctx": (payload.context or f"Roadmap clarification — module_id={module_id}")[:500],
            },
        )
        await db.commit()
        logger.info(
            "roadmap.clarification_pfq_created pfq_id=%s persona=%s module=%s",
            pfq_id, persona_norm, module_id,
        )
    except Exception as exc:
        logger.error("roadmap.clarification_failed error=%s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao criar pergunta: {type(exc).__name__}",
        )

    return {
        "pfq_id": str(pfq_id),
        "persona_id": persona_norm,
        "status": "pending",
        "message": (
            f"Pergunta criada para persona {persona_norm}. "
            f"Acompanhe em 'Questões em Aberto'."
        ),
    }
