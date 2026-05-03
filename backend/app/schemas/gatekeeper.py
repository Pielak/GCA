"""Schemas Pydantic para endpoints do Gatekeeper (Phase B)."""
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class HumanAnswerInput(BaseModel):
    """Resposta humana a uma pergunta de persona."""
    persona_tag: str
    question_id: str
    answer_text: str


class HumanAnswersRequest(BaseModel):
    """Solicitação de coleta de respostas humanas."""
    route_map_id: UUID
    answers: List[HumanAnswerInput]


class PersonaScoreResponse(BaseModel):
    """Scores de uma persona."""
    escopo: int = 0
    stack: int = 0
    dados: int = 0
    implementacao: int = 0
    testes: int = 0
    ux: int = 0
    ui: int = 0


class PersonaResponseDetail(BaseModel):
    """Resposta detalhada de uma persona."""
    persona_tag: str
    passada: int
    scores: PersonaScoreResponse
    approved: bool
    tentative: bool
    issues: List[dict]
    questions: List[dict]
    justification: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0

    class Config:
        from_attributes = True


class PersonasBoardResponse(BaseModel):
    """Board visual com status de todas as personas."""
    route_map_id: UUID
    passada: int
    total_personas: int
    approved_count: int
    personas: dict[str, PersonaResponseDetail]  # {persona_tag: PersonaResponseDetail}


class Passada1Request(BaseModel):
    """Solicitação para executar Passada 1."""
    route_map_id: UUID
    execute_now: bool = True  # Se false, agenda para executar later


class Passada1Response(BaseModel):
    """Resposta de Passada 1."""
    route_map_id: UUID
    personas_board: PersonasBoardResponse
    total_questions: int
    questions_to_answer: List[dict]


class Passada2Request(BaseModel):
    """Solicitação para executar Passada 2."""
    route_map_id: UUID
    human_answers: List[HumanAnswerInput]


class Passada2Response(BaseModel):
    """Resposta de Passada 2."""
    route_map_id: UUID
    personas_board: PersonasBoardResponse
    all_approved: bool
    blocking_issues: List[dict]
