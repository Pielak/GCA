"""MVP 24 Fase 24.1 — Gera PDF editável do questionário técnico retroativo.

Agrupa `GatekeeperItem` pendentes em 5 seções canônicas e produz um
AcroForm navegável:

  governance    — GP/Tech Lead (decisões, stakeholders, priorização)
  architecture  — padrões, camadas, dependências
  capacity      — performance, throughput, disponibilidade
  security      — auth, CWE, dados sensíveis, vault
  legal         — LGPD/GDPR/compliance setorial

IDs canônicos dos form fields: `Q_<item.id>` (UUID do GatekeeperItem),
checkboxes `Q_<item.id>__cb_<idx>`, complementos `Q__COMPLEMENTS`. O
parser da Fase 24.2 rejeita PDF que não tenha pelo menos um campo com
esse padrão — contrato duro.

Shape de decisão (`decide_input_shape`):
  - `item_data.options` é list de 2 itens → radio (`single`)
  - `item_data.options` é list com 3+ itens → checkbox grid (`multi`)
  - `item_data.suggestions` é list → checkbox grid + "Outros" texto (`multi`)
  - Senão → textfield livre (`text`)

Sempre há `Q__COMPLEMENTS` (textarea multi-linha) no fim — ele sozinho
vira um `IngestedDocument` separado processado pelo Arguidor como
texto livre.
"""
from __future__ import annotations

import io
import json
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional
from uuid import UUID


