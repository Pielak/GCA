"""ParallelEvaluator — Phase B orchestrator for 7 technical personas."""
import asyncio
import time
from uuid import UUID
import structlog
from sqlalchemy.orm import Session

from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
from app.services.personas.base import PersonaOutput
from app.services.personas.gp import GPPersona
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


class ParallelEvaluator:
    """Executa 7 personas técnicas em paralelo (Passada 1 ou 2)."""

    PERSONAS = {
        "gp": GPPersona,
        # "arq": ArchitectPersona,  # TODO: Phase B.1
        # "dba": DBAPersona,         # TODO: Phase B.1
        # "dev": DevPersona,         # TODO: Phase B.1
        # "qa": QAPersona,           # TODO: Phase B.1
        # "ux": UXPersona,           # TODO: Phase C
        # "ui": UIPersona,           # TODO: Phase C
    }

    def __init__(self, llm_client: LLMClient, db: Session):
        self.llm = llm_client
        self.db = db

    async def run_passada_1(
        self,
        route_map: DocumentRouteMap,
        auditor_output: AuditorOutput,
    ) -> dict[str, GatekeeperPersonaResponse]:
        """
        Run Passada 1 (tentative analysis).

        Args:
            route_map: DocumentRouteMap from Phase A
            auditor_output: AuditorOutput from Phase A

        Returns:
            dict of persona_tag → GatekeeperPersonaResponse (persisted to DB)
        """

        logger.info("Starting Passada 1 (tentative analysis)", extra={
            "route_map_id": route_map.id,
            "personas_count": len(self.PERSONAS),
        })

        # Reconstruct chunks from route_map
        chunks = [
            Chunk(**chunk_data)
            for chunk_data in route_map.chunks
        ]

        # Prepare common inputs
        summary = auditor_output.summary
        highlights = auditor_output.highlights
        backlog = auditor_output.backlog_to_specialists

        # Run personas in parallel
        start = time.perf_counter()
        tasks = {}
        for persona_tag, persona_cls in self.PERSONAS.items():
            persona = persona_cls(self.llm)
            tasks[persona_tag] = persona.analyze(
                chunks=chunks,
                summary=summary,
                highlights=highlights,
                backlog=backlog,
                passada=1,
                human_answers=None,
            )

        results = await asyncio.gather(*tasks.values())
        elapsed_sec = time.perf_counter() - start

        # Map results to GatekeeperPersonaResponse models
        responses = {}
        for (persona_tag, _), persona_output in zip(tasks.items(), results):
            response_model = GatekeeperPersonaResponse(
                route_map_id=route_map.id,
                persona_tag=persona_tag,
                passada=1,
                scores=persona_output.scores.__dict__,
                approved=persona_output.approved,
                tentative=True,
                issues=[issue.__dict__ for issue in persona_output.issues],
                questions=[q.__dict__ for q in persona_output.questions],
                justification=persona_output.justification,
                input_tokens=persona_output.input_tokens,
                output_tokens=persona_output.output_tokens,
                cached_input_tokens=persona_output.cached_input_tokens,
                elapsed_ms=persona_output.elapsed_ms,
                error_code=persona_output.error_code,
                error_message=persona_output.error_message,
                fallback_used=persona_output.fallback_used,
                llm_provider=persona_output.llm_provider,
                llm_model=persona_output.llm_model,
            )
            self.db.add(response_model)
            responses[persona_tag] = response_model

        self.db.commit()

        logger.info("Passada 1 complete", extra={
            "elapsed_sec": f"{elapsed_sec:.1f}",
            "personas_ok": len([r for r in responses.values() if r.approved]),
            "personas_total": len(responses),
            "questions_total": sum(len(r.questions) for r in responses.values()),
        })

        return responses

    async def run_passada_2(
        self,
        route_map: DocumentRouteMap,
        auditor_output: AuditorOutput,
        human_answers: dict[str, str],  # {question_id → answer_text}
    ) -> dict[str, GatekeeperPersonaResponse]:
        """
        Run Passada 2 (final analysis after human answers).

        Args:
            route_map: DocumentRouteMap from Phase A
            auditor_output: AuditorOutput from Phase A
            human_answers: Answers to questions from Passada 1

        Returns:
            dict of persona_tag → GatekeeperPersonaResponse (passada=2, tentative=false)
        """

        logger.info("Starting Passada 2 (final analysis)", extra={
            "route_map_id": route_map.id,
            "human_answers_count": len(human_answers),
        })

        # Reconstruct chunks from route_map
        chunks = [
            Chunk(**chunk_data)
            for chunk_data in route_map.chunks
        ]

        # Prepare common inputs
        summary = auditor_output.summary
        highlights = auditor_output.highlights
        backlog = auditor_output.backlog_to_specialists

        # Run personas in parallel with human context
        start = time.perf_counter()
        tasks = {}
        for persona_tag, persona_cls in self.PERSONAS.items():
            persona = persona_cls(self.llm)
            tasks[persona_tag] = persona.analyze(
                chunks=chunks,
                summary=summary,
                highlights=highlights,
                backlog=backlog,
                passada=2,
                human_answers=human_answers,
            )

        results = await asyncio.gather(*tasks.values())
        elapsed_sec = time.perf_counter() - start

        # Map results to GatekeeperPersonaResponse models
        responses = {}
        for (persona_tag, _), persona_output in zip(tasks.items(), results):
            response_model = GatekeeperPersonaResponse(
                route_map_id=route_map.id,
                persona_tag=persona_tag,
                passada=2,
                scores=persona_output.scores.__dict__,
                approved=persona_output.approved,
                tentative=False,
                issues=[issue.__dict__ for issue in persona_output.issues],
                questions=[q.__dict__ for q in persona_output.questions],
                justification=persona_output.justification,
                input_tokens=persona_output.input_tokens,
                output_tokens=persona_output.output_tokens,
                cached_input_tokens=persona_output.cached_input_tokens,
                elapsed_ms=persona_output.elapsed_ms,
                error_code=persona_output.error_code,
                error_message=persona_output.error_message,
                fallback_used=persona_output.fallback_used,
                llm_provider=persona_output.llm_provider,
                llm_model=persona_output.llm_model,
            )
            self.db.add(response_model)
            responses[persona_tag] = response_model

        self.db.commit()

        logger.info("Passada 2 complete", extra={
            "elapsed_sec": f"{elapsed_sec:.1f}",
            "personas_approved": len([r for r in responses.values() if r.approved]),
            "personas_total": len(responses),
        })

        return responses
