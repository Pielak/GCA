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
        iteration_id: str | None = None,
    ) -> bytes:
        """
        Gera PDF com as questões da iteração.

        Args:
            project_name: nome do projeto
            questions: lista de questões (cada uma com id, text, context, pillar)
            iteration: número sequencial da iteração
            iteration_id: UUID da iteração (CustomQuestionnaireIteration.id).
                Gravado nos metadados do PDF (Keywords) como marker canônico
                `gca_iteration_id=<uuid>`. Usado pela Ingestão pra linkar o
                doc respondido à iteração correta automaticamente — sem
                precisar de upload pela aba Questões em Aberto.

        Returns:
            bytes do PDF gerado
        """
        buf = io.BytesIO()
        c = Canvas(buf, pagesize=A4)
        c.setTitle(f"Questões Abertas — Iteração {iteration}")
        c.setAuthor("GCA — Gerenciador Central de Arquiteturas")
        c.setSubject("GCA M01 — resposta iterativa do questionário customizado")
        # Marker canônico pra auto-linkagem ingestão → iteração (M01).
        # Sobrevive a save/edit nos PDF readers comuns (Acrobat, Chrome, Foxit).
        if iteration_id:
            c.setKeywords(f"gca_iteration_id={iteration_id}")
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
            # Page break PREVENTIVO: mede altura total da questão + campo e,
            # se não couber no resto da página, pula pra próxima ANTES de
            # começar a desenhar. Evita campo cortado entre páginas.
            needed = self._estimate_question_height(q)
            if y - needed < MB:
                c.showPage()
                y = PAGE_H - MT
            y = self._draw_question(c, form, q, y, field_idx)
            field_idx += 1

        c.save()
        buf.seek(0)
        return buf.getvalue()

    def _estimate_question_height(self, question: dict[str, Any]) -> float:
        """Altura total necessária pra desenhar a questão completa.

        Cálculo pessimista — é melhor sobrar espaço que cortar.
        """
        qtype = question.get("type", "text")
        text = question.get("text", "") or question.get("question", "")
        context = question.get("context", "")
        options = question.get("options") or []

        usable_w = PAGE_W - ML - MR - 0.5 * cm
        h = LINE_H  # cabeçalho Q + pilar
        h += LINE_H * max(1, len(self._wrap_text(text, max_width=usable_w))) + 4  # texto
        if context:
            h += LINE_H * min(2, max(1, len(self._wrap_text(context, max_width=usable_w)))) + 4
        if qtype == "choice" and options:
            h += LINE_H  # "Opções (responda com...)"
            for opt in options:
                h += LINE_H * max(1, len(self._wrap_text(f"  1. {opt}", max_width=usable_w - 0.3 * cm)))
            h += 4
        # Campo de resposta — muito maior agora (multi-line até 10k chars)
        h += self._field_height(qtype) + 0.5 * cm
        return h

    def _field_height(self, qtype: str) -> float:
        """Altura do textfield da resposta.

        - `choice`: menor (~3cm), respostas costumam ser curtas.
        - `text`: grande (~8cm, ~16 linhas visíveis) pra respostas longas.
        """
        return 3 * cm if qtype == "choice" else 8 * cm

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
        # Campos canônicos produzidos por parse_iterative_response:
        # id, type, text, context, pillar, required, options, max_chars.
        text = question.get("text", "") or question.get("question", "")
        context = question.get("context", "")
        pillar = question.get("pillar", "") or question.get("target_pillar", "")
        qtype = question.get("type", "text")

        # Número + código do pilar (ex: P3)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(VIOLET)
        pillar_code = "—"
        if pillar:
            try:
                pillar_code = pillar.split("_", 1)[0] if pillar.startswith("P") else "—"
            except Exception:  # noqa: BLE001
                pillar_code = "—"
        c.drawString(ML, y, f"Q{field_idx + 1}  [{pillar_code}]")
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
            for line in ctx_lines[:2]:
                c.drawString(ML + 0.3 * cm, y, line)
                y -= LINE_H
        y -= 4

        # Opções (só pra type=choice) — listadas numeradas.
        options = question.get("options") or []
        if qtype == "choice" and options:
            c.setFont("Helvetica", 8)
            c.setFillColor(SLATE_DARK)
            c.drawString(ML + 0.3 * cm, y, "Opções (responda com o número ou texto):")
            y -= LINE_H
            for idx, opt in enumerate(options, start=1):
                opt_lines = self._wrap_text(f"  {idx}. {opt}", max_width=PAGE_W - ML - MR - 0.8 * cm)
                for line in opt_lines:
                    c.drawString(ML + 0.6 * cm, y, line)
                    y -= LINE_H
            y -= 4

        # Campo de resposta — AcroForm multi-line com até 10k chars.
        # `fieldFlags='multiline'` ativa word-wrap automático pela largura
        # do campo no PDF reader. Quebra visual conforme o usuário digita.
        field_name = f"q_{qid}_{field_idx}"
        field_height = self._field_height(qtype)
        field_width = PAGE_W - ML - MR - 0.2 * cm

        # Fundo claro
        c.setFillColor(colors.HexColor("#f9fafb"))
        c.setStrokeColor(SLATE_LIGHT)
        c.setLineWidth(0.5)
        c.rect(ML + 0.1 * cm, y - field_height, field_width, field_height, fill=1)

        form.textfield(
            name=field_name,
            tooltip=(
                f"Resposta para questão {field_idx + 1}. "
                f"Digite sua resposta aqui — até 10 mil caracteres. "
                f"O texto quebra automaticamente conforme a largura do campo."
            ),
            x=int(ML + 0.15 * cm),
            y=int(y - field_height + 0.1 * cm),
            width=int(field_width - 0.2 * cm),
            height=int(field_height - 0.2 * cm),
            fontSize=9,
            fontName="Helvetica",
            maxlen=10000,
            fieldFlags="multiline",
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