def _normalize(text: str) -> str:
    """Remove acentos e lowercases — pra keyword matching robusto em PT-BR."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import GatekeeperItem, Project


# ─── Seções canônicas ─────────────────────────────────────────────────


SectionKey = Literal["governance", "architecture", "capacity", "security", "legal"]
CANONICAL_SECTIONS: tuple[SectionKey, ...] = (
    "governance", "architecture", "capacity", "security", "legal",
)

SECTION_LABELS: dict[SectionKey, str] = {
    "governance":   "Governança (GP / Tech Lead)",
    "architecture": "Arquitetura e Design",
    "capacity":     "Capacity / Performance",
    "security":     "Segurança",
    "legal":        "Compliance Legal",
}

SECTION_DESCRIPTIONS: dict[SectionKey, str] = {
    "governance":   "Decisões de governança, stakeholders e priorização que dependem do GP ou Tech Lead.",
    "architecture": "Padrões arquiteturais, camadas, dependências e modelo de dados.",
    "capacity":     "Latência, throughput, escala, disponibilidade e recuperação.",
    "security":     "Autenticação, autorização, proteções CWE, vault, dados sensíveis.",
    "legal":        "LGPD, GDPR, compliance setorial e jurisdição.",
}


# Keywords pra classificação de items não-RNF.
_KW_LEGAL = (
    "lgpd", "gdpr", "hipaa", "sox", "pci", "compliance", "regulat",
    "juridic", "legal", "privacy", "consentimento", "dados pessoais",
)
_KW_SECURITY = (
    "cwe", "vault", "credenc", "secret", "xss", "csrf", "injection",
    "sql injection", "auth", "mfa", "jwt", "oauth", "encrypt", "hash",
    "segredo", "segurança", "security",
)
_KW_CAPACITY = (
    "latenc", "throughput", "uptime", "rpo", "rto", "rate limit",
    "performance", "escala", "scale", "capacit", "disponib",
    "observabil", "métric", "metric", "slo", "sla",
)
_KW_ARCH = (
    "arquitet", "architecture", "design", "padrão", "pattern",
    "camada", "layer", "dependênc", "depend", "modelo de dados",
    "data model", "microserv", "monólito", "hexagon",
)


@dataclass(frozen=True)
class QuestionnaireItem:
    """View canônica de um item pronto pro PDF."""
    id: str                    # UUID do GatekeeperItem (string)
    code: str                  # item_id_in_analysis (G001, RNF-P-001, etc)
    item_type: str             # gap, show_stopper, poor_definition, improvement
    question: str              # pergunta em PT-BR
    section: SectionKey
    input_type: Literal["text", "single", "multi"]
    options: tuple[str, ...] = ()
    hint: str = ""             # severidade, pilar, etc
    offers_count: int = 0      # Fase 24.3 — quantas vezes apareceu no PDF
    skip_count: int = 0        # Fase 24.3 — quantas vezes foi ignorado

    @property
    def needs_outros(self) -> bool:
        """Múltipla escolha com sugestões → oferece campo Outros."""
        return self.input_type == "multi" and bool(self.options)


@dataclass(frozen=True)
class SectionPayload:
    section: SectionKey
    items: tuple[QuestionnaireItem, ...]

    @property
    def is_empty(self) -> bool:
        return not self.items


# ─── Classificação + agrupamento ──────────────────────────────────────


def classify_item(code: str, data: dict[str, Any]) -> SectionKey:
    """Mapeia GatekeeperItem → seção canônica.

    Regras (ordem):
      1. RNF-S-* → security
      2. RNF-C-* → legal
      3. RNF-P-*, RNF-A-* → capacity
      4. data.rnf_category / data.category match
      5. data.pillar match (P2→legal, P4→capacity, P5/P6→architecture, P7→security, P1→governance)
      6. keyword match em data.text / data.description / data.question
      7. fallback → governance
    """
    code_upper = (code or "").upper()
    if code_upper.startswith("RNF-S"):
        return "security"
    if code_upper.startswith("RNF-C"):
        return "legal"
    if code_upper.startswith(("RNF-P", "RNF-A")):
        return "capacity"

    # Check rnf_category (from rnf_arguider_service)
    rnf_category = str(data.get("rnf_category", "")).lower().replace(" ", "")
    if rnf_category in ("security", "compliance"):
        return "security" if rnf_category == "security" else "legal"
    if rnf_category in ("performance", "availability"):
        return "capacity"

    # Check generic category (from other sources)
    category = str(data.get("category", "")).lower().replace(" ", "")
    if category == "compliance" or "compliance" in category:
        return "legal"
    if category == "security" or "security" in category:
        return "security"

    pillar = str(data.get("pillar", "")).upper().replace(" ", "")
    if pillar in ("P2", "P2_COMPLIANCE", "REGRAS", "COMPLIANCE"):
        return "legal"
    if pillar in ("P4", "P4_NFR", "NFR", "RNF"):
        return "capacity"
    if pillar in ("P5", "P5_ARCHITECTURE", "P6", "P6_DATA", "ARCHITECTURE", "DATA"):
        return "architecture"
    if pillar in ("P7", "P7_SECURITY", "SECURITY"):
        return "security"
    if pillar in ("P1", "P1_BUSINESS", "BUSINESS"):
        return "governance"

    haystack = _normalize(" ".join(
        str(data.get(k, "")) for k in (
            "text", "description", "question", "title", "finding", "label",
        )
    ))
    if any(kw in haystack for kw in _KW_LEGAL):
        return "legal"
    if any(kw in haystack for kw in _KW_SECURITY):
        return "security"
    if any(kw in haystack for kw in _KW_CAPACITY):
        return "capacity"
    if any(kw in haystack for kw in _KW_ARCH):
        return "architecture"

    return "governance"


def decide_input_shape(data: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Retorna (input_type, options) canônicos.

    Ordem:
      1. data.options com 2 itens → ("single", (...))
      2. data.options com 3+ itens → ("multi", (...))
      3. data.suggestions (lista) → ("multi", (...))
      4. default → ("text", ())

    Qualquer valor não-lista ou vazio é ignorado silenciosamente.
    """
    options = data.get("options")
    if isinstance(options, list) and options:
        clean = tuple(str(o) for o in options if str(o).strip())
        if len(clean) == 2:
            return ("single", clean)
        if len(clean) >= 3:
            return ("multi", clean)

    suggestions = data.get("suggestions")
    if isinstance(suggestions, list) and suggestions:
        clean = tuple(str(s) for s in suggestions if str(s).strip())
        if clean:
            return ("multi", clean)

    return ("text", ())


