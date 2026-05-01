"""Endpoints para execução de Personas no Gatekeeper (Phase B)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import structlog

from app.db.database import get_db
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.models.human_answer import HumanAnswer
from app.services.parallel_evaluator import ParallelEvaluator
from app.services.llm_client import AnthropicLLMClient
from app.schemas.gatekeeper import (
    Passada1Request,
    Passada1Response,
    Passada2Request,
    Passada2Response,
    PersonasBoardResponse,
    PersonaResponseDetail,
    PersonaScoreResponse,
)
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/gatekeeper", tags=["gatekeeper"])


@router.post("/passada-1", response_model=Passada1Response)
async def run_passada_1(
    request: Passada1Request,
    db: AsyncSession = Depends(get_db),
) -> Passada1Response:
    """Executa Passada 1 (análise tentativa com perguntas para validador humano)."""

    # Fetch route_map and auditor_output
    result = await db.execute(
        select(DocumentRouteMap).where(DocumentRouteMap.id == request.route_map_id)
    )
    route_map = result.scalars().first()

    if not route_map:
        raise HTTPException(status_code=404, detail="DocumentRouteMap não encontrado")

    result = await db.execute(
        select(AuditorOutput).where(AuditorOutput.route_map_id == request.route_map_id)
    )
    auditor_output = result.scalars().first()

    if not auditor_output:
        raise HTTPException(status_code=404, detail="AuditorOutput não encontrado")

    # Run Passada 1 with all 7 personas in parallel
    llm = AnthropicLLMClient()
    evaluator = ParallelEvaluator(llm, db)

    persona_responses = await evaluator.run_passada_1(route_map, auditor_output)

    # Build board response
    personas_board = _build_personas_board(route_map.id, 1, persona_responses)

    # Collect all questions from all personas
    all_questions = []
    for response in persona_responses.values():
        if response.questions:
            all_questions.extend(response.questions)

    return Passada1Response(
        route_map_id=route_map.id,
        personas_board=personas_board,
        total_questions=len(all_questions),
        questions_to_answer=[q.__dict__ if hasattr(q, '__dict__') else dict(q) for q in all_questions],
    )


@router.get("/personas-board/{route_map_id}", response_model=PersonasBoardResponse)
async def get_personas_board(
    route_map_id: UUID,
    passada: int = 1,
    db: AsyncSession = Depends(get_db),
) -> PersonasBoardResponse:
    """Obtém o board visual com status de todas as personas para uma rota."""

    from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse

    # Fetch all responses for this route_map
    result = await db.execute(
        select(GatekeeperPersonaResponse).where(
            (GatekeeperPersonaResponse.route_map_id == route_map_id) &
            (GatekeeperPersonaResponse.passada == passada)
        )
    )
    responses = result.scalars().all()

    if not responses:
        raise HTTPException(status_code=404, detail="Nenhuma resposta de persona encontrada")

    personas_dict = {}
    approved_count = 0

    for response in responses:
        personas_dict[response.persona_tag] = PersonaResponseDetail(
            persona_tag=response.persona_tag,
            passada=response.passada,
            scores=PersonaScoreResponse(**response.scores),
            approved=response.approved,
            tentative=response.tentative,
            issues=response.issues,
            questions=response.questions,
            justification=response.justification,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            elapsed_ms=response.elapsed_ms,
        )
        if response.approved:
            approved_count += 1

    return PersonasBoardResponse(
        route_map_id=route_map_id,
        passada=passada,
        total_personas=len(personas_dict),
        approved_count=approved_count,
        personas=personas_dict,
    )


@router.post("/human-answers")
async def store_human_answers(
    request: Passada2Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Armazena respostas humanas às perguntas das personas."""

    # Check route_map exists
    result = await db.execute(
        select(DocumentRouteMap).where(DocumentRouteMap.id == request.route_map_id)
    )
    route_map = result.scalars().first()

    if not route_map:
        raise HTTPException(status_code=404, detail="DocumentRouteMap não encontrado")

    # Store all human answers
    for answer_input in request.human_answers:
        answer = HumanAnswer(
            route_map_id=request.route_map_id,
            persona_tag=answer_input.persona_tag,
            question_id=answer_input.question_id,
            answer_text=answer_input.answer_text,
        )
        db.add(answer)

    await db.commit()

    return {
        "route_map_id": str(request.route_map_id),
        "answers_stored": len(request.human_answers),
    }


@router.post("/passada-2", response_model=Passada2Response)
async def run_passada_2(
    request: Passada2Request,
    db: AsyncSession = Depends(get_db),
) -> Passada2Response:
    """Executa Passada 2 (análise final com respostas humanas integradas)."""

    # Fetch route_map and auditor_output
    result = await db.execute(
        select(DocumentRouteMap).where(DocumentRouteMap.id == request.route_map_id)
    )
    route_map = result.scalars().first()

    if not route_map:
        raise HTTPException(status_code=404, detail="DocumentRouteMap não encontrado")

    result = await db.execute(
        select(AuditorOutput).where(AuditorOutput.route_map_id == request.route_map_id)
    )
    auditor_output = result.scalars().first()

    if not auditor_output:
        raise HTTPException(status_code=404, detail="AuditorOutput não encontrado")

    # Build human_answers dict from request and stored answers
    human_answers = {}

    # Add request answers
    for answer_input in request.human_answers:
        key = f"{answer_input.persona_tag}:{answer_input.question_id}"
        human_answers[key] = answer_input.answer_text

    # Run Passada 2 with all 7 personas in parallel
    llm = AnthropicLLMClient()
    evaluator = ParallelEvaluator(llm, db)

    persona_responses = await evaluator.run_passada_2(route_map, auditor_output, human_answers)

    # Build board response
    personas_board = _build_personas_board(route_map.id, 2, persona_responses)

    # Check if all personas approved
    all_approved = all(r.approved for r in persona_responses.values())

    # Collect blocking issues
    blocking_issues = []
    for response in persona_responses.values():
        if response.issues:
            for issue in response.issues:
                if isinstance(issue, dict) and issue.get("severity") == "blocker":
                    blocking_issues.append(issue)

    return Passada2Response(
        route_map_id=route_map.id,
        personas_board=personas_board,
        all_approved=all_approved,
        blocking_issues=blocking_issues,
    )


def _build_personas_board(
    route_map_id: UUID,
    passada: int,
    persona_responses: dict,
) -> PersonasBoardResponse:
    """Helper para construir PersonasBoardResponse a partir das respostas das personas."""

    personas_dict = {}
    approved_count = 0

    for persona_tag, response in persona_responses.items():
        personas_dict[persona_tag] = PersonaResponseDetail(
            persona_tag=response.persona_tag,
            passada=response.passada,
            scores=PersonaScoreResponse(**response.scores.__dict__),
            approved=response.approved,
            tentative=response.tentative,
            issues=[i.__dict__ if hasattr(i, '__dict__') else dict(i) for i in response.issues],
            questions=[q.__dict__ if hasattr(q, '__dict__') else dict(q) for q in response.questions],
            justification=response.justification,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            elapsed_ms=response.elapsed_ms,
        )
        if response.approved:
            approved_count += 1

    return PersonasBoardResponse(
        route_map_id=route_map_id,
        passada=passada,
        total_personas=len(personas_dict),
        approved_count=approved_count,
        personas=personas_dict,
    )
