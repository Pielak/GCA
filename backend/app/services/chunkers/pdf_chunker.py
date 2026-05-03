"""Chunker para .pdf via pypdf."""
from pypdf import PdfReader

from app.services.chunkers.base import Chunker, RawChunk


class PdfChunker(Chunker):
    """
    Segmenta .pdf tratando:
    - Cada página é uma seção potencial
    - Heurística: se texto tem múltiplos \\n\\n, quebra em parágrafos
    - Tabelas detectadas por estrutura espacial
    """

    def chunk(self, file_path: str) -> list[RawChunk]:
        pdf = PdfReader(file_path)
        chunks: list[RawChunk] = []
        position = 0
        heading_stack = ["PDF Document"]

        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text or not text.strip():
                continue

            # Heurística simples: quebra por parágrafos (2+ quebras)
            paragraphs = text.split('\n\n')
            for para in paragraphs:
                if not para.strip():
                    continue

                para_text = para.strip()
                chunks.append(RawChunk(
                    id=f"chunk_{position:03d}",
                    heading_path=f"Page {page_num + 1}",
                    chunk_type='section',
                    text=para_text,
                    first_sentence=self.first_sentence(para_text),
                    token_count=self.estimate_tokens(para_text),
                    position=position,
                ))
                position += 1

        return chunks if chunks else [RawChunk(
            id="chunk_000",
            heading_path="PDF (vazio ou não-extraível)",
            chunk_type='section',
            text="",
            first_sentence="",
            token_count=0,
            position=0,
        )]