def _item_question(code: str, data: dict[str, Any]) -> str:
    """Pergunta canônica em PT-BR. Tenta data.question, depois text/description/title."""
    for k in ("question", "text", "description", "title", "finding", "label"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return f"Item {code}: aguardando esclarecimento do GP."


def _item_hint(data: dict[str, Any]) -> str:
    bits = []
    pillar = data.get("pillar")
    severity = data.get("severity") or data.get("priority")
    if pillar:
        bits.append(f"pilar {pillar}")
    if severity:
        bits.append(f"severidade {severity}")
    return " · ".join(bits)


async def group_pending_items(
    db: AsyncSession, project_id: UUID,
) -> dict[SectionKey, list[QuestionnaireItem]]:
    """Carrega GatekeeperItem pending do projeto e agrupa por seção.

    Retorna dict com TODAS as 5 seções canônicas (mesmo vazias).
    """
    rows = (await db.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project_id,
            GatekeeperItem.status == "pending",
        )
    )).scalars().all()

    buckets: dict[SectionKey, list[QuestionnaireItem]] = {
        s: [] for s in CANONICAL_SECTIONS
    }

    for row in rows:
        try:
            data = json.loads(row.item_data) if row.item_data else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}

        code = row.item_id_in_analysis or ""
        section = classify_item(code, data)
        input_type, options = decide_input_shape(data)
        offers = int(data.get("offers_count") or 0)
        skips = int(data.get("skip_count") or 0)
        item = QuestionnaireItem(
            id=str(row.id),
            code=code,
            item_type=row.item_type or "gap",
            question=_item_question(code, data),
            section=section,
            input_type=input_type,  # type: ignore[arg-type]
            options=options,
            hint=_item_hint(data),
            offers_count=offers,
            skip_count=skips,
        )
        buckets[section].append(item)

    # Fase 24.3 — items mais "esquecidos" (maior skip_count, depois
    # offers_count) ficam no topo. Desempate por código canônico pra
    # estabilidade.
    for section_key in buckets:
        buckets[section_key].sort(
            key=lambda q: (-q.skip_count, -q.offers_count, q.code),
        )

    return buckets


async def bump_offers_count(
    db: AsyncSession, item_ids: Iterable[str],
) -> None:
    """Incrementa `item_data.offers_count` em cada item dado.

    Chamado por `generate_section_pdf` logo após gerar o PDF — fecha o
    ciclo "emiti round, registrei o round".
    """
    from uuid import UUID as _UUID
    for raw in item_ids:
        try:
            uid = _UUID(str(raw))
        except (ValueError, TypeError):
            continue
        item = await db.get(GatekeeperItem, uid)
        if item is None:
            continue
        try:
            data = json.loads(item.item_data) if item.item_data else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["offers_count"] = int(data.get("offers_count") or 0) + 1
        item.item_data = json.dumps(data, ensure_ascii=False)
        db.add(item)
    await db.flush()


# ─── Geração do PDF ───────────────────────────────────────────────────


VIOLET = colors.HexColor("#7C3AED")
VIOLET_LIGHT = colors.HexColor("#DDD6FE")
SLATE_DARK = colors.HexColor("#1E293B")
SLATE_MID = colors.HexColor("#64748B")
SLATE_BORDER = colors.HexColor("#CBD5E1")
FIELD_BG = colors.HexColor("#F8FAFC")
WHITE = colors.HexColor("#FFFFFF")

PAGE_W, PAGE_H = A4
ML = 2.0 * cm
MR = 2.0 * cm
MT = 2.0 * cm
MB = 2.5 * cm
USABLE_W = PAGE_W - ML - MR

CB_SIZE = 10
CB_GAP = 3
ROW_H = 16
FIELD_H = 18
Q_GAP = 14

# Prefixo canônico dos form fields — parser 24.2 exige esse padrão.
FIELD_PREFIX = "Q_"
COMPLEMENTS_FIELD = "Q__COMPLEMENTS"
OFFERED_IDS_FIELD = "Q__OFFERED_IDS"  # Fase 24.3 — metadata do round


def _cb_name(item_id: str, idx: int) -> str:
    return f"{FIELD_PREFIX}{item_id}__cb_{idx}"


def _outros_cb_name(item_id: str) -> str:
    return f"{FIELD_PREFIX}{item_id}__cb_outros"


def _outros_txt_name(item_id: str) -> str:
    return f"{FIELD_PREFIX}{item_id}__outros"


def _field_name(item_id: str) -> str:
    return f"{FIELD_PREFIX}{item_id}"


def _new_page(c: Canvas) -> float:
    c.showPage()
    return PAGE_H - MT


def _need_space(c: Canvas, y: float, needed: float) -> float:
    if y - needed < MB:
        return _new_page(c)
    return y


