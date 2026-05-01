"""Endpoints para execução de Personas no Gatekeeper (Phase B)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import structlog
from typing import Optional, Literal

from app.db.database import get_db
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.models.human_answer import HumanAnswer
from app.models.base import IngestedDocument
from app.services.parallel_evaluator import ParallelEvaluator
from app.services.ai_key_resolver import AIKeyResolver
from app.services.llm_service import LLMServiceFactory, LLMProvider, BaseLLMClient
from app.services.llm_client import LLMClient, LLMUsage, LLMResponse
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


class LLMClientAdapter(LLMClient):
    """Adapta BaseLLMClient (de llm_service.py) para interface LLMClient esperada pelas personas."""

    def __init__(self, base_client: BaseLLMClient):
        self.base_client = base_client
        self.provider_name = getattr(base_client, 'provider_name', base_client.__class__.__name__.replace('Client', '').lower())
        self.model_name = getattr(base_client, 'model', 'unknown')

    async def complete(
        self,
        system: Optional[str],
        user: str,
        cacheable_system: Optional[str] = None,
        response_format: Optional[Literal["json", "text"]] = None,
        max_output_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Adapts BaseLLMClient.generate() to LLMClient.complete() interface."""
        # Combine system prompts
        full_system = ""
        if cacheable_system:
            full_system += cacheable_system + "\n"
        if system:
            full_system += system

        # Build full prompt
        full_prompt = user
        if full_system:
            full_prompt = full_system + "\n\n" + user

        # Call base client
        content = await self.base_client.generate(
            prompt=full_prompt,
            max_tokens=max_output_tokens,
            temperature=temperature,
        )

        # Return in expected format
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                input_tokens=0,  # Not tracked by base client
                output_tokens=0,  # Not tracked by base client
            ),
            finish_reason="stop",
        )


async def resolve_llm_client_for_route_map(
    db: AsyncSession,
    route_map: DocumentRouteMap,
) -> LLMClient:
    """Resolve LLM client respecting project_settings (Settings > IA).

    Returns an LLMClient adapter wrapping the configured provider,
    or raises HTTPException if not configured.
    """
    # Get project_id via IngestedDocument
    result = await db.execute(
        select(IngestedDocument).where(IngestedDocument.id == route_map.document_id)
    )
    doc = result.scalars().first()

    if not doc:
        raise HTTPException(status_code=404, detail="IngestedDocument não encontrado")

    project_id = doc.project_id

    # Get configured provider chain
    provider_chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)

    if not provider_chain:
        raise HTTPException(
            status_code=400,
            detail="Nenhum provedor de IA configurado. Abra Settings > Provedor IA para configurar.",
        )

    # Try each provider in chain
    for provider_config in provider_chain:
        provider_name = provider_config.get("provider", "").lower()

        try:
            # Get API key for this provider
            api_key = await AIKeyResolver.get_project_key(db, project_id, provider_name)

            if not api_key:
                logger.warning(
                    "llm.provider_skipped_no_key",
                    provider=provider_name,
                    project_id=str(project_id),
                )
                continue

            # Map provider string to LLMProvider enum
            provider_enum = LLMProvider(provider_name.lower())

            # Get model from config, with fallback
            model = provider_config.get("model")

            # Create base client from llm_service.py
            base_client = LLMServiceFactory.create_client(provider_enum, api_key)

            # Update model if provided
            if model and hasattr(base_client, 'model'):
                base_client.model = model

            # Wrap in adapter for personas interface
            adapted_client = LLMClientAdapter(base_client)

            logger.info(
                "llm.client_resolved",
                provider=provider_name,
                model=model or getattr(base_client, 'model', 'unknown'),
                project_id=str(project_id),
            )
            return adapted_client

        except ValueError as e:
            logger.warning(
                "llm.provider_enum_error",
                provider=provider_name,
                error=str(e),
            )
            continue
        except Exception as e:
            logger.warning(
                "llm.provider_creation_error",
                provider=provider_name,
                error=str(e),
            )
            continue

    # If we get here, all providers in chain failed
    raise HTTPException(
        status_code=500,
        detail="Nenhum provedor de IA conseguiu ser inicializado. Configure pelo menos um em Settings > Provedor IA com chave válida.",
    )


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

    # Resolve LLM client respecting project_settings
    llm = await resolve_llm_client_for_route_map(db, route_map)
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

    # Resolve LLM client respecting project_settings
    llm = await resolve_llm_client_for_route_map(db, route_map)
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
        # Handle scores that might be a dict or dataclass
        scores_data = response.scores if isinstance(response.scores, dict) else response.scores.__dict__
        personas_dict[persona_tag] = PersonaResponseDetail(
            persona_tag=response.persona_tag,
            passada=response.passada,
            scores=PersonaScoreResponse(**scores_data),
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
