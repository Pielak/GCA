"""MVP 9 Fase 9.5.1 — Geração de template PDF AcroForm por item do Roadmap.

Contrato §7 MVP 9 (semântica nova confirmada pelo stakeholder):
  - GP clica num item → backend gera PDF com AcroForm fields editáveis;
  - cabeçalho do item + seções pré-preenchidas com dados já no OCG
    (texto preto, fixo) + lacunas em **amarelo** com fields editáveis;
  - GP baixa, abre em qualquer leitor PDF, preenche, salva, e faz upload
    na aba Ingestão (Fase 9.5.2 detecta `module_id` embutido e vincula);
  - pipeline processa via Arguidor → item vira `adicionado` →
    DELIVERABLE automático (Fase 9.5.2).

Fonte das seções: `module_candidates.details_json` produzido pela
Fase 9.2. Se o item ainda não tem detalhes gerados, este service
delega ao `module_details_service.get_or_generate_details` antes
(custo: uma chamada Ollama local).

`module_id` é embutido em **3 lugares pra redundância**:
  1. Hidden AcroForm field `_gca_module_id` (parsável via pypdf).
  2. PDF metadata `/Subject` no formato `gca-module:{uuid}`.
  3. Footer visual em texto pequeno (último recurso).

Sem assinatura digital nesta fase — o pipeline registra hash do upload
no audit_log normal (DT-063 já cobre).
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.acroform import AcroForm
from reportlab.pdfgen import canvas as pdf_canvas
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.module_categories import CATEGORY_LABELS_PT_BR
from app.models.base import ModuleCandidate

logger = structlog.get_logger(__name__)


# Paleta — cinza escuro do "Observatory" design system, com lacunas amarelas
COLOR_HEADER_BG = HexColor("#1a1f2e")
COLOR_INK = HexColor("#1a1a1a")
COLOR_INK_MUTED = HexColor("#5a5a5a")
COLOR_OCG_VALUE = HexColor("#0f5132")  # verde escuro: já está no OCG
COLOR_GAP_BG = HexColor("#fff3cd")     # amarelo claro: campo a preencher
COLOR_GAP_BORDER = HexColor("#856404")
COLOR_SECTION_RULE = HexColor("#cccccc")

# Hidden field name conhecido pelo upload handler da Fase 9.5.2
HIDDEN_MODULE_ID_FIELD = "_gca_module_id"


async def generate_template_pdf(
    db: AsyncSession,
    project_id: UUID,
    module_id: UUID,
) -> bytes:
    """Gera PDF AcroForm do item, regerando detalhamento se ausente.

    Retorna bytes prontos pra HTTP Response com `application/pdf`.
    """
    module = await db.get(ModuleCandidate, module_id)
    if not module or module.project_id != project_id:
        raise ValueError(f"Módulo {module_id} não encontrado no projeto {project_id}")

    # Carrega/gera detalhamento (Fase 9.2)
    if module.details_json:
        try:
            details = json.loads(module.details_json)
        except (ValueError, TypeError):
            details = await _force_generate(db, project_id, module_id)
    else:
        details = await _force_generate(db, project_id, module_id)

    return _render_pdf(module, details)


async def _force_generate(db: AsyncSession, project_id: UUID, module_id: UUID) -> dict[str, Any]:
    from app.services.module_details_service import get_or_generate_details
    return await get_or_generate_details(db, project_id, module_id, force_regenerate=False)


# ---------------------------------------------------------------------------
# Render PDF (síncrono — reportlab não é async)
# ---------------------------------------------------------------------------

def _render_pdf(module: ModuleCandidate, details: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Metadata pra rastreabilidade no upload
    c.setTitle(f"GCA Template — {module.name}")
    c.setSubject(f"gca-module:{module.id}")
    c.setAuthor("GCA — Roadmap Foundation")
    c.setKeywords([
        f"gca-module-id={module.id}",
        f"gca-project-id={module.project_id}",
        f"gca-module-type={module.module_type}",
    ])

    state = _LayoutState(canvas=c, width=width, height=height)

    _draw_header(state, module)
    _draw_module_summary(state, module, details)
    _draw_template_sections(state, module, details)
    _draw_free_text(state, module)
    _draw_footer(state, module)

    # Hidden field pro upload handler ler module_id mesmo se metadata for stripped.
    # AcroForm exige posição — colocamos em uma área "fora de tela" no rodapé,
    # mas em y > 0 pra reportlab aceitar. Visualmente em cor branca sobre branco.
    state.canvas.setFillColor(white)
    state.canvas.acroForm.textfield(
        name=HIDDEN_MODULE_ID_FIELD,
        value=str(module.id),
        x=0.1 * cm, y=0.1 * cm,
        width=0.5 * cm, height=0.3 * cm,
        borderStyle="solid",
        borderWidth=0,
        fillColor=white,
        textColor=white,
        fontName="Helvetica",
        fontSize=2,
    )
    state.canvas.setFillColor(black)

    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------

class _LayoutState:
    """Mantém posição vertical conforme desenhamos top→bottom."""

    LEFT = 2 * cm
    RIGHT_PAD = 2 * cm
    BOTTOM_MARGIN = 2 * cm
    TOP_MARGIN = 2 * cm

    def __init__(self, *, canvas, width, height):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.y = height - self.TOP_MARGIN
        self.right = width - self.RIGHT_PAD

    @property
    def content_width(self) -> float:
        return self.right - self.LEFT

    def newpage(self):
        self.canvas.showPage()
        self.y = self.height - self.TOP_MARGIN

    def need(self, space: float):
        if self.y - space < self.BOTTOM_MARGIN:
            self.newpage()


def _draw_header(state: _LayoutState, module: ModuleCandidate):
    c = state.canvas
    band_h = 2.2 * cm
    c.setFillColor(COLOR_HEADER_BG)
    c.rect(0, state.height - band_h, state.width, band_h, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(state.LEFT, state.height - 1.0 * cm, "GCA — Template do item de Roadmap")
    c.setFont("Helvetica", 9)
    cat_label = CATEGORY_LABELS_PT_BR.get(module.module_type or "", module.module_type or "—")
    c.drawString(state.LEFT, state.height - 1.5 * cm, f"Categoria: {cat_label}")
    c.drawString(state.LEFT, state.height - 1.95 * cm,
                 f"Status atual: {module.status} · Prioridade: {module.priority}")

    # Title à direita: nome do item
    c.setFont("Helvetica-Bold", 11)
    text = (module.name or "")[:60]
    c.drawRightString(state.right, state.height - 1.0 * cm, text)
    c.setFont("Helvetica", 8)
    c.drawRightString(state.right, state.height - 1.5 * cm,
                      f"id: {str(module.id)[:13]}…")
    c.drawRightString(state.right, state.height - 1.95 * cm,
                      f"emitido em {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    state.y = state.height - band_h - 0.8 * cm
    c.setFillColor(COLOR_INK)


def _draw_module_summary(state: _LayoutState, module: ModuleCandidate, details: dict[str, Any]):
    c = state.canvas
    state.need(3.5 * cm)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(COLOR_INK)
    c.drawString(state.LEFT, state.y, "1. Sobre o item")
    state.y -= 0.4 * cm
    _hr(state)

    c.setFont("Helvetica", 9.5)
    c.setFillColor(COLOR_INK_MUTED)
    c.drawString(state.LEFT, state.y, "Descrição do Roadmap:")
    state.y -= 0.4 * cm
    c.setFillColor(COLOR_INK)
    state.y -= _draw_wrapped(c, module.description or "(sem descrição)",
                              x=state.LEFT, y=state.y, max_width=state.content_width,
                              font="Helvetica", size=10)

    what_it_is = (details.get("what_it_is") or "").strip()
    if what_it_is:
        state.y -= 0.4 * cm
        c.setFillColor(COLOR_INK_MUTED)
        c.setFont("Helvetica", 9.5)
        c.drawString(state.LEFT, state.y, "Detalhamento técnico (gerado por IA local):")
        state.y -= 0.4 * cm
        c.setFillColor(COLOR_INK)
        state.y -= _draw_wrapped(c, what_it_is, x=state.LEFT, y=state.y,
                                  max_width=state.content_width,
                                  font="Helvetica", size=10)

    prereqs = details.get("prerequisites") or []
    if prereqs:
        state.y -= 0.5 * cm
        c.setFillColor(COLOR_INK_MUTED)
        c.setFont("Helvetica", 9.5)
        c.drawString(state.LEFT, state.y, "Pré-requisitos:")
        state.y -= 0.4 * cm
        c.setFillColor(COLOR_INK)
        for p in prereqs[:5]:
            state.y -= _draw_wrapped(c, f"• {p}", x=state.LEFT + 0.3 * cm, y=state.y,
                                      max_width=state.content_width - 0.3 * cm,
                                      font="Helvetica", size=9.5)
            state.y -= 0.05 * cm


def _draw_template_sections(state: _LayoutState, module: ModuleCandidate, details: dict[str, Any]):
    sections = details.get("suggested_template_sections") or []
    if not sections:
        return

    c = state.canvas
    state.y -= 0.6 * cm
    state.need(2 * cm)
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(COLOR_INK)
    c.drawString(state.LEFT, state.y, "2. Informações estruturadas")
    state.y -= 0.2 * cm
    c.setFont("Helvetica", 9)
    c.setFillColor(COLOR_INK_MUTED)
    c.drawString(state.LEFT, state.y - 0.35 * cm,
                 "Campos em verde já estão no OCG. Campos em amarelo precisam ser preenchidos por você.")
    state.y -= 0.6 * cm
    _hr(state)

    for s_idx, section in enumerate(sections, start=1):
        section_name = section.get("section") or f"Seção {s_idx}"
        fields = section.get("fields") or []
        state.need(1.5 * cm + 1.2 * cm * len(fields))
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(COLOR_INK)
        c.drawString(state.LEFT, state.y, f"2.{s_idx}. {section_name}")
        state.y -= 0.5 * cm

        for f in fields:
            fname = f.get("name") or "campo"
            from_ocg = f.get("from_ocg")
            hint = f.get("hint") or ""
            _draw_field_row(state, module=module, field_name=fname,
                             from_ocg=from_ocg, hint=hint, section_idx=s_idx)
            state.y -= 0.3 * cm


def _draw_field_row(
    state: _LayoutState, *, module: ModuleCandidate, field_name: str,
    from_ocg: str | None, hint: str, section_idx: int,
):
    c = state.canvas
    label_x = state.LEFT
    # ratio label/valor — 35% / 65%
    label_w = state.content_width * 0.32
    value_x = label_x + label_w + 0.3 * cm
    value_w = state.content_width - label_w - 0.3 * cm

    # Label (nome do campo)
    c.setFont("Helvetica", 10)
    c.setFillColor(COLOR_INK)
    c.drawString(label_x, state.y, _truncate(field_name, 40) + ":")

    if from_ocg:
        # Já preenchido pelo OCG — mostra valor em verde, sem AcroForm field
        c.setFillColor(COLOR_OCG_VALUE)
        c.setFont("Helvetica-Bold", 9.5)
        used = _draw_wrapped(c, _truncate(from_ocg, 200),
                              x=value_x, y=state.y,
                              max_width=value_w, font="Helvetica-Bold", size=9.5)
        state.y -= max(used, 0.3 * cm)
        if hint:
            c.setFont("Helvetica-Oblique", 7.5)
            c.setFillColor(COLOR_INK_MUTED)
            c.drawString(value_x, state.y - 0.05 * cm, _truncate(hint, 100))
            state.y -= 0.3 * cm
    else:
        # Lacuna — campo AcroForm editável amarelo
        field_h = 0.55 * cm
        c.acroForm.textfield(
            name=_safe_field_name(module.id, section_idx, field_name),
            tooltip=hint or f"Preencha {field_name}",
            x=value_x, y=state.y - 0.15 * cm,
            width=value_w, height=field_h,
            borderStyle="solid", borderWidth=0.7,
            borderColor=COLOR_GAP_BORDER, fillColor=COLOR_GAP_BG,
            textColor=COLOR_INK, fontName="Helvetica", fontSize=9.5,
            value="",
        )
        state.y -= 0.6 * cm
        if hint:
            c.setFont("Helvetica-Oblique", 7.5)
            c.setFillColor(COLOR_INK_MUTED)
            c.drawString(value_x, state.y, _truncate(hint, 100))
            state.y -= 0.3 * cm


def _draw_free_text(state: _LayoutState, module: ModuleCandidate):
    """Sempre oferece um campo livre adicional pra GP comentar."""
    c = state.canvas
    state.y -= 0.6 * cm
    state.need(4 * cm)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(COLOR_INK)
    c.drawString(state.LEFT, state.y, "3. Notas adicionais (opcional)")
    state.y -= 0.5 * cm

    c.setFont("Helvetica", 9)
    c.setFillColor(COLOR_INK_MUTED)
    c.drawString(state.LEFT, state.y,
                 "Use este espaço pra qualquer informação adicional que julgue relevante.")
    state.y -= 0.4 * cm

    field_h = 3 * cm
    c.acroForm.textfield(
        name=_safe_field_name(module.id, section_idx=99, field_name="notas_livres"),
        tooltip="Notas livres do GP",
        x=state.LEFT, y=state.y - field_h,
        width=state.content_width, height=field_h,
        borderStyle="solid", borderWidth=0.7,
        borderColor=COLOR_GAP_BORDER, fillColor=COLOR_GAP_BG,
        textColor=COLOR_INK, fontName="Helvetica", fontSize=10,
        value="",
        fieldFlags="multiline",
    )
    state.y -= field_h + 0.3 * cm


def _draw_footer(state: _LayoutState, module: ModuleCandidate):
    """Rodapé com module_id visível em texto pequeno + instrução de upload."""
    c = state.canvas
    c.saveState()
    c.setFillColor(COLOR_INK_MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(2 * cm, 1.2 * cm,
                 f"GCA — gca-module-id={module.id}")
    c.drawRightString(state.width - 2 * cm, 1.2 * cm,
                      "Após preencher, faça upload na aba Ingestão deste projeto.")
    c.restoreState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hr(state: _LayoutState):
    c = state.canvas
    c.setStrokeColor(COLOR_SECTION_RULE)
    c.setLineWidth(0.4)
    c.line(state.LEFT, state.y, state.right, state.y)
    state.y -= 0.25 * cm


def _draw_wrapped(canvas, text, *, x, y, max_width, font, size, leading=None) -> float:
    """Desenha texto com word-wrap simples. Retorna altura consumida."""
    if not text:
        return 0
    leading = leading or (size * 1.25)
    canvas.setFont(font, size)
    words = text.split()
    line = ""
    cy = y
    used = 0.0
    for w in words:
        candidate = (line + " " + w).strip()
        if canvas.stringWidth(candidate, font, size) <= max_width:
            line = candidate
        else:
            if line:
                canvas.drawString(x, cy, line)
                cy -= leading
                used += leading
            line = w
    if line:
        canvas.drawString(x, cy, line)
        used += leading
    return used


def _truncate(text: str, n: int) -> str:
    if not text:
        return ""
    text = str(text)
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _safe_field_name(module_id: UUID, section_idx: int, field_name: str) -> str:
    """AcroForm field names devem ser ASCII safe (sem espaços/acentos)."""
    import re
    base = re.sub(r"[^A-Za-z0-9_]", "_", str(field_name).strip().lower())
    return f"f_{section_idx}_{base}"[:60]