def generate_pdf(
    *,
    project_name: str,
    section: SectionKey,
    items: Iterable[QuestionnaireItem],
) -> bytes:
    """Gera PDF editável (AcroForm) da seção com os items dados.

    Seção vazia ainda produz PDF válido, com mensagem "nenhum gap pendente"
    e o campo Complementos — o GP pode usar o Complementos pra mandar
    qualquer coisa que achar relevante fora do roteiro.
    """
    items_list = list(items)
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(f"Questionário Técnico GCA — {project_name} / {SECTION_LABELS[section]}")
    c.setAuthor("GCA — Gestão de Codificação Assistida")
    c.setSubject(f"Seção canônica: {section}")
    form = c.acroForm
    y = PAGE_H - MT

    # Cabeçalho
    c.setFillColor(VIOLET)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(ML, y, "GCA")
    c.setFont("Helvetica", 9)
    c.setFillColor(SLATE_MID)
    c.drawString(ML + 46, y + 2, "Gestão de Codificação Assistida")
    y -= 24

    c.setFillColor(SLATE_DARK)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(ML, y, f"Questionário Técnico — {SECTION_LABELS[section]}")
    y -= 18

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(VIOLET)
    c.drawString(ML, y, project_name)
    y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(SLATE_MID)
    c.drawString(ML, y, SECTION_DESCRIPTIONS[section])
    y -= 14

    c.setStrokeColor(VIOLET)
    c.setLineWidth(1.2)
    c.line(ML, y, PAGE_W - MR, y)
    y -= 14

    # Instruções curtas
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(SLATE_DARK)
    c.drawString(ML, y, "COMO PREENCHER")
    y -= 11
    c.setFont("Helvetica", 7.5)
    c.setFillColor(SLATE_MID)
    for line in (
        "1. Abra em Adobe Reader, Foxit ou Preview; preencha os campos diretamente no PDF.",
        "2. Perguntas sem resposta ficam registradas como dívida informacional — podem reaparecer.",
        "3. Use o campo Complementos ao final para adicionar qualquer informação relevante.",
        "4. Salve e faça upload via Ingestão do projeto. A propagação para backlog/roadmap é automática.",
    ):
        c.drawString(ML, y, line)
        y -= 10
    y -= 6

    c.setStrokeColor(SLATE_BORDER)
    c.setLineWidth(0.4)
    c.line(ML, y, PAGE_W - MR, y)
    y -= 14

    if not items_list:
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColor(SLATE_MID)
        c.drawString(
            ML, y,
            "Nenhum item pendente nesta seção. Use o campo Complementos abaixo "
            "se quiser adicionar algo relevante.",
        )
        y -= 22

    for q in items_list:
        # Espaço estimado (conservador).
        if q.input_type == "text":
            needed = 28 + FIELD_H + Q_GAP
        elif q.input_type == "single":
            needed = 28 + FIELD_H + Q_GAP
        else:
            cols = 2
            rows = -(-len(q.options) // cols) + (1 if q.needs_outros else 0)
            needed = 28 + rows * ROW_H + (FIELD_H if q.needs_outros else 0) + Q_GAP + 6
        y = _need_space(c, y, needed)

        # Código + pergunta
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(VIOLET)
        c.drawString(ML, y, f"[{q.code}]")
        if q.hint:
            c.setFont("Helvetica", 7)
            c.setFillColor(SLATE_MID)
            c.drawString(ML + 80, y, q.hint)
        y -= 11

        c.setFont("Helvetica", 9)
        c.setFillColor(SLATE_DARK)
        # Quebra simples da pergunta em múltiplas linhas (split em ~100 chars).
        for chunk in _wrap_text(q.question, max_chars=110):
            c.drawString(ML, y, chunk)
            y -= 11
        y -= 2

        if q.input_type == "text":
            form.textfield(
                name=_field_name(q.id),
                x=ML, y=y - FIELD_H, width=USABLE_W, height=FIELD_H,
                fontSize=9,
                borderColor=SLATE_BORDER, fillColor=FIELD_BG,
                textColor=SLATE_DARK,
            )
            y -= FIELD_H + Q_GAP

        elif q.input_type == "single":
            form.choice(
                name=_field_name(q.id),
                x=ML, y=y - FIELD_H, width=min(USABLE_W, 300), height=FIELD_H,
                fontSize=9,
                options=["Selecione..."] + list(q.options),
                value="Selecione...",
                borderColor=SLATE_BORDER, fillColor=FIELD_BG,
                textColor=SLATE_DARK,
            )
            y -= FIELD_H + Q_GAP

        else:  # multi
            cols = 2
            col_w = USABLE_W / cols
            for idx, opt in enumerate(q.options):
                col = idx % cols
                row = idx // cols
                cx = ML + col * col_w
                cy = y - row * ROW_H
                if cy < MB + 40:
                    y = _new_page(c)
                    cy = y
                form.checkbox(
                    name=_cb_name(q.id, idx),
                    x=cx, y=cy - CB_SIZE,
                    size=CB_SIZE,
                    borderColor=SLATE_BORDER, fillColor=FIELD_BG,
                    buttonStyle="check", checked=False,
                )
                c.setFont("Helvetica", 8)
                c.setFillColor(SLATE_DARK)
                c.drawString(cx + CB_SIZE + CB_GAP, cy - 8, str(opt)[:45])
            rows_used = -(-len(q.options) // cols)
            y -= rows_used * ROW_H + 4

            if q.needs_outros:
                y = _need_space(c, y, ROW_H + FIELD_H + 8)
                form.checkbox(
                    name=_outros_cb_name(q.id),
                    x=ML, y=y - CB_SIZE,
                    size=CB_SIZE,
                    borderColor=colors.HexColor("#F59E0B"),
                    fillColor=colors.HexColor("#FFFBEB"),
                    buttonStyle="check", checked=False,
                )
                c.setFont("Helvetica-Oblique", 8)
                c.setFillColor(colors.HexColor("#D97706"))
                c.drawString(ML + CB_SIZE + CB_GAP, y - 8, "Outros (descreva abaixo):")
                y -= ROW_H
                form.textfield(
                    name=_outros_txt_name(q.id),
                    x=ML, y=y - FIELD_H, width=USABLE_W, height=FIELD_H,
                    fontSize=8,
                    borderColor=colors.HexColor("#FDE68A"),
                    fillColor=colors.HexColor("#FFFBEB"),
                    textColor=SLATE_DARK,
                )
                y -= FIELD_H
            y -= Q_GAP

    # Campo Complementos (sempre presente)
    y = _need_space(c, y, 18 + FIELD_H * 6 + 12)
    y -= 10
    c.setStrokeColor(VIOLET)
    c.setLineWidth(0.8)
    c.line(ML, y, PAGE_W - MR, y)
    y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(VIOLET)
    c.drawString(ML, y, "Complementos")
    y -= 12
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(SLATE_MID)
    c.drawString(
        ML, y,
        "Informações adicionais que você considere relevantes — entram no "
        "Arguidor como texto livre e propagam para o OCG.",
    )
    y -= 14

    form.textfield(
        name=COMPLEMENTS_FIELD,
        x=ML, y=y - FIELD_H * 6, width=USABLE_W, height=FIELD_H * 6,
        fontSize=9,
        borderColor=SLATE_BORDER, fillColor=FIELD_BG,
        textColor=SLATE_DARK,
        fieldFlags="multiline",
    )
    y -= FIELD_H * 6 + 8

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(SLATE_MID)
    c.drawString(
        ML, y,
        f"GCA · seção {section} · {len(items_list)} itens · upload via Ingestão do projeto.",
    )

    # Fase 24.3 — field oculto com CSV dos IDs oferecidos neste round.
    # O parser usa pra calcular `skipped = offered - answered` e promover
    # dívida informacional no backlog quando GP ignora perguntas repetidas.
    # Campo em coordenada fora da área visível + read-only via fieldFlags.
    offered_csv = ",".join(q.id for q in items_list)
    # Posiciona fora do canvas visível (reportlab não expõe flag `hidden`);
    # o visualizador nem renderiza, mas o parser ainda lê via AcroForm.
    form.textfield(
        name=OFFERED_IDS_FIELD,
        x=-1000, y=-1000, width=1, height=1,
        fontSize=1, value=offered_csv,
        borderColor=WHITE, fillColor=WHITE, textColor=WHITE,
        fieldFlags="readOnly",
    )

    c.save()
    return buf.getvalue()


def _wrap_text(text: str, *, max_chars: int) -> list[str]:
    """Quebra por palavras preservando até `max_chars` por linha."""
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + 1 + len(w) <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ─── Fachada (consumida pelo router) ──────────────────────────────────


async def generate_section_pdf(
    db: AsyncSession, project_id: UUID, section: SectionKey,
) -> Optional[bytes]:
    """Gera PDF da seção canônica dada. `None` se o projeto não existe.

    Fase 24.3 — incrementa `offers_count` em cada item oferecido. A
    contagem persiste no `GatekeeperItem.item_data` e é usada pelo
    aplicador pra calcular dívida quando o GP não responde.
    """
    project = await db.get(Project, project_id)
    if project is None:
        return None

    buckets = await group_pending_items(db, project_id)
    items = buckets.get(section, [])
    pdf_bytes = generate_pdf(
        project_name=project.name or "(sem nome)",
        section=section,
        items=items,
    )
    if items:
        await bump_offers_count(db, [q.id for q in items])
        await db.commit()
    return pdf_bytes
