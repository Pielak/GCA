"""Chunker para .md via markdown-it-py."""
import re
from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.services.chunkers.base import Chunker, RawChunk


class MarkdownChunker(Chunker):
    """
    Segmenta .md tratando:
    - Headings como início de seção
    - Cada seção entre headings = 1 chunk
    - Tabelas como chunks atômicos
    """

    def chunk(self, file_path: str) -> list[RawChunk]:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        md = MarkdownIt('commonmark')
        tokens = md.parse(text)

        chunks: list[RawChunk] = []
        heading_stack: list[str] = []
        section_buf: list[str] = []
        position = 0

        for i, token in enumerate(tokens):
            if token.type == 'heading_open':
                # Fecha seção pendente
                if section_buf:
                    content = '\n'.join(section_buf).strip()
                    if content:
                        chunks.append(self._mk_section(position, heading_stack, content))
                        position += 1
                    section_buf = []

                level = int(token.tag[1])
                heading_stack = heading_stack[:level - 1]

                # Próximo token é heading_close, depois inline com conteúdo
                if i + 1 < len(tokens) and tokens[i + 1].type == 'inline':
                    heading_text = tokens[i + 1].content.strip()
                    heading_stack.append(heading_text)

            elif token.type == 'inline' and (i == 0 or tokens[i - 1].type != 'heading_open'):
                if token.content.strip():
                    section_buf.append(token.content)

            elif token.type == 'table_open':
                if section_buf:
                    content = '\n'.join(section_buf).strip()
                    if content:
                        chunks.append(self._mk_section(position, heading_stack, content))
                        position += 1
                    section_buf = []

                table_text = self._extract_table(tokens, i)
                chunks.append(RawChunk(
                    id=f"chunk_{position:03d}",
                    heading_path=' / '.join(heading_stack) or 'Sem heading',
                    chunk_type='table',
                    text=table_text,
                    first_sentence=self.first_sentence(table_text),
                    token_count=self.estimate_tokens(table_text),
                    position=position,
                ))
                position += 1

        if section_buf:
            content = '\n'.join(section_buf).strip()
            if content:
                chunks.append(self._mk_section(position, heading_stack, content))

        return chunks

    def _mk_section(self, position: int, heading_stack: list[str], text: str) -> RawChunk:
        return RawChunk(
            id=f"chunk_{position:03d}",
            heading_path=' / '.join(heading_stack) or 'Sem heading',
            chunk_type='section',
            text=text,
            first_sentence=self.first_sentence(text),
            token_count=self.estimate_tokens(text),
            position=position,
        )

    def _extract_table(self, tokens: list[Token], start_idx: int) -> str:
        lines = []
        i = start_idx + 1
        while i < len(tokens) and tokens[i].type != 'table_close':
            if tokens[i].type == 'inline':
                lines.append(tokens[i].content)
            i += 1
        return '\n'.join(lines)
