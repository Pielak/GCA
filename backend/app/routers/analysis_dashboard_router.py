"""
Analysis Dashboard Router — Visualização consolidada de análises de personas

Endpoints para:
- Listar todas as 7 análises de um documento
- Comparar OCG Individual vs OCG Global
- Histórico de refinements
- Statistiques e métricas
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional, List, Dict, Any
import structlog
import json

from app.db.database import get_db
from app.models.base import (
    OCGIndividual,
    OCGIndividualRefined,
    PersonaFollowUpQuestion,
    IngestedDocument,
)
from app.middleware.auth import get_current_user_from_token
from pydantic import BaseModel

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["analysis-dashboard"])


class PersonaAnalysisResponse(BaseModel):
    """Análise individual de uma persona."""
    persona_id: str
    persona_name: str
    status: str
    parecer: Dict[str, Any]
    ai_provider: Optional[str]
    ai_model: Optional[str]
    created_at: str
    completed_at: Optional[str]
    follow_up_count: int
    refined_iteration: Optional[int]


class AnalysisDashboardResponse(BaseModel):
    """Dashboard consolidado com todas as análises."""
    document_id: str
    document_name: str
    total_personas: int
    analyses: List[PersonaAnalysisResponse]
    ocg_global: Optional[Dict[str, Any]]
    statistics: Dict[str, Any]


@router.get("/projects/{project_id}/ingestion/{document_id}/analysis-dashboard")
async def get_analysis_dashboard(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna dashboard consolidado com todas as análises de personas.

    Inclui:
    - 7 OCG Individual
    - OCG Global (se consolidado)
    - Estatísticas por persona
    - Status de follow-up questions
    """
    # 1. Buscar documento
    document = await db.get(IngestedDocument, document_id)
    if not document or document.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # 2. Buscar todas as análises (7 personas)
    ocg_individuals = await db.scalars(
        select(OCGIndividual).where(
            (OCGIndividual.project_id == project_id) &
            (OCGIndividual.document_id == document_id)
        )
    )
    ocg_list = ocg_individuals.all()

    if not ocg_list:
        raise HTTPException(status_code=404, detail="Nenhuma análise encontrada")

    # 3. Montar response com detalhes
    analyses = []
    for ocg in ocg_list:
        # Buscar follow-up questions
        follow_up_count = len(
            await db.scalars(
                select(PersonaFollowUpQuestion).where(
                    PersonaFollowUpQuestion.ocg_individual_id == ocg.id
                )
            )
        ) or 0

        # Buscar refinement mais recente
        refined = await db.scalar(
            select(OCGIndividualRefined)
            .where(OCGIndividualRefined.ocg_individual_id == ocg.id)
            .order_by(OCGIndividualRefined.refinement_iteration.desc())
        )

        analysis = PersonaAnalysisResponse(
            persona_id=str(ocg.persona_id),
            persona_name=ocg.persona_name,
            status=ocg.status,
            parecer=ocg.parecer or {},
            ai_provider=ocg.ai_provider,
            ai_model=ocg.ai_model,
            created_at=ocg.created_at.isoformat() if ocg.created_at else "",
            completed_at=ocg.completed_at.isoformat() if ocg.completed_at else None,
            follow_up_count=follow_up_count,
            refined_iteration=refined.refinement_iteration if refined else None,
        )
        analyses.append(analysis)

    # 4. Calcular estatísticas
    criticalities = [
        a.parecer.get("criticidade", "MEDIA") for a in analyses if a.parecer
    ]
    statistics = {
        "total_analyses": len(analyses),
        "completed_count": sum(1 for a in analyses if a.status == "completed"),
        "pending_count": sum(1 for a in analyses if a.status == "pending"),
        "with_follow_up": sum(1 for a in analyses if a.follow_up_count > 0),
        "with_refinement": sum(1 for a in analyses if a.refined_iteration),
        "criticality_distribution": {
            "BAIXA": criticalities.count("BAIXA"),
            "MEDIA": criticalities.count("MEDIA"),
            "ALTA": criticalities.count("ALTA"),
        },
    }

    # 5. Tentar buscar OCG Global (se consolidado)
    # Será armazenado em algum lugar (por enquanto, retornar None)
    ocg_global = None

    return AnalysisDashboardResponse(
        document_id=str(document_id),
        document_name=document.original_filename,
        total_personas=len(analyses),
        analyses=analyses,
        ocg_global=ocg_global,
        statistics=statistics,
    )


class ComparisonResponse(BaseModel):
    """Comparação entre duas análises."""
    persona_a: str
    persona_b: str
    fields_matching: List[str]
    fields_diverging: Dict[str, Dict[str, Any]]
    similarity_score: float  # 0-1


