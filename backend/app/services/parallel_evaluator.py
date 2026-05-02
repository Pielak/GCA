"""ParallelEvaluator — Phase B orchestrator for 7 technical personas."""
import asyncio
import time
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
from app.services.personas.base import PersonaOutput, PersonaScore
from app.services.personas.gp import GPPersona
from app.services.personas.arq import ArchitectPersona
from app.services.personas.dba import DBAPersona
from app.services.personas.dev import DevPersona
from app.services.personas.qa import QAPersona
from app.services.personas.ux import UXPersona
from app.services.personas.ui import UIPersona
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


class ParallelEvaluator:
    """Executa 7 personas técnicas em paralelo (Passada 1 ou 2)."""

    PERSONAS = {
        "gp": GPPersona,
        "arq": ArchitectPersona,
        "dba": DBAPersona,
        "dev": DevPersona,
        "qa": QAPersona,
        "ux": UXPersona,
        "ui": UIPersona,
    }

    # Limite de tokens total por passada (soma token_count × personas)
    MAX_TOKEN_BUDGET = 100_000

    def __init__(self, llm_client: LLMClient, db: AsyncSession):
        self.llm = llm_client
        self.db = db

    @staticmethod
    def _filter_chunks_for_persona(chunks: list[Chunk], persona_tag: str) -> list[Chunk]:
        """Filtra chunks relevantes ao domínio da persona pela tag nos metadados."""
        tag_upper = persona_tag.upper()
        relevant = [c for c in chunks if tag_upper in (c.tags or [])]
        if not relevant:
            # Fallback: se nenhum chunk tem tag da persona, envia chunks sem tag
            # para que persona declare "sem conteúdo para análise"
            relevant = [c for c in chunks if not c.tags]
        if not relevant:
            # Se ainda vazio, envia até 3 chunks genéricos com texto truncado
            import copy
            fallback = []
            for c in chunks[:3]:
                fb = copy.copy(c)
                fb.text = c.text[:500]
                fallback.append(fb)
            return fallback
        return relevant

    def _compute_token_budget(self, chunks_by_persona: dict[str, list[Chunk]]) -> int:
        """Estima total de tokens se rodarmos todas as personas em paralelo."""
        total = 0
        for chunks in chunks_by_persona.values():
            total += sum(c.token_count for c in chunks)
        return total

    @staticmethod
    def _make_fallback_persona_output(
        persona_tag: str, passada: int, error: str,
    ) -> PersonaOutput:
        """Produz PersonaOutput degradado quando uma persona crasha."""
        return PersonaOutput(
            persona_tag=persona_tag,
            passada=passada,
            scores=PersonaScore(
                escopo=50, stack=50, dados=50,
                implementacao=50, testes=50, ux=50, ui=50,
            ),
            approved=False,
            tentative=(passada == 1),
            issues=[],
            questions=[],
            justification=f"(Análise de {persona_tag} indisponível — crash no parallel evaluator)",
            input_tokens=0,
            output_tokens=0,
            elapsed_ms=0,
            error_code="PAR-EVAL-001",
            error_message=error[:500],
            fallback_used=True,
        )

    @staticmethod
    def _safe_gather_results(
        raw_results: list,
        task_keys: list[str],
        passada: int,
    ) -> dict[str, PersonaOutput]:
        """Processa resultados de asyncio.gather com return_exceptions=True.

        Personas que levantaram exceção viram fallback; as outras seguem normais.
        """
        results: dict[str, PersonaOutput] = {}
        for idx, (tag, result) in enumerate(zip(task_keys, raw_results)):
            if isinstance(result, Exception):
                logger.exception(
                    "parallel_evaluator.persona_crashed",
                    persona_tag=tag,
                    passada=passada,
                    error=str(result),
                )
                results[tag] = ParallelEvaluator._make_fallback_persona_output(
                    tag, passada, str(result),
                )
            else:
                results[tag] = result
        return results

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
        all_chunks = [
            Chunk(**chunk_data)
            for chunk_data in route_map.chunks
        ]

        # Filtrar chunks por domínio de cada persona
        chunks_by_persona = {
            tag: self._filter_chunks_for_persona(all_chunks, tag)
            for tag in self.PERSONAS
        }

        # Token budget guard: se total > MAX_TOKEN_BUDGET, rodar em 2 ondas
        estimated_tokens = self._compute_token_budget(chunks_by_persona)
        wave_count = 1 if estimated_tokens <= self.MAX_TOKEN_BUDGET else 2
        logger.info(
            "parallel_evaluator.token_budget",
            estimated_tokens=estimated_tokens,
            max_budget=self.MAX_TOKEN_BUDGET,
            wave_count=wave_count,
        )

        # Prepare common inputs
        summary = auditor_output.summary
        highlights = auditor_output.highlights
        backlog = auditor_output.backlog_to_specialists

        # Run personas in parallel
        start = time.perf_counter()
        results = {}

        persona_tags = list(self.PERSONAS.keys())
        if wave_count == 1:
            # Todas as personas em paralelo
            tasks = {}
            for persona_tag, persona_cls in self.PERSONAS.items():
                persona = persona_cls(self.llm)
                tasks[persona_tag] = persona.analyze(
                    chunks=chunks_by_persona[persona_tag],
                    summary=summary,
                    highlights=highlights,
                    backlog=backlog,
                    passada=1,
                    human_answers=None,
                )
            raw_results = await asyncio.gather(
                *tasks.values(), return_exceptions=True,
            )
            results = self._safe_gather_results(
                list(raw_results), list(tasks.keys()), passada=1,
            )
        else:
            # 2 ondas: metade das personas em cada
            mid = len(persona_tags) // 2
            wave1_tags = persona_tags[:mid]
            wave2_tags = persona_tags[mid:]

            logger.info("parallel_evaluator.wave1_start", tags=wave1_tags)
            tasks1 = {}
            for tag in wave1_tags:
                persona = self.PERSONAS[tag](self.llm)
                tasks1[tag] = persona.analyze(
                    chunks=chunks_by_persona[tag],
                    summary=summary,
                    highlights=highlights,
                    backlog=backlog,
                    passada=1,
                    human_answers=None,
                )
            raw1 = await asyncio.gather(
                *tasks1.values(), return_exceptions=True,
            )
            results.update(self._safe_gather_results(
                list(raw1), list(tasks1.keys()), passada=1,
            ))

            logger.info("parallel_evaluator.wave2_start", tags=wave2_tags)
            tasks2 = {}
            for tag in wave2_tags:
                persona = self.PERSONAS[tag](self.llm)
                tasks2[tag] = persona.analyze(
                    chunks=chunks_by_persona[tag],
                    summary=summary,
                    highlights=highlights,
                    backlog=backlog,
                    passada=1,
                    human_answers=None,
                )
            raw2 = await asyncio.gather(
                *tasks2.values(), return_exceptions=True,
            )
            results.update(self._safe_gather_results(
                list(raw2), list(tasks2.keys()), passada=1,
            ))
        elapsed_sec = time.perf_counter() - start

        # Map results to GatekeeperPersonaResponse models
        responses = {}
        for persona_tag, persona_output in results.items():
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

        await self.db.commit()

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
        all_chunks = [
            Chunk(**chunk_data)
            for chunk_data in route_map.chunks
        ]

        # Filtrar chunks por domínio de cada persona
        chunks_by_persona = {
            tag: self._filter_chunks_for_persona(all_chunks, tag)
            for tag in self.PERSONAS
        }

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
                chunks=chunks_by_persona[persona_tag],
                summary=summary,
                highlights=highlights,
                backlog=backlog,
                passada=2,
                human_answers=human_answers,
            )

        raw_results = await asyncio.gather(
            *tasks.values(), return_exceptions=True,
        )
        results = self._safe_gather_results(
            list(raw_results), list(tasks.keys()), passada=2,
        )
        elapsed_sec = time.perf_counter() - start

        # Map results to GatekeeperPersonaResponse models
        responses = {}
        for persona_tag, persona_output in results.items():
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

        await self.db.commit()

        logger.info("Passada 2 complete", extra={
            "elapsed_sec": f"{elapsed_sec:.1f}",
            "personas_approved": len([r for r in responses.values() if r.approved]),
            "personas_total": len(responses),
        })

        return responses
