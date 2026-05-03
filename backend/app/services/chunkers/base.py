"""Chunker abstrato — segmenta documento em unidades atômicas."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import re


@dataclass
class RawChunk:
    id: str
    heading_path: str
    chunk_type: str
    text: str
    first_sentence: str
    token_count: int
    position: int


class Chunker(ABC):
    @abstractmethod
    def chunk(self, file_path: str) -> list[RawChunk]:
        """Segmenta arquivo em RawChunks ordenados."""
        ...

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """1 word ≈ 1.4 tokens (estimativa conservadora)."""
        return int(len(text.split()) * 1.4)

    @staticmethod
    def first_sentence(text: str, max_chars: int = 200) -> str:
        match = re.search(r'^[^.!?]{10,}[.!?]', text)
        if match:
            return match.group(0)[:max_chars]
        return text[:max_chars]