@router.get(
    "/projects/{project_id}/ingestion/{document_id}/compare-analyses",
    response_model=ComparisonResponse,
)
async def compare_analyses(
    project_id: UUID,
    document_id: UUID,
    persona_a_id: str,
    persona_b_id: str,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Compara duas análises de personas.

    Retorna campos em comum e divergentes.
    """
    # Buscar análises
    ocg_a = await db.get(OCGIndividual, UUID(persona_a_id))
    ocg_b = await db.get(OCGIndividual, UUID(persona_b_id))

    if not ocg_a or not ocg_b:
        raise HTTPException(status_code=404, detail="Análises não encontradas")

    parecer_a = ocg_a.parecer or {}
    parecer_b = ocg_b.parecer or {}

    # Encontrar campos em comum
    fields_matching = []
    fields_diverging = {}

    all_keys = set(parecer_a.keys()) | set(parecer_b.keys())

    for key in all_keys:
        val_a = parecer_a.get(key)
        val_b = parecer_b.get(key)

        if val_a == val_b:
            fields_matching.append(key)
        else:
            fields_diverging[key] = {
                ocg_a.persona_name: val_a,
                ocg_b.persona_name: val_b,
            }

    # Calcular similaridade
    matching_count = len(fields_matching)
    total_count = len(all_keys) if all_keys else 1
    similarity = matching_count / total_count

    return ComparisonResponse(
        persona_a=ocg_a.persona_name,
        persona_b=ocg_b.persona_name,
        fields_matching=fields_matching,
        fields_diverging=fields_diverging,
        similarity_score=similarity,
    )


class RefinementHistoryResponse(BaseModel):
    """Histórico de refinements de uma análise."""
    ocg_individual_id: str
    persona_name: str
    original_parecer: Dict[str, Any]
    refinements: List[Dict[str, Any]]
    total_iterations: int


@router.get(
    "/projects/{project_id}/ingestion/{document_id}/ocg/{ocg_id}/refinement-history"
)
async def get_refinement_history(
    project_id: UUID,
    document_id: UUID,
    ocg_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna histórico de refinements de uma análise.

    Mostra evolução da análise através de múltiplas iterações.
    """
    # Buscar OCG original
    ocg = await db.get(OCGIndividual, ocg_id)
    if not ocg or ocg.document_id != document_id or ocg.project_id != project_id:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Buscar refinements
    refined_list = await db.scalars(
        select(OCGIndividualRefined)
        .where(OCGIndividualRefined.ocg_individual_id == ocg_id)
        .order_by(OCGIndividualRefined.refinement_iteration.asc())
    )
    refinements = refined_list.all()

    refinement_data = [
        {
            "iteration": r.refinement_iteration,
            "parecer_refined": r.parecer_refined,
            "changed_fields": r.changed_fields or [],
            "change_summary": r.change_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in refinements
    ]

    return RefinementHistoryResponse(
        ocg_individual_id=str(ocg_id),
        persona_name=ocg.persona_name,
        original_parecer=ocg.parecer or {},
        refinements=refinement_data,
        total_iterations=len(refinements),
    )


class SummaryAnalysisResponse(BaseModel):
    """Resumo consolidado de todas as análises."""
    document_id: str
    document_name: str
    total_personas: int
    all_criticalities: List[str]
    common_recommendations: List[str]
    major_risks: List[str]
    consensus_fields: List[str]
    conflicting_fields: List[str]
    analysis_readiness: str  # raw, refined, consolidated


@router.get(
    "/projects/{project_id}/ingestion/{document_id}/analysis-summary"
)
async def get_analysis_summary(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna resumo consolidado das análises.

    Extrai insights comuns e divergências principais.
    """
    # Buscar documento
    document = await db.get(IngestedDocument, document_id)
    if not document or document.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Buscar todas as análises
    ocg_individuals = await db.scalars(
        select(OCGIndividual).where(
            (OCGIndividual.project_id == project_id) &
            (OCGIndividual.document_id == document_id)
        )
    )
    ocg_list = ocg_individuals.all()

    if not ocg_list:
        raise HTTPException(status_code=404, detail="Nenhuma análise encontrada")

    # Extrair dados consolidados
    all_criticalities = []
    all_recommendations = []
    all_risks = []
    all_pareceres = []

    for ocg in ocg_list:
        parecer = ocg.parecer or {}
        all_pareceres.append(parecer)

        if "criticidade" in parecer:
            all_criticalities.append(parecer["criticidade"])

        if "recomendacoes" in parecer:
            recs = parecer["recomendacoes"]
            if isinstance(recs, list):
                all_recommendations.extend(recs)

        if "riscos" in parecer:
            risks = parecer["riscos"]
            if isinstance(risks, list):
                all_risks.extend(risks)

    # Contar frequências
    from collections import Counter

    rec_freq = Counter(all_recommendations)
    risk_freq = Counter(all_risks)

    # Top recomendações e riscos (apareceram em 2+ personas)
    common_recs = [r for r, c in rec_freq.items() if c >= 2][:5]
    major_risks = [r for r, c in risk_freq.items() if c >= 2][:5]

    # Detectar consensus vs conflito
    consensus_fields = []
    conflicting_fields = []

    all_keys = set()
    for parecer in all_pareceres:
        all_keys.update(parecer.keys())

    for key in all_keys:
        values = [p.get(key) for p in all_pareceres if key in p]
        if len(set(map(str, values))) == 1:  # Todos os mesmos
            consensus_fields.append(key)
        elif len(set(map(str, values))) > 1:
            conflicting_fields.append(key)

    # Determinar readiness
    readiness = "raw"
    refined_count = sum(
        1
        for ocg in ocg_list
        if len(
            await db.scalars(
                select(OCGIndividualRefined).where(
                    OCGIndividualRefined.ocg_individual_id == ocg.id
                )
            )
        )
        > 0
    )
    if refined_count == len(ocg_list):
        readiness = "refined"

    return SummaryAnalysisResponse(
        document_id=str(document_id),
        document_name=document.original_filename,
        total_personas=len(ocg_list),
        all_criticalities=all_criticalities,
        common_recommendations=common_recs,
        major_risks=major_risks,
        consensus_fields=consensus_fields,
        conflicting_fields=conflicting_fields,
        analysis_readiness=readiness,
    )
