"""Chunker para .docx via python-docx."""
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.table import Table

from app.services.chunkers.base import Chunker, RawChunk


class DocxChunker(Chunker):
    """
    Segmenta .docx tratando:
    - Headings (H1/H2/H3) como início de seção
    - Cada seção entre headings vira 1 chunk
    - Cada tabela é UM chunk atômico
    """

    def chunk(self, file_path: str) -> list[RawChunk]:
        doc = DocxDocument(file_path)
        chunks: list[RawChunk] = []
        heading_stack: list[str] = []
        section_buf: list[str] = []
        position = 0

        for elem in doc.element.body.iterchildren():
            tag = elem.tag

            if tag == qn('w:p'):
                p = Paragraph(elem, doc)

                if p.style.name.startswith(('Heading', 'Título')):
                    # Fecha seção pendente
                    if section_buf:
                        text = '\n'.join(section_buf).strip()
                        if text:
                            chunks.append(self._mk_section(position, heading_stack, text))
                            position += 1
                        section_buf = []

                    level = self._heading_level(p.style.name)
                    heading_stack = heading_stack[:level - 1]
                    heading_stack.append(p.text.strip())
                else:
                    if p.text.strip():
                        section_buf.append(p.text)

            elif tag == qn('w:tbl'):
                if section_buf:
                    text = '\n'.join(section_buf).strip()
                    if text:
                        chunks.append(self._mk_section(position, heading_stack, text))
                        position += 1
                    section_buf = []

                table = Table(elem, doc)
                table_text = self._serialize_table(table)
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
            text = '\n'.join(section_buf).strip()
            if text:
                chunks.append(self._mk_section(position, heading_stack, text))

        return chunks

    def _heading_level(self, style_name: str) -> int:
        import re
        m = re.search(r'(\d+)', style_name)
        return int(m.group(1)) if m else 1

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

    def _serialize_table(self, table: Table) -> str:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
            rows.append(' | '.join(cells))
        return '\n'.join(rows)
