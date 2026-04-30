"""Base class for technical personas (Phase B)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import time
import structlog

from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


@dataclass
class PersonaScore:
    """Scores por pilar/aspecto."""
    escopo: int = 0      # GP: completude, clareza de requisitos
    stack: int = 0       # ARQ: tecnologias apropriadas
    dados: int = 0       # DBA: modelo de dados, performance
    implementacao: int = 0  # DEV: viabilidade, dependências
    testes: int = 0      # QA: cobertura, estratégia
    ux: int = 0          # UX: jornada, acessibilidade
    ui: int = 0          # UI: design system, consistência


@dataclass
class PersonaIssue:
    """Issue estruturado encontrado pela persona."""
    chunk_id: str
    category: str  # "ambiguity", "risk", "missing", "contradiction", "tech_debt"
    severity: str  # "blocker", "critical", "warning", "info"
    description: str
    suggested_action: Optional[str] = None


@dataclass
class PersonaQuestion:
    """Pergunta gerada pela persona para validador humano."""
    id: str
    question_text: str
    rationale: str
    answer_type: str  # "single_choice", "free_text", "numeric"
    severity: str  # "blocker", "important", "nice_to_have"
    chunk_refs: list[str] = field(default_factory=list)


@dataclass
class PersonaOutput:
    """Resposta estruturada de uma persona."""
    persona_tag: str
    passada: int  # 1 ou 2
    scores: PersonaScore
    approved: bool
    tentative: bool
    issues: list[PersonaIssue] = field(default_factory=list)
    questions: list[PersonaQuestion] = field(default_factory=list)
    justification: Optional[str] = None

    # Metadados de execução
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    elapsed_ms: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    fallback_used: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class Persona(ABC):
    """Base class for technical personas."""

    tag: str  # "gp", "arq", "dba", "dev", "qa", "ux", "ui"
    name: str

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    @abstractmethod
    async def analyze(
        self,
        chunks: list[Chunk],
        summary: str,
        highlights: dict,
        backlog: list,
        passada: int = 1,
        human_answers: Optional[dict] = None,
    ) -> PersonaOutput:
        """
        Analyze document chunks and produce persona response.

        Args:
            chunks: list of parsed chunks with tags
            summary: Auditor's summary (context)
            highlights: Auditor's highlights for this persona
            backlog: Auditor's backlog items
            passada: 1 (tentative) or 2 (final after human answers)
            human_answers: dict of answers to questions from Passada 1

        Returns:
            PersonaOutput with scores, issues, questions, etc.
        """
        ...

    def _create_output(
        self,
        scores: PersonaScore,
        approved: bool,
        issues: list[PersonaIssue] = None,
        questions: list[PersonaQuestion] = None,
        justification: str = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        elapsed_ms: int = 0,
        passada: int = 1,
    ) -> PersonaOutput:
        """Helper to create PersonaOutput."""
        return PersonaOutput(
            persona_tag=self.tag,
            passada=passada,
            scores=scores,
            approved=approved,
            tentative=(passada == 1),
            issues=issues or [],
            questions=questions or [],
            justification=justification,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
            elapsed_ms=elapsed_ms,
            llm_provider=self.llm.provider_name,
            llm_model=self.llm.model_name,
        )
