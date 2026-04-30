"""Schemas Pydantic para chunks e tags."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator


# As 8 tags possíveis (Auditor + 7 técnicas)
PersonaTag = Literal["AUD", "GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI"]
TECHNICAL_TAGS: list[PersonaTag] = ["GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI"]
ALL_TAGS: list[PersonaTag] = ["AUD"] + TECHNICAL_TAGS


class Chunk(BaseModel):
    id: str = Field(..., description="Identificador estável (ex: 'chunk_001')")
    heading_path: str
    chunk_type: Literal["section", "table", "list", "code"]
    text: str
    first_sentence: str
    token_count: int = Field(..., ge=0)
    position: int = Field(..., ge=0)
    tags: list[PersonaTag] = Field(default_factory=list, min_length=0)

    @field_validator('tags')
    @classmethod
    def validate_unique_tags(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Tags duplicadas")
        return v
