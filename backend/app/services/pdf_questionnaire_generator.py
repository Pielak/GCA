"""M01 — gerador PDF de iterações de questionário customizado.

Cria PDF editável com as questões geradas para a iteração.
Usa ReportLab AcroForm para campos interativos.
"""
from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas

# ──────────────────────────────────────────────────────────────────
# Constantes de layout
# ──────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
ML, MR, MT, MB = 2 * cm, 2 * cm, 2 * cm, 2 * cm

# Cores do design system GCA
VIOLET = colors.HexColor("#6366f1")
SLATE_DARK = colors.HexColor("#1f2937")
SLATE_MID = colors.HexColor("#6b7280")
SLATE_LIGHT = colors.HexColor("#e5e7eb")

# Distâncias
LINE_H = 12  # altura padrão de texto
SECTION_SPACE = 18  # espaço entre seções


class PDFQuestionnaireGenerator:
    """Gerador de PDF para iterações de questionário customizado."""

    def generate_pdf(
        self,
        project_name: str,
        questions: list[dict[str, Any]],
        iteration: int,
    ) -> bytes:
        """
        Gera PDF com as questões da iteração.

        Args:
            project_name: nome do projeto
            questions: lista de questões (cada uma com id, question, context, target_pillar)
            iteration: número da iteração

        Returns:
            bytes do PDF gerado
        """
        buf = io.BytesIO()
        c = Canvas(buf, pagesize=A4)
        c.setTitle(f"Questões Abertas — Iteração {iteration}")
        c.setAuthor("GCA — Gerenciador Central de Arquiteturas")
        form = c.acroForm

        y = PAGE_H - MT

        # ── Cabeçalho ──
        c.setFillColor(VIOLET)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(ML, y, "GCA")
        c.setFont("Helvetica", 10)
        c.setFillColor(SLATE_MID)
        c.drawString(ML + 55, y + 2, "Gerenciador Central de Arquiteturas")
        y -= 28

        c.setFillColor(SLATE_DARK)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(ML, y, "Questões Abertas para Melhoria")
        y -= 20

        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(VIOLET)
        c.drawString(ML, y, f"{project_name} — Iteração {iteration}")
        y -= 16

        # Linha separadora
        c.setStrokeColor(VIOLET)
        c.setLineWidth(1.5)
        c.line(ML, y, PAGE_W - MR, y)
        y -= 16

        # Instruções
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(SLATE_DARK)
        c.drawString(ML, y, "INSTRUÇÕES")
        y -= 13
        c.setFont("Helvetica", 8)
        c.setFillColor(SLATE_MID)
        instrucoes = [
            "1. Responda as questões abertas abaixo digitando diretamente nos campos de texto.",
            "2. Responda em português-BR de forma concisa e factual.",
            "3. Salve o PDF preenchido e faça upload no GCA (aba 'Questões Abertas').",
            "4. As respostas serão analisadas por IA e o OCG será re-avaliado automaticamente.",
        ]
        for line in instrucoes:
            c.drawString(ML, y, line)
            y -= 11
        y -= 8

        # ── Questões ──
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(SLATE_DARK)
        c.drawString(ML, y, "QUESTÕES")
        y -= SECTION_SPACE

        field_idx = 0
        for q in questions:
            y = self._draw_question(c, form, q, y, field_idx)
            field_idx += 1
            if y < MB + 40:  # nova página se faltando espaço
                c.showPage()
                y = PAGE_H - MT

        c.save()
        buf.seek(0)
        return buf.getvalue()

    def _draw_question(
        self,
        c: Canvas,
        form: Any,
        question: dict[str, Any],
        y: float,
        field_idx: int,
    ) -> float:
        """Desenha uma questão com campo de texto interativo.

        Returns:
            nova posição Y
        """
        qid = question.get("id", f"q_{field_idx}")
        text = question.get("question", "")
        context = question.get("context", "")
        pillar = question.get("target_pillar", "")

        # Número + pilar
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(VIOLET)
        pillar_text = f"P{pillar[-1]}" if pillar and pillar.startswith("P") else "—"
        c.drawString(ML, y, f"Q{field_idx + 1}  [{pillar_text}]")
        y -= LINE_H

        # Texto da pergunta
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(SLATE_DARK)
        lines = self._wrap_text(text, max_width=PAGE_W - ML - MR - 0.5 * cm)
        for line in lines:
            c.drawString(ML + 0.3 * cm, y, line)
            y -= LINE_H
        y -= 4

        # Contexto (menor, italizado)
        if context:
            c.setFont("Helvetica-Oblique", 8)
            c.setFillColor(SLATE_MID)
            ctx_lines = self._wrap_text(context, max_width=PAGE_W - ML - MR - 0.5 * cm)
            for line in ctx_lines[:2]:  # max 2 linhas de contexto
                c.drawString(ML + 0.3 * cm, y, line)
                y -= LINE_H
        y -= 6

        # Campo de texto (multilinhas)
        field_name = f"q_{qid}_{field_idx}"
        field_height = 3 * cm
        field_width = PAGE_W - ML - MR - 0.2 * cm

        # Desenha fundo claro para o campo
        c.setFillColor(colors.HexColor("#f9fafb"))
        c.setStrokeColor(SLATE_LIGHT)
        c.setLineWidth(0.5)
        c.rect(ML + 0.1 * cm, y - field_height, field_width, field_height, fill=1)

        # Campo AcroForm multilinhas
        form.textfield(
            name=field_name,
            tooltip=f"Resposta para questão {field_idx + 1}",
            x=ML + 0.15 * cm,
            y=y - field_height + 0.1 * cm,
            width=field_width - 0.2 * cm,
            height=field_height - 0.2 * cm,
            multiline=True,
            fontSize=9,
            fontName="Helvetica",
        )

        y -= field_height + 0.5 * cm
        return y

    @staticmethod
    def _wrap_text(text: str, max_width: float, font_size: int = 9) -> list[str]:
        """Quebra texto em linhas para caber na largura máxima.

        Aproximação: assume Helvetica, ~4.5 caracteres por cm.
        """
        approx_chars_per_line = int((max_width / cm) * 4.5)
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) <= approx_chars_per_line:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines


# Singleton global
pdf_generator = PDFQuestionnaireGenerator()
