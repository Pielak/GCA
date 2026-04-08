"""
Gerador do documento de Análise de Requisitos - GCA 08/04/2026
Requisitos Funcionais, Não Funcionais, Técnicos, Regras de Negócio,
Telas, Diagramas de Fluxo, de Sequência e Glossário.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, Image
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Line, Rect, String, Circle, Polygon
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from datetime import datetime
import os

# ============================================================================
# CORES DO TEMA
# ============================================================================
VIOLET = HexColor("#7c3aed")
VIOLET_DARK = HexColor("#5b21b6")
VIOLET_LIGHT = HexColor("#ede9fe")
EMERALD = HexColor("#10b981")
EMERALD_LIGHT = HexColor("#d1fae5")
DARK_BG = HexColor("#1e1b2e")
DARK_100 = HexColor("#2a2640")
GRAY_TEXT = HexColor("#6b7280")
GRAY_LIGHT = HexColor("#f3f4f6")
RED = HexColor("#ef4444")
AMBER = HexColor("#f59e0b")
BLUE = HexColor("#3b82f6")

OUTPUT_PATH = "/home/luiz/GCA/GCA_08_04.pdf"

# ============================================================================
# ESTILOS
# ============================================================================
styles = getSampleStyleSheet()

style_title = ParagraphStyle(
    "DocTitle", parent=styles["Title"],
    fontSize=28, textColor=VIOLET_DARK, spaceAfter=6,
    fontName="Helvetica-Bold", alignment=TA_CENTER,
)
style_subtitle = ParagraphStyle(
    "DocSubtitle", parent=styles["Normal"],
    fontSize=14, textColor=GRAY_TEXT, alignment=TA_CENTER,
    spaceAfter=20, fontName="Helvetica",
)
style_h1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontSize=20, textColor=VIOLET_DARK, spaceBefore=20, spaceAfter=10,
    fontName="Helvetica-Bold", borderWidth=0, borderPadding=0,
)
style_h2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontSize=15, textColor=VIOLET, spaceBefore=14, spaceAfter=8,
    fontName="Helvetica-Bold",
)
style_h3 = ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontSize=12, textColor=DARK_BG, spaceBefore=10, spaceAfter=6,
    fontName="Helvetica-Bold",
)
style_body = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=10, textColor=DARK_BG, alignment=TA_JUSTIFY,
    spaceAfter=6, leading=14, fontName="Helvetica",
)
style_bullet = ParagraphStyle(
    "Bullet", parent=style_body,
    leftIndent=20, bulletIndent=10, spaceAfter=3,
)
style_code = ParagraphStyle(
    "Code", parent=styles["Normal"],
    fontSize=8.5, fontName="Courier", textColor=DARK_BG,
    backColor=GRAY_LIGHT, leftIndent=10, rightIndent=10,
    spaceBefore=4, spaceAfter=4, leading=11,
    borderWidth=0.5, borderColor=HexColor("#d1d5db"),
    borderPadding=6,
)
style_table_header = ParagraphStyle(
    "TH", parent=styles["Normal"],
    fontSize=9, fontName="Helvetica-Bold", textColor=white,
    alignment=TA_CENTER,
)
style_table_cell = ParagraphStyle(
    "TD", parent=styles["Normal"],
    fontSize=8.5, fontName="Helvetica", textColor=DARK_BG,
    leading=11,
)
style_table_cell_center = ParagraphStyle(
    "TDC", parent=style_table_cell, alignment=TA_CENTER,
)
style_note = ParagraphStyle(
    "Note", parent=style_body,
    fontSize=9, textColor=GRAY_TEXT, leftIndent=15,
    borderLeftWidth=3, borderLeftColor=VIOLET_LIGHT,
    borderPadding=8, backColor=VIOLET_LIGHT,
)


# ============================================================================
# HELPERS
# ============================================================================
def h1(text): return Paragraph(text, style_h1)
def h2(text): return Paragraph(text, style_h2)
def h3(text): return Paragraph(text, style_h3)
def p(text): return Paragraph(text, style_body)
def bullet(text): return Paragraph(f"&bull; {text}", style_bullet)
def code(text): return Paragraph(text.replace("\n", "<br/>"), style_code)
def note(text): return Paragraph(text, style_note)
def spacer(h=0.3): return Spacer(1, h * cm)
def hr(): return HRFlowable(width="100%", thickness=1, color=VIOLET_LIGHT, spaceAfter=8, spaceBefore=8)


def make_table(headers, rows, col_widths=None):
    """Cria tabela estilizada."""
    header_cells = [Paragraph(h, style_table_header) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([
            Paragraph(str(cell), style_table_cell if i == 0 else style_table_cell_center)
            if not isinstance(cell, Paragraph) else cell
            for i, cell in enumerate(row)
        ])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VIOLET),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (-1, -1), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, GRAY_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


class DiagramBox(Flowable):
    """Diagrama de fluxo como flowable."""
    def __init__(self, width, height, draw_func):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.draw_func = draw_func

    def draw(self):
        self.draw_func(self.canv, self.width, self.height)


def draw_rounded_rect(c, x, y, w, h, color, text, text_color=white, r=5, font_size=8):
    """Retangulo arredondado com texto."""
    c.setFillColor(color)
    c.roundRect(x, y, w, h, r, fill=1, stroke=0)
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", font_size)
    lines = text.split("\n")
    line_height = font_size + 2
    total_h = len(lines) * line_height
    start_y = y + h / 2 + total_h / 2 - font_size
    for i, line in enumerate(lines):
        c.drawCentredString(x + w / 2, start_y - i * line_height, line)


def draw_arrow(c, x1, y1, x2, y2, color=GRAY_TEXT):
    """Seta simples."""
    c.setStrokeColor(color)
    c.setLineWidth(1.5)
    c.line(x1, y1, x2, y2)
    # Ponta da seta
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    arrow_len = 6
    c.line(x2, y2, x2 - arrow_len * math.cos(angle - 0.4), y2 - arrow_len * math.sin(angle - 0.4))
    c.line(x2, y2, x2 - arrow_len * math.cos(angle + 0.4), y2 - arrow_len * math.sin(angle + 0.4))


def draw_diamond(c, cx, cy, size, color, text, text_color=white, font_size=7):
    """Losango de decisão."""
    c.setFillColor(color)
    path = c.beginPath()
    path.moveTo(cx, cy + size)
    path.lineTo(cx + size, cy)
    path.lineTo(cx, cy - size)
    path.lineTo(cx - size, cy)
    path.close()
    c.drawPath(path, fill=1, stroke=0)
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(cx, cy - 3, text)


# ============================================================================
# HEADER/FOOTER
# ============================================================================
LOGO_PATH_HEADER = "/home/luiz/GCA/logogca.png"

def header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    # Header
    canvas_obj.setFillColor(VIOLET)
    canvas_obj.rect(0, A4[1] - 25, A4[0], 25, fill=1, stroke=0)
    if os.path.exists(LOGO_PATH_HEADER):
        canvas_obj.drawImage(LOGO_PATH_HEADER, 0.8 * cm, A4[1] - 22, width=40, height=40 * 784 / 1168, mask='auto')
    canvas_obj.setFillColor(white)
    canvas_obj.setFont("Helvetica-Bold", 8)
    canvas_obj.drawString(2.5 * cm, A4[1] - 17, "GCA - Gestão de Codificação Assistida")
    canvas_obj.drawRightString(A4[0] - 1.5 * cm, A4[1] - 17, "Análise de Requisitos v1.0")
    # Footer
    canvas_obj.setFillColor(GRAY_TEXT)
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.drawString(1.5 * cm, 1 * cm, f"Documento gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas_obj.drawRightString(A4[0] - 1.5 * cm, 1 * cm, f"Pagina {doc.page}")
    canvas_obj.setStrokeColor(VIOLET_LIGHT)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(1.5 * cm, 1.3 * cm, A4[0] - 1.5 * cm, 1.3 * cm)
    canvas_obj.restoreState()


# ============================================================================
# CONTEUDO DO DOCUMENTO
# ============================================================================
def build_document():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    story = []
    W = doc.width

    # ========================================================================
    # CAPA
    # ========================================================================
    LOGO_PATH = "/home/luiz/GCA/logogca.png"
    story.append(Spacer(1, 2.5 * cm))
    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=8 * cm, height=8 * cm * 784 / 1168, hAlign="CENTER")
        story.append(logo)
        story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("Gestão de Codificação Assistida", ParagraphStyle(
        "CoverSub", fontSize=18, textColor=VIOLET,
        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=20,
    )))
    story.append(hr())
    story.append(Paragraph("Documento de Análise de Requisitos", style_title))
    story.append(Paragraph(
        "Requisitos Funcionais | Não Funcionais | Técnicos | Regras de Negócio<br/>"
        "Telas | Diagramas de Fluxo | Diagramas de Sequência | Glossário",
        style_subtitle
    ))
    story.append(Spacer(1, 2 * cm))

    meta_data = [
        ["Projeto", "GCA - Gestão de Codificação Assistida"],
        ["Versão", "1.0"],
        ["Data", "08/04/2026"],
        ["Autor", "Luiz Carlos Pielak"],
        ["Responsável", "Luiz Carlos Pielak"],
        ["Status", "Em Desenvolvimento"],
    ]
    meta_table = Table(meta_data, colWidths=[4 * cm, 10 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), VIOLET),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK_BG),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, VIOLET_LIGHT),
    ]))
    story.append(meta_table)
    story.append(PageBreak())

    # ========================================================================
    # SUMARIO
    # ========================================================================
    story.append(h1("Sumário"))
    story.append(hr())
    toc_items = [
        ("1", "Introdução e Visão Geral"),
        ("2", "Requisitos Funcionais (RF)"),
        ("3", "Requisitos Não Funcionais (RNF)"),
        ("4", "Requisitos Técnicos (RT)"),
        ("5", "Regras de Negócio (RN)"),
        ("6", "Mapa de Telas e Componentes"),
        ("7", "Diagramas de Fluxo"),
        ("8", "Diagramas de Sequência"),
        ("9", "Endpoints da API"),
        ("10", "Modelos de Dados"),
        ("11", "Pipeline de Verificação Tecnológica"),
        ("12", "Arquitetura de Agentes IA"),
        ("13", "Infraestrutura e Deploy"),
        ("14", "Glossário"),
    ]
    for num, title in toc_items:
        story.append(Paragraph(
            f"<b>{num}.</b> {title}",
            ParagraphStyle("TOC", parent=style_body, fontSize=11, spaceAfter=4, leftIndent=10)
        ))
    story.append(PageBreak())

    # ========================================================================
    # 1. INTRODUCAO
    # ========================================================================
    story.append(h1("1. Introdução e Visão Geral"))
    story.append(hr())
    story.append(p(
        "O <b>GCA (Gestão de Codificação Assistida)</b> e um sistema end-to-end para análise, "
        "avaliação e geração de código de projetos de software. Utiliza inteligência artificial "
        "(Claude/Anthropic) para avaliar requisitos técnicos atraves de 7 pilares de qualidade "
        "e gerar artefatos de código alinhados com as melhores práticas."
    ))
    story.append(spacer())
    story.append(h2("1.1 Objetivo"))
    story.append(p(
        "Transformar respostas de um questionário técnico de 54 campos em um <b>Objeto Contexto "
        "Global (OCG)</b> que serve como base para avaliação de artefatos e geração de código. "
        "O sistema garante consistência, segurança e qualidade em cada etapa."
    ))
    story.append(spacer())
    story.append(h2("1.2 Os 7 Pilares de Qualidade"))
    pillars = [
        ("P1", "Business", "ROI, stakeholders, timeline, budget, KPIs"),
        ("P2", "Rules/Compliance", "LGPD/GDPR, residência de dados, auditoria, privacidade"),
        ("P3", "Features/Scope", "MVP, gestão de escopo, integrações, risco de scope creep"),
        ("P4", "Non-Functional", "Performance, escalabilidade, confiabilidade, observabilidade"),
        ("P5", "Architecture", "Stack, patterns, escolhas tecnológicas"),
        ("P6", "Data", "Banco de dados, schema, estrategia de persistência"),
        ("P7", "Security", "Controles de segurança, testes, gestão de vulnerabilidades"),
    ]
    story.append(make_table(
        ["Pilar", "Nome", "Criterios"],
        pillars,
        col_widths=[1.5 * cm, 4 * cm, W - 5.5 * cm]
    ))
    story.append(spacer())
    story.append(h2("1.3 Fluxo Principal"))
    story.append(p(
        "Questionário (54Q) &rarr; Verificação Tecnológica (8 fases) &rarr; Agentes IA (8 agentes) "
        "&rarr; OCG &rarr; Avaliação de Artefatos &rarr; Geração de Código"
    ))
    story.append(PageBreak())

    # ========================================================================
    # 2. REQUISITOS FUNCIONAIS
    # ========================================================================
    story.append(h1("2. Requisitos Funcionais (RF)"))
    story.append(hr())

    rfs = [
        ("RF-001", "Sistema de Convite por Token", "Crítica",
         "Admin convida usuários via token temporário (2h TTL, max 3 tentativas). "
         "Usuário so e criado apos definir senha permanente. InvitationToken com hash de senha temporária."),
        ("RF-002", "Autenticação e Controle de Acesso", "Crítica",
         "Login com email/senha, JWT access+refresh tokens, first-access obrigatório, "
         "reset de senha via email, bootstrap do primeiro admin."),
        ("RF-003", "Questionário Técnico (54 campos)", "Crítica",
         "Formulário de 54 campos em 9 blocos (A.1-A.8 + A.12). Campos Q1-Q49 preenchidos pelo GP, "
         "Q50-Q54 preenchidos pela IA. 40+ enums de validação. Suporta formato numérico e nomeado."),
        ("RF-004", "Verificação Tecnológica Pré-OCG", "Crítica",
         "Pipeline de 8 fases com 50+ regras. Severidades: BLOCKER (impede OCG), CRITICAL, WARNING, INFO. "
         "Matrizes de compatibilidade linguagem/framework/banco/arquitetura."),
        ("RF-005", "Geração do OCG via Agentes IA", "Crítica",
         "8 agentes: Analyzer + 7 Pillar Specialists (paralelo) + Consolidator. "
         "Gera scores por pilar, recomendações de stack, status final. P7 < 70 = BLOCKING."),
        ("RF-006", "Criação de Projeto (Externo)", "Alta",
         "Link único por email com token de 5 dias. Formulário externo sem login. "
         "Timer de contagem regressiva. Salvar rascunho. Aviso ao sair sem salvar."),
        ("RF-007", "Aprovação/Rejeição de Projetos", "Alta",
         "Admin visualiza projetos pendentes, aprova (provisiona tenant) ou rejeita com motivo. "
         "Notificação por email ao GP."),
        ("RF-008", "Gestão de Usuários (Admin)", "Alta",
         "Listar todos usuários, bloquear/desbloquear, ativar/desativar (Zap icon), "
         "reset de senha. Admin nao pode desativar propria conta."),
        ("RF-009", "Dashboard Administrativo", "Média",
         "Métricas do sistema, resumo de projetos, atividade recente, saúde do sistema, "
         "alertas, log de auditoria."),
        ("RF-010", "Avaliação de Artefatos", "Alta",
         "Avaliação individual ou em lote contra 7 pilares. Scores 0-100 por pilar. "
         "P7 < 70 bloqueia geração de código. Histórico de avaliacoes."),
        ("RF-011", "Geração de Código", "Alta",
         "Geração de projeto completo ou por modulo. Suporte a 4 provedores LLM "
         "(Anthropic, OpenAI, Grok, DeepSeek). Histórico de geracoes."),
        ("RF-012", "Log de Auditoria Global", "Alta",
         "Registro de todos os eventos com actor, tipo, recurso, detalhes, hash encadeado "
         "para integridade. Visualização no painel admin."),
        ("RF-013", "Sistema de Tickets de Suporte", "Média",
         "Criacao de tickets com severidade, descrição do erro, comportamento errático. "
         "Respostas do admin, status tracking, SLA."),
        ("RF-014", "Notificações por Email", "Alta",
         "Convites, reset de senha, links de questionário, aprovação/rejeição de projeto, "
         "resultado de análise, alertas de sistema."),
        ("RF-015", "Integrações Webhook", "Média",
         "Teste de webhook, integração com n8n para análise enriquecida com IA, "
         "callbacks de resultado OCG."),
    ]
    for rf_id, name, priority, desc in rfs:
        story.append(h3(f"{rf_id}: {name}"))
        story.append(p(f"<b>Prioridade:</b> {priority}"))
        story.append(p(desc))
        story.append(spacer(0.2))

    story.append(PageBreak())

    # ========================================================================
    # 3. REQUISITOS NAO FUNCIONAIS
    # ========================================================================
    story.append(h1("3. Requisitos Não Funcionais (RNF)"))
    story.append(hr())

    rnfs = [
        ("RNF-001", "Performance", "Resposta da API < 500ms para operações CRUD. "
         "Análise de questionário < 5s (built-in) + análise IA assíncrona. "
         "Build frontend: 858KB JS, 2332 módulos."),
        ("RNF-002", "Segurança", "Senhas: min 10 chars, 1 maiuscula, 1 numero, 1 simbolo. "
         "JWT com refresh token. Tokens de convite com TTL (2h). Reset tokens com TTL (24h). "
         "Hash bcrypt. Proteção contra enumeração de email."),
        ("RNF-003", "Disponibilidade", "Docker containers com restart: unless-stopped. "
         "Systemd user service para auto-start no boot. Health checks em Postgres e Redis."),
        ("RNF-004", "Escalabilidade", "Arquitetura multi-tenant por projeto (schema isolado). "
         "Agentes IA executam em paralelo. Análise assíncrona via n8n."),
        ("RNF-005", "Auditabilidade", "Log global com hash encadeado (integridade). "
         "Registro de todos os eventos criticos: login, criação, alteracao, bloqueio."),
        ("RNF-006", "Usabilidade", "Interface em português-BR. Tailwind CSS consistente. "
         "Feedback visual (toasts, modais, timers). Dark theme. Responsivo."),
        ("RNF-007", "Manutenibilidade", "Separação backend (FastAPI) / frontend (React+Vite). "
         "Serviços desacoplados. 54/54 testes automatizados passando."),
        ("RNF-008", "Compatibilidade", "Node.js 20+, Python 3.11+, PostgreSQL 16, Redis 7. "
         "Docker Compose para orquestração."),
    ]
    for rnf_id, name, desc in rnfs:
        story.append(h3(f"{rnf_id}: {name}"))
        story.append(p(desc))
        story.append(spacer(0.2))

    story.append(PageBreak())

    # ========================================================================
    # 4. REQUISITOS TECNICOS
    # ========================================================================
    story.append(h1("4. Requisitos Técnicos (RT)"))
    story.append(hr())

    story.append(h2("4.1 Stack Tecnológico"))
    stack = [
        ("Backend", "Python 3.11+ / FastAPI", "API REST, async, SQLAlchemy 2.0"),
        ("Frontend", "React 18 + TypeScript + Vite", "SPA, Tailwind CSS, Zustand"),
        ("Banco de Dados", "PostgreSQL 16", "Multi-tenant, schemas isolados"),
        ("Cache", "Redis 7", "Sessions, filas, cache"),
        ("Automação", "n8n", "Workflows, webhooks, análise IA"),
        ("IA Principal", "Claude (Anthropic SDK)", "8 agentes especializados"),
        ("Containerização", "Docker + Docker Compose", "5 serviços orquestrados"),
        ("Proxy Reverso", "Cloudflare Tunnel", "HTTPS, DNS, proteção DDoS"),
    ]
    story.append(make_table(
        ["Camada", "Tecnologia", "Uso"],
        stack,
        col_widths=[3.5 * cm, 5.5 * cm, W - 9 * cm]
    ))
    story.append(spacer())

    story.append(h2("4.2 Provedores LLM Suportados"))
    llm = [
        ("Anthropic", "Claude 3/4", "Principal - Agentes OCG"),
        ("OpenAI", "GPT-4", "Alternativo"),
        ("Grok", "Grok-1", "Alternativo"),
        ("DeepSeek", "DeepSeek Coder", "Alternativo"),
    ]
    story.append(make_table(
        ["Provedor", "Modelo", "Uso"],
        llm,
        col_widths=[3.5 * cm, 4 * cm, W - 7.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("4.3 Portas e URLs"))
    ports = [
        ("Frontend", "5173", "gca.code-auditor.com.br"),
        ("Backend API", "8000", "api.code-auditor.com.br"),
        ("PostgreSQL", "5432", "localhost (interno)"),
        ("Redis", "6379", "localhost (interno)"),
        ("n8n", "5678", "n8n.code-auditor.com.br"),
    ]
    story.append(make_table(
        ["Serviço", "Porta", "URL Produção"],
        ports,
        col_widths=[3.5 * cm, 2.5 * cm, W - 6 * cm]
    ))

    story.append(PageBreak())

    # ========================================================================
    # 5. REGRAS DE NEGOCIO
    # ========================================================================
    story.append(h1("5. Regras de Negócio (RN)"))
    story.append(hr())

    rules = [
        ("RN-001", "Bootstrap Admin",
         "O primeiro usuário do sistema DEVE ser criado via /bootstrap-admin. "
         "Este endpoint so funciona quando nao existem usuários no banco."),
        ("RN-002", "Convite em 2 Etapas",
         "Step 1: Validar token + senha temporária. Step 2: Definir senha permanente. "
         "Usuário SO e criado no Step 2. Token expira em 2h, max 3 tentativas."),
        ("RN-003", "First Access Obrigatório",
         "Todo usuário convidado DEVE trocar a senha temporária no primeiro login. "
         "Frontend exibe FirstAccessModal bloqueante ate conclusao."),
        ("RN-004", "Admin Não se Auto-Desativa",
         "Um administrador NAO pode desativar sua propria conta. "
         "Proteção implementada no frontend e backend."),
        ("RN-005", "Questionário Pré-OCG",
         "Nenhum OCG pode ser gerado sem que o questionário passe pela verificação tecnológica. "
         "Findings com severidade BLOCKER impedem a geração."),
        ("RN-006", "Scoring de Pilares",
         "90-100: Excelente. 70-89: Bom, gaps menores. 50-69: Vago/incompleto. < 50: Gaps criticos. "
         "P7 (Security) < 70 = BLOQUEIO total da geração de código."),
        ("RN-007", "Token de Projeto Externo",
         "Links para questionário externo tem validade de 5 dias. "
         "Apos expirar: tela de expirado com notificação ao GP e Admin."),
        ("RN-008", "Rascunho com Detecção de Alterações",
         "Questionário detecta alterações nao salvas. Botao 'Sair' exibe warning se houver "
         "modificações pendentes. Salvamento manual via botao 'Salvar Rascunho'."),
        ("RN-009", "Roles e Permissões",
         "Admin: acesso total, ve todos projetos/usuários. GP: ve apenas seus projetos. "
         "Roles mistas permitidas (Admin + GP)."),
        ("RN-010", "Aprovação de Projeto",
         "Projeto enviado fica como 'Pendente'. Admin pode Aprovar (cria tenant) ou "
         "Rejeitar (com motivo). Email enviado ao GP em ambos os casos."),
        ("RN-011", "Auditoria com Hash Encadeado",
         "Cada registro de auditoria contem hash do registro anterior, "
         "garantindo integridade e deteccao de adulteração."),
        ("RN-012", "Compatibilidade de Stack",
         "Sistema valida automaticamente: linguagem vs framework, framework vs banco, "
         "frontend vs entregáveis, arquitetura vs modelo de execução. "
         "Combinacoes inválidas geram BLOCKER."),
        ("RN-013", "Análise Dupla",
         "Questionário passa por análise built-in (imediata, regras determinísticas) "
         "E análise IA via n8n (assíncrona, insights profundos). Ambas complementares."),
        ("RN-014", "Multi-Tenant por Schema",
         "Cada projeto aprovado ganha schema PostgreSQL isolado (proj_{slug}_*). "
         "Dados do projeto nunca se misturam entre tenants."),
        ("RN-015", "Proteção de Email",
         "Reset de senha retorna mensagem generica independente de o email existir ou nao. "
         "Previne enumeração de contas."),
    ]
    for rn_id, name, desc in rules:
        story.append(h3(f"{rn_id}: {name}"))
        story.append(p(desc))
        story.append(spacer(0.2))

    story.append(PageBreak())

    # ========================================================================
    # 6. MAPA DE TELAS
    # ========================================================================
    story.append(h1("6. Mapa de Telas e Componentes"))
    story.append(hr())

    story.append(h2("6.1 Telas de Autenticação"))
    auth_screens = [
        ("LoginPage", "/login", "Login com email/senha, botao 'Criar Novo Projeto GCA'"),
        ("AcceptInvitationPage", "/accept-invitation", "2 steps: validar token + definir senha permanente"),
        ("FirstAccessModal", "(modal)", "Troca obrigatoria de senha temporária no primeiro login"),
        ("ResetPasswordPage", "/reset-password", "Solicitar reset e confirmar nova senha via token"),
    ]
    story.append(make_table(
        ["Componente", "Rota", "Descrição"],
        auth_screens,
        col_widths=[4.5 * cm, 4 * cm, W - 8.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("6.2 Telas de Projeto"))
    proj_screens = [
        ("NovoProjetoPage", "/novo-projeto", "3 steps: identificação, questionário (54Q), enviado. Timer 5d."),
        ("ProjectListPage", "/projects", "Lista de projetos acessiveis ao usuário"),
        ("ProjectDashPage", "/projects/:id", "Dashboard do projeto com métricas e status"),
        ("ProjectDetailLayout", "/projects/:id/*", "Layout wrapper com sidebar de navegação"),
        ("QuestionnairePage", "/projects/:id/questionnaire", "Formulário técnico 54 campos em 8 blocos"),
        ("ProjectTeamPage", "/projects/:id/team", "Gestão de equipe do projeto"),
        ("GatekeeperPage", "/projects/:id/gatekeeper", "Avaliação de qualidade por pilares"),
        ("OCGPage", "/projects/:id/ocg", "Visualização do Objeto Contexto Global"),
        ("CodeGeneratorPage", "/projects/:id/codegen", "Interface de geração de código"),
        ("QAReadinessPage", "/projects/:id/qa", "Prontidão para QA"),
        ("IngestionPage", "/projects/:id/ingestion", "Ingestão de dados (placeholder)"),
        ("MergeEnginePage", "/projects/:id/merge", "Engine de merge (placeholder)"),
        ("ArguiderPage", "/projects/:id/arguider", "Guia de arquitetura (placeholder)"),
        ("LegacyPage", "/projects/:id/legacy", "Análise de legado (placeholder)"),
        ("LiveDocsPage", "/projects/:id/docs", "Documentação ao vivo (placeholder)"),
        ("RoadmapPage", "/projects/:id/roadmap", "Roadmap do projeto (placeholder)"),
    ]
    story.append(make_table(
        ["Componente", "Rota", "Descrição"],
        proj_screens,
        col_widths=[4.5 * cm, 5 * cm, W - 9.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("6.3 Telas Administrativas"))
    admin_screens = [
        ("AdminDashboardPage", "/admin", "Métricas, alertas, atividade recente, saúde do sistema"),
        ("AdminUsersPage", "/admin/users", "Gestão de usuários: listar, bloquear, desativar (Zap icon)"),
        ("AdminProjectsPage", "/admin/projects", "Projetos pendentes, aprovar/rejeitar"),
        ("AdminAuditPage", "/admin/audit", "Log de auditoria global com filtros"),
    ]
    story.append(make_table(
        ["Componente", "Rota", "Descrição"],
        admin_screens,
        col_widths=[4.5 * cm, 3.5 * cm, W - 8 * cm]
    ))
    story.append(spacer())

    story.append(h2("6.4 Telas do Sistema"))
    sys_screens = [
        ("DashboardPage", "/dashboard", "Dashboard geral com métricas e KPIs"),
        ("AlertsPage", "/alerts", "Alertas do sistema"),
        ("TicketsPage", "/tickets", "Tickets de suporte"),
        ("SecurityPage", "/security", "Configurações de segurança"),
        ("IntegrationsPage", "/integrations", "Integrações (Teams, Slack, Discord)"),
        ("SettingsPage", "/settings", "Configurações do sistema"),
    ]
    story.append(make_table(
        ["Componente", "Rota", "Descrição"],
        sys_screens,
        col_widths=[4.5 * cm, 3.5 * cm, W - 8 * cm]
    ))
    story.append(spacer())

    story.append(h2("6.5 Componentes Compartilhados"))
    shared = [
        ("AppLayout", "Layout principal com sidebar e header"),
        ("Sidebar", "Navegação lateral com menu contextual"),
        ("ErrorBoundary", "Captura de erros com fallback UI"),
        ("UI Components", "Card, Dialog, Form, Dropdown, Input, Button (shadcn/ui)"),
    ]
    story.append(make_table(
        ["Componente", "Descrição"],
        shared,
        col_widths=[4.5 * cm, W - 4.5 * cm]
    ))

    story.append(PageBreak())

    # ========================================================================
    # 7. DIAGRAMAS DE FLUXO (TD - Top-Down, cabe na A4)
    # ========================================================================
    story.append(h1("7. Diagramas de Fluxo"))
    story.append(hr())
    story.append(p("Todos os diagramas utilizam orientação <b>Top-Down (TD)</b> para melhor leitura em formato A4."))
    story.append(spacer())

    # --- 7.1 Fluxo de Autenticação (TD) ---
    story.append(h2("7.1 Fluxo de Autenticação e Login"))

    def draw_auth_flow_td(c, w, h):
        cx = w / 2  # centro horizontal
        bw = 140  # largura das caixas
        bh = 26
        gap = 42

        y = h - 10
        # Row 1: Inicio
        draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, EMERALD, "Inicio: Usuário acessa /login", font_size=8)
        y -= bh
        draw_arrow(c, cx, y, cx, y - gap + bh, GRAY_TEXT)
        y -= gap

        # Row 2: POST /login
        draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, VIOLET, "POST /auth/login  (email + senha)", font_size=7)
        y -= bh
        draw_arrow(c, cx, y, cx, y - gap + bh, GRAY_TEXT)
        y -= gap

        # Row 3: Decision - valido?
        draw_diamond(c, cx, y - 18, 22, AMBER, "Valido?", font_size=7)
        # No - left
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(cx - 22 - 30, y - 18 + 2, "Nao")
        draw_arrow(c, cx - 22, y - 18, cx - 70, y - 18, RED)
        draw_rounded_rect(c, cx - 70 - 60, y - 18 - bh/2, 60, bh, RED, "Erro 401", font_size=8)
        # Yes - down
        c.setFillColor(EMERALD)
        c.drawString(cx + 5, y - 18 - 25, "Sim")
        draw_arrow(c, cx, y - 18 - 22, cx, y - 18 - 22 - (gap - bh - 4), EMERALD)
        y = y - 18 - 22 - (gap - bh - 4)

        # Row 4: Decision - first access?
        draw_diamond(c, cx, y - 18, 25, AMBER, "1o Acesso?", font_size=6)
        # Yes - left
        c.setFillColor(VIOLET)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(cx - 25 - 25, y - 18 + 2, "Sim")
        draw_arrow(c, cx - 25, y - 18, cx - 70, y - 18, VIOLET)
        draw_rounded_rect(c, cx - 70 - 80, y - 18 - bh/2, 80, bh, VIOLET, "FirstAccessModal\n(trocar senha)", font_size=7)
        # No - down
        c.setFillColor(EMERALD)
        c.drawString(cx + 5, y - 18 - 28, "Nao")
        draw_arrow(c, cx, y - 18 - 25, cx, y - 18 - 25 - (gap - bh - 8), EMERALD)
        y = y - 18 - 25 - (gap - bh - 8)

        # Row 5: Dashboard
        draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, EMERALD, "Dashboard (logado)", font_size=8)

    story.append(DiagramBox(W, 9.5 * cm, draw_auth_flow_td))
    story.append(PageBreak())

    # --- 7.2 Fluxo de Convite (TD) ---
    story.append(h2("7.2 Fluxo de Convite de Usuário (RF-001)"))

    def draw_invite_flow_td(c, w, h):
        cx = w / 2
        bw = 160
        bh = 28
        gap = 40

        y = h - 8
        steps = [
            (VIOLET_DARK, "Admin: POST /invite-admin\n(email, nome, role)"),
            (BLUE, "Cria InvitationToken\n(token + hash senha temp, TTL 2h, max 3 tentativas)"),
            (EMERALD, "Email enviado ao convidado\n(link + senha temporária)"),
            (AMBER, "Convidado: Step 1 - Validar Token\nPOST /validate-invitation-token"),
        ]
        for color, text in steps:
            draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, color, text, font_size=7)
            y -= bh
            if text != steps[-1][1]:
                draw_arrow(c, cx, y, cx, y - (gap - bh), GRAY_TEXT)
                y -= (gap - bh)

        # Decision
        draw_arrow(c, cx, y, cx, y - 14, GRAY_TEXT)
        y -= 14
        draw_diamond(c, cx, y - 18, 22, AMBER, "OK?", font_size=7)

        # No - left
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(cx - 22 - 25, y - 16, "Nao")
        draw_arrow(c, cx - 22, y - 18, cx - 65, y - 18, RED)
        draw_rounded_rect(c, cx - 65 - 70, y - 18 - 12, 70, 24, RED, "Erro: token\ninvalido/expirado", font_size=6)

        # Yes - down
        c.setFillColor(EMERALD)
        c.drawString(cx + 5, y - 18 - 25, "Sim")
        draw_arrow(c, cx, y - 18 - 22, cx, y - 18 - 22 - 12, EMERALD)
        y = y - 18 - 22 - 12

        steps2 = [
            (VIOLET, "Step 2: Definir Senha Permanente\nPOST /set-permanent-password-from-invitation"),
            (EMERALD, "Usuário CRIADO no banco\n(email, nome, senha hash, role)"),
            (DARK_100, "Redirect para /login\n(usuário pode fazer login)"),
        ]
        for color, text in steps2:
            draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, color, text, font_size=7)
            y -= bh
            if text != steps2[-1][1]:
                draw_arrow(c, cx, y, cx, y - (gap - bh), GRAY_TEXT)
                y -= (gap - bh)

    story.append(DiagramBox(W, 13 * cm, draw_invite_flow_td))
    story.append(PageBreak())

    # --- 7.3 Fluxo Questionário -> OCG (TD) ---
    story.append(h2("7.3 Fluxo Questionário &rarr; Verificação &rarr; OCG"))

    def draw_questionnaire_flow_td(c, w, h):
        cx = w / 2
        bw = 160
        bh = 28
        gap = 40

        y = h - 8
        # Step 1: Questionário
        draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, VIOLET, "GP preenche Questionário\n54 campos (Q1-Q49)", font_size=7)
        y -= bh
        draw_arrow(c, cx, y, cx, y - 12, GRAY_TEXT)
        y -= 12

        # Step 2: Verificação
        draw_rounded_rect(c, cx - bw/2, y - 32, bw, 32, AMBER, "Verificação Tecnológica\n8 fases, 50+ regras, matrizes", font_size=7)
        y -= 32
        draw_arrow(c, cx, y, cx, y - 14, GRAY_TEXT)
        y -= 14

        # Decision: Aprovado?
        draw_diamond(c, cx, y - 18, 24, AMBER, "Aprovado?", font_size=6)

        # No - left
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(cx - 24 - 30, y - 16, "Nao")
        draw_arrow(c, cx - 24, y - 18, cx - 75, y - 18, RED)
        draw_rounded_rect(c, cx - 75 - 80, y - 18 - 14, 80, 28, RED, "Devolver ao GP\ncom ações corretivas", font_size=6)

        # Yes - down
        c.setFillColor(EMERALD)
        c.drawString(cx + 5, y - 18 - 27, "Sim")
        draw_arrow(c, cx, y - 18 - 24, cx, y - 18 - 24 - 12, EMERALD)
        y = y - 18 - 24 - 12

        # Agent 0
        draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, VIOLET_DARK, "Agent 0: Analyzer\nClassifica respostas por pilar", font_size=7)
        y -= bh
        draw_arrow(c, cx, y, cx, y - 12, GRAY_TEXT)
        y -= 12

        # Agents P1-P7 in parallel (side by side)
        pw = 56
        ph = 36
        total_w = 7 * pw + 6 * 4
        start_x = cx - total_w / 2
        colors_p = [BLUE, VIOLET, EMERALD, AMBER, VIOLET_DARK, BLUE, RED]
        labels_p = ["P1\nBusiness", "P2\nRules", "P3\nFeatures", "P4\nNFR", "P5\nArch", "P6\nData", "P7\nSecurity"]
        for i in range(7):
            xx = start_x + i * (pw + 4)
            draw_rounded_rect(c, xx, y - ph, pw, ph, colors_p[i], labels_p[i], font_size=6)
        c.setFillColor(GRAY_TEXT)
        c.setFont("Helvetica-Oblique", 7)
        c.drawCentredString(cx, y - ph - 10, "[Executam em PARALELO]")
        y -= ph + 16
        draw_arrow(c, cx, y, cx, y - 12, GRAY_TEXT)
        y -= 12

        # Consolidator
        draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, DARK_100, "Agent 8: Consolidator\nAgrega scores, gera OCG final", font_size=7)
        y -= bh
        draw_arrow(c, cx, y, cx, y - 12, EMERALD)
        y -= 12

        # OCG
        draw_rounded_rect(c, cx - 50, y - 32, 100, 32, EMERALD, "OCG Gerado\n(salvo no banco)", font_size=8)

    story.append(DiagramBox(W, 14.5 * cm, draw_questionnaire_flow_td))
    story.append(PageBreak())

    # --- 7.4 Fluxo Projeto Externo (TD) ---
    story.append(h2("7.4 Fluxo de Criação de Projeto Externo"))

    def draw_external_flow_td(c, w, h):
        cx = w / 2
        bw = 170
        bh = 28
        gap = 40

        y = h - 8
        steps = [
            (DARK_100, "LoginPage: clica 'Criar Novo Projeto GCA'"),
            (VIOLET, "POST /questionnaires/request-access\n(email, nome, role=gp)"),
            (BLUE, "Token gerado (5 dias de validade)\nSalvo como InvitationToken"),
            (EMERALD, "Email enviado com link único\nhttps://gca.../novo-projeto?token=..."),
            (VIOLET, "NovoProjetoPage: 3 Steps\n1.Identificacao  2.Questionário  3.Enviado"),
            (AMBER, "Timer contagem regressiva 5 dias\nSalvar rascunho, aviso ao sair"),
            (VIOLET_DARK, "Preenche Questionário (54 campos)\nSubmit: POST /questionnaires"),
            (EMERALD, "Questionário Enviado!\nStatus: Pendente de aprovação"),
            (AMBER, "Admin: Aprovar ou Rejeitar\ncom motivo (email ao GP)"),
            (EMERALD, "Projeto Aprovado!\nTenant PostgreSQL criado (proj_slug_*)"),
        ]
        for i, (color, text) in enumerate(steps):
            draw_rounded_rect(c, cx - bw/2, y - bh, bw, bh, color, text, font_size=7)
            y -= bh
            if i < len(steps) - 1:
                draw_arrow(c, cx, y, cx, y - (gap - bh), GRAY_TEXT)
                y -= (gap - bh)

    story.append(DiagramBox(W, 14.5 * cm, draw_external_flow_td))
    story.append(PageBreak())

    # ========================================================================
    # 8. DIAGRAMAS DE SEQUENCIA (visual, TD)
    # ========================================================================
    story.append(h1("8. Diagramas de Sequência"))
    story.append(hr())
    story.append(p("Diagramas de sequência representando interações entre componentes do sistema."))
    story.append(spacer())

    def draw_sequence_diagram(c, w, h, title, actors, messages):
        """
        Desenha diagrama de sequência vertical.
        actors: list of (name, color)
        messages: list of (from_idx, to_idx, label, is_return)
        """
        n = len(actors)
        margin = 30
        spacing = (w - 2 * margin) / max(n - 1, 1)
        actor_x = [margin + i * spacing for i in range(n)]
        actor_w = 70
        actor_h = 22

        # Title
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(VIOLET_DARK)
        c.drawCentredString(w / 2, h - 12, title)

        top_y = h - 25
        # Draw actor boxes
        for i, (name, color) in enumerate(actors):
            x = actor_x[i]
            draw_rounded_rect(c, x - actor_w/2, top_y - actor_h, actor_w, actor_h, color, name, font_size=7)

        # Draw lifelines
        line_start_y = top_y - actor_h - 2
        line_end_y = 15
        c.setStrokeColor(HexColor("#d1d5db"))
        c.setDash(3, 3)
        c.setLineWidth(0.8)
        for x in actor_x:
            c.line(x, line_start_y, x, line_end_y)
        c.setDash()

        # Draw messages
        msg_y = line_start_y - 18
        msg_gap = (line_start_y - line_end_y - 20) / max(len(messages), 1)
        msg_gap = min(msg_gap, 22)

        for from_idx, to_idx, label, is_return in messages:
            x1 = actor_x[from_idx]
            x2 = actor_x[to_idx]

            if from_idx == to_idx:
                # Self-call
                c.setStrokeColor(VIOLET if not is_return else GRAY_TEXT)
                c.setLineWidth(1)
                c.setDash() if not is_return else c.setDash(2, 2)
                loop_w = 25
                c.line(x1, msg_y, x1 + loop_w, msg_y)
                c.line(x1 + loop_w, msg_y, x1 + loop_w, msg_y - 8)
                c.line(x1 + loop_w, msg_y - 8, x1, msg_y - 8)
                # Arrow head
                c.line(x1, msg_y - 8, x1 + 5, msg_y - 5)
                c.line(x1, msg_y - 8, x1 + 5, msg_y - 11)
                c.setDash()
                c.setFillColor(DARK_BG)
                c.setFont("Helvetica", 6)
                c.drawString(x1 + loop_w + 3, msg_y - 5, label)
            else:
                color = GRAY_TEXT if is_return else VIOLET
                c.setStrokeColor(color)
                c.setLineWidth(1.2)
                if is_return:
                    c.setDash(3, 3)
                else:
                    c.setDash()
                c.line(x1, msg_y, x2, msg_y)
                # Arrow head
                import math
                angle = math.atan2(0, x2 - x1)
                al = 5
                c.line(x2, msg_y, x2 - al * math.cos(angle - 0.4), msg_y - al * math.sin(angle - 0.4))
                c.line(x2, msg_y, x2 - al * math.cos(angle + 0.4), msg_y + al * math.sin(angle + 0.4))
                c.setDash()

                # Label centered above arrow
                c.setFillColor(DARK_BG)
                c.setFont("Helvetica", 6)
                mid_x = (x1 + x2) / 2
                c.drawCentredString(mid_x, msg_y + 3, label)

            msg_y -= msg_gap

    # --- 8.1 Sequência: Login ---
    story.append(h2("8.1 Sequência: Login Completo"))

    def draw_login_seq(c, w, h):
        actors = [
            ("Usuário", DARK_100),
            ("Frontend", VIOLET),
            ("API /auth", VIOLET_DARK),
            ("PostgreSQL", BLUE),
        ]
        messages = [
            (0, 1, "Preenche email + senha", False),
            (1, 2, "POST /login {email, password}", False),
            (2, 3, "SELECT user WHERE email=?", False),
            (3, 2, "User record", True),
            (2, 2, "Verifica bcrypt hash", False),
            (2, 2, "Gera JWT access + refresh token", False),
            (2, 3, "UPDATE last_login_at", False),
            (2, 1, "Response {tokens, user_info}", True),
            (1, 1, "Verifica first_access_completed", False),
            (1, 0, "Dashboard ou FirstAccessModal", True),
        ]
        draw_sequence_diagram(c, w, h, "Login Completo", actors, messages)

    story.append(DiagramBox(W, 10 * cm, draw_login_seq))
    story.append(PageBreak())

    # --- 8.2 Sequência: Convite ---
    story.append(h2("8.2 Sequência: Convite de Usuário"))

    def draw_invite_seq(c, w, h):
        actors = [
            ("Admin", VIOLET_DARK),
            ("API", VIOLET),
            ("PostgreSQL", BLUE),
            ("Email Svc", EMERALD),
            ("Convidado", DARK_100),
        ]
        messages = [
            (0, 1, "POST /invite-admin {email,nome,role}", False),
            (1, 1, "Gera token + hash senha temp", False),
            (1, 2, "INSERT InvitationToken", False),
            (1, 3, "Envia email com link + senha temp", False),
            (3, 4, "Email recebido", True),
            (4, 1, "POST /validate-invitation-token", False),
            (1, 2, "SELECT token, verifica TTL + tentativas", False),
            (1, 4, "Response {valid, email}", True),
            (4, 1, "POST /set-permanent-password", False),
            (1, 2, "INSERT User + UPDATE token.is_used", False),
            (1, 4, "Response {success}", True),
            (4, 4, "Redirect /login", False),
        ]
        draw_sequence_diagram(c, w, h, "Convite de Usuário (RF-001)", actors, messages)

    story.append(DiagramBox(W, 11 * cm, draw_invite_seq))
    story.append(PageBreak())

    # --- 8.3 Sequência: Questionário -> OCG ---
    story.append(h2("8.3 Sequência: Questionário &rarr; OCG"))

    def draw_q_ocg_seq(c, w, h):
        actors = [
            ("GP", DARK_100),
            ("Frontend", VIOLET),
            ("API", VIOLET_DARK),
            ("TechVerif", AMBER),
            ("Agents IA", BLUE),
            ("PostgreSQL", EMERALD),
        ]
        messages = [
            (0, 1, "Preenche 54 campos (Q1-Q49)", False),
            (1, 2, "POST /questionnaires {responses}", False),
            (2, 3, "run_full_pipeline(responses)", False),
            (3, 3, "8 fases: completude, stack, cross-pillar", False),
            (3, 2, "Return {approved, findings, score}", True),
            (2, 4, "Se aprovado: generate_ocg()", False),
            (4, 4, "Agent 0: Analyzer", False),
            (4, 4, "Agents P1-P7 [PARALELO]", False),
            (4, 4, "Agent 8: Consolidator", False),
            (4, 5, "INSERT OCG + OCGAnalysisLog", False),
            (4, 2, "OCGResponse {scores, status}", True),
            (2, 1, "Resultado da análise", True),
            (1, 0, "Exibe resultado + status", True),
        ]
        draw_sequence_diagram(c, w, h, "Questionário -> Verificação -> OCG", actors, messages)

    story.append(DiagramBox(W, 12 * cm, draw_q_ocg_seq))
    story.append(PageBreak())

    # --- 8.4 Sequência: Reset de Senha ---
    story.append(h2("8.4 Sequência: Reset de Senha"))

    def draw_reset_seq(c, w, h):
        actors = [
            ("Usuário", DARK_100),
            ("Frontend", VIOLET),
            ("API /auth", VIOLET_DARK),
            ("PostgreSQL", BLUE),
            ("Email Svc", EMERALD),
        ]
        messages = [
            (0, 1, "Clica 'Esqueci minha senha'", False),
            (1, 2, "POST /reset-password {email}", False),
            (2, 3, "Verifica email (sem revelar)", False),
            (2, 3, "INSERT ResetToken (24h TTL)", False),
            (2, 4, "Envia email com link + token", False),
            (2, 1, "Response generica (sem enumeração)", True),
            (0, 1, "Clica link do email", False),
            (1, 2, "POST /verify-reset-token {token}", False),
            (2, 3, "Verifica valido + nao expirado", False),
            (2, 1, "Response {valid}", True),
            (0, 1, "Define nova senha", False),
            (1, 2, "POST /reset-password-confirm", False),
            (2, 2, "Valida forca da senha", False),
            (2, 3, "UPDATE password_hash + token.used", False),
            (2, 1, "Response {success}", True),
            (1, 0, "Redirect /login", True),
        ]
        draw_sequence_diagram(c, w, h, "Reset de Senha", actors, messages)

    story.append(DiagramBox(W, 13 * cm, draw_reset_seq))

    story.append(PageBreak())

    # ========================================================================
    # 9. ENDPOINTS DA API
    # ========================================================================
    story.append(h1("9. Endpoints da API"))
    story.append(hr())

    story.append(h2("9.1 Autenticação (/auth)"))
    auth_endpoints = [
        ("POST", "/bootstrap-admin", "Cria primeiro admin (so sem usuários)"),
        ("POST", "/login", "Login email + senha"),
        ("POST", "/refresh", "Renova access token"),
        ("POST", "/change-password", "Altera senha (autenticado)"),
        ("POST", "/reset-password", "Solicita reset por email"),
        ("POST", "/verify-reset-token", "Verifica token de reset"),
        ("POST", "/reset-password-confirm", "Confirma nova senha com token"),
        ("POST", "/change-first-password", "Troca senha temporária (1o acesso)"),
        ("GET", "/me", "Perfil do usuário autenticado"),
        ("GET", "/password-requirements", "Regras de senha para UI"),
        ("POST", "/validate-invitation-token", "Step 1: valida token + senha temp"),
        ("POST", "/set-permanent-password-from-invitation", "Step 2: cria usuário com senha permanente"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        auth_endpoints,
        col_widths=[2 * cm, 7 * cm, W - 9 * cm]
    ))
    story.append(spacer())

    story.append(h2("9.2 Projetos (/projects)"))
    proj_endpoints = [
        ("GET", "/", "Lista projetos acessiveis"),
        ("POST", "/{id}/invite", "Convida usuário para projeto"),
        ("GET", "/{id}/invites", "Convites pendentes do projeto"),
        ("POST", "/{id}/accept-invite", "Aceita convite (sem auth)"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        proj_endpoints,
        col_widths=[2 * cm, 5 * cm, W - 7 * cm]
    ))
    story.append(spacer())

    story.append(h2("9.3 Questionários (/questionnaires)"))
    q_endpoints = [
        ("POST", "/", "Submete questionário para análise"),
        ("GET", "/{id}/status", "Status + resultado da análise"),
        ("POST", "/request-access", "Gera token para acesso externo (5d)"),
        ("POST", "/draft", "Salva rascunho do questionário"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        q_endpoints,
        col_widths=[2 * cm, 5 * cm, W - 7 * cm]
    ))
    story.append(spacer())

    story.append(h2("9.4 Admin (/admin)"))
    admin_endpoints = [
        ("POST", "/projects", "Cria projeto (admin)"),
        ("GET", "/projects/pending", "Projetos pendentes"),
        ("POST", "/projects/{id}/approve", "Aprova projeto (cria tenant)"),
        ("POST", "/projects/{id}/reject", "Rejeita projeto com motivo"),
        ("GET", "/users", "Lista todos usuários"),
        ("POST", "/users/{id}/reset-password", "Reset senha do usuário"),
        ("POST", "/users/{id}/lock", "Bloqueia conta"),
        ("POST", "/users/{id}/unlock", "Desbloqueia conta"),
        ("POST", "/users/{id}/block", "Bloqueia usuário (segurança)"),
        ("POST", "/users/{id}/unblock", "Desbloqueia usuário"),
        ("GET", "/suspicious-access", "Acessos suspeitos"),
        ("GET", "/tickets", "Lista tickets"),
        ("POST", "/tickets/{id}/respond", "Responde ticket"),
        ("GET", "/dashboard/metrics", "Métricas do dashboard"),
        ("POST", "/invite-admin", "Convida novo admin"),
        ("GET", "/audit", "Log de auditoria global"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        admin_endpoints,
        col_widths=[2 * cm, 5.5 * cm, W - 7.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("9.5 Agentes IA (/agents)"))
    agent_endpoints = [
        ("POST", "/agents/analyze", "Agent 0: classifica questionário por pilar"),
        ("POST", "/agents/pillar/{pillar_id}", "Agents 1-7: analisa pilar especifico"),
        ("POST", "/agents/consolidate", "Agent 8: consolida OCG final"),
        ("GET", "/ocg/{ocg_id}", "Recupera OCG gerado"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        agent_endpoints,
        col_widths=[2 * cm, 5.5 * cm, W - 7.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("9.6 Avaliação e Geração de Código"))
    eval_endpoints = [
        ("POST", "/projects/{id}/artifacts/{aid}/evaluate", "Avalia artefato (7 pilares)"),
        ("GET", "/projects/{id}/artifacts/{aid}/evaluation", "Ultima avaliação"),
        ("GET", "/projects/{id}/evaluations", "Todas avaliacoes do projeto"),
        ("POST", "/projects/{id}/evaluate-all", "Avalia todos artefatos"),
        ("POST", "/code-generation/project", "Gera código do projeto completo"),
        ("POST", "/code-generation/module", "Gera modulo especifico"),
        ("GET", "/code-generation/providers", "Lista provedores LLM"),
        ("GET", "/code-generation/history/{id}", "Histórico de geracoes"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        eval_endpoints,
        col_widths=[2 * cm, 7 * cm, W - 9 * cm]
    ))
    story.append(spacer())

    story.append(h2("9.7 Webhooks"))
    wh_endpoints = [
        ("POST", "/webhooks/questionnaire", "Webhook n8n: análise de questionário"),
        ("POST", "/webhooks/questionnaire-result", "Callback n8n: resultado IA"),
        ("POST", "/webhooks/ocg-result", "Callback: resultado OCG dos agentes"),
    ]
    story.append(make_table(
        ["Metodo", "Rota", "Descrição"],
        wh_endpoints,
        col_widths=[2 * cm, 6 * cm, W - 8 * cm]
    ))

    story.append(PageBreak())

    # ========================================================================
    # 10. MODELOS DE DADOS
    # ========================================================================
    story.append(h1("10. Modelos de Dados"))
    story.append(hr())

    story.append(h2("10.1 Schema Global"))
    global_models = [
        ("User", "user_id, email, password_hash, full_name, is_active, is_admin, first_access_completed, password_changed_at, created_at, updated_at, last_login_at"),
        ("Organization", "id, name, slug, description, owner_id, is_active, created_at, updated_at"),
        ("Project", "id, organization_id, name, slug, description, status, wizard_completed_at, provisioning_status, created_at, updated_at"),
        ("ProjectMember", "id, project_id, user_id, role, invited_by, invite_token, invite_expires_at, invited_at, accepted_at"),
        ("InvitationToken", "id, email, full_name, role, token, temporary_password_hash, validation_attempts, is_used, invited_by_id, expires_at, created_at"),
        ("ResetToken", "id, user_id, token, expires_at, used, used_at, created_at"),
        ("AccessAttempt", "id, user_id, project_id, attempt_number, blocked, blocked_at, created_at, unblocked_at"),
        ("Questionnaire", "id, project_id, gp_email, responses, adherence_score, status, approved, validations, observations, restrictions, highlighted_fields, submitted_at, analyzed_at"),
        ("OCG", "id, questionnaire_id, project_id, p1-p7_scores, overall_score, status, is_blocking, ocg_data, generated_at, generated_by"),
        ("OCGAnalysisLog", "id, ocg_id, agent_name, agent_input_hash, agent_output_hash, tokens_used, latency_ms, status, error_message"),
        ("GlobalAuditLog", "id, event_type, actor_id, actor_email, resource_type, resource_id, details, previous_hash, created_at"),
        ("SupportTicket", "id, user_id, project_id, title, description, severity, status, created_at, resolved_at"),
        ("TicketResponse", "id, ticket_id, responder_id, message, is_resolution, created_at"),
        ("IntegrationWebhook", "id, integration_type, webhook_url, is_active, last_tested_at"),
        ("SystemAlert", "id, alert_type, severity, title, message, status, acknowledged_at, acknowledged_by"),
    ]
    for model_name, cols in global_models:
        story.append(h3(model_name))
        story.append(code(cols))
        story.append(spacer(0.1))

    story.append(spacer())
    story.append(h2("10.2 Schema por Tenant (proj_{slug}_*)"))
    tenant_models = [
        ("PillarConfiguration", "id, pillar_code, pillar_name, weight, importance, custom_criteria, subcriteria_weights, is_active"),
        ("OGCVersion", "id, version, language, architecture, framework, database, frontend_framework, deployment_type, pillar_context, ocg_data, created_by"),
        ("Artifact", "id, name, type, content, file_path, description, tags, status, evaluation_id, generated_code, created_by"),
        ("ArtifactEvaluation", "id, artifact_id, p1-p7_scores, final_score, final_status, code_generation_allowed, evaluation_details, feedback"),
        ("AuditLog", "id, action, resource_type, resource_id, details, actor_id, created_at"),
    ]
    for model_name, cols in tenant_models:
        story.append(h3(model_name))
        story.append(code(cols))
        story.append(spacer(0.1))

    story.append(PageBreak())

    # ========================================================================
    # 11. PIPELINE DE VERIFICACAO TECNOLOGICA
    # ========================================================================
    story.append(h1("11. Pipeline de Verificação Tecnológica"))
    story.append(hr())
    story.append(p(
        "O <b>TechnologyVerificationService</b> (1.464 linhas) e o guardiao entre o questionário "
        "e o OCG. Executa 8 fases de validação com 50+ regras e matrizes de compatibilidade."
    ))
    story.append(spacer())

    story.append(h2("11.1 Fases do Pipeline"))
    phases = [
        ("1", "Completude", "_check_completeness", "Campos obrigatórios preenchidos", "BLOCKER"),
        ("2", "Stack", "_check_language_framework_compat + 3", "Linguagem x Framework x Banco x Arch", "BLOCKER"),
        ("3", "Arquitetura", "_check_arch_* (5 metodos)", "Execução, conflitos, entregáveis, DB", "CRITICAL"),
        ("4", "Viabilidade", "_check_tech_feasibility", "Combinacoes impossiveis/arriscadas", "BLOCKER"),
        ("5", "Cross-Pillar", "_check_cross_pillar_* (5)", "P1xP5, P3xP4, P5xP7, P2xP7, P3xP6", "CRITICAL"),
        ("6", "Segurança", "_check_security_compliance", "Criticidade vs controles de segurança", "BLOCKER"),
        ("7", "Entregáveis", "_check_delivery_alignment", "Coerência de entregáveis vs stack", "WARNING"),
        ("8", "Projeto Existente", "_check_existing_project", "Regras especificas se Q3=Sim", "WARNING"),
    ]
    story.append(make_table(
        ["Fase", "Nome", "Metodo(s)", "Verifica", "Max Sev."],
        phases,
        col_widths=[1.2 * cm, 2.5 * cm, 4.5 * cm, 5.5 * cm, 2.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("11.2 Severidades"))
    sevs = [
        ("BLOCKER", "Impede geração do OCG. Questionário devolvido com ações corretivas.", "Vermelho"),
        ("CRITICAL", "Risco alto. Requer justificativa ou correção antes de prosseguir.", "Laranja"),
        ("WARNING", "Recomendacao forte. Nao impede, mas deve ser revisada.", "Amarelo"),
        ("INFO", "Sugestão. Informativo, sem impacto no fluxo.", "Azul"),
    ]
    story.append(make_table(
        ["Severidade", "Descrição", "Indicador"],
        sevs,
        col_widths=[2.5 * cm, W - 5 * cm, 2.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("11.3 Matrizes de Compatibilidade"))
    matrices = [
        ("LANGUAGE_FRAMEWORK", "Python: FastAPI, Django, Flask | Node.js: NestJS, Express | Java: Spring | C#: .NET | Go: Gin, Echo"),
        ("FRAMEWORK_DB", "FastAPI: PostgreSQL, MySQL | Django: PostgreSQL, SQLite | NestJS: PostgreSQL, MongoDB"),
        ("FRONTEND_LANGUAGE", "React/Next.js: TypeScript, JavaScript | Angular: TypeScript | Vue: TypeScript, JavaScript"),
        ("ARCH_EXECUTION", "Monolito: Stand-alone, On-premises | Microserviços: Cloud, Containerizado | Serverless: Cloud"),
        ("DELIVERABLE_REQUIREMENTS", "Web App: requer frontend + backend | API: requer backend | Mobile: requer frontend mobile"),
        ("DB_USAGE_RISKS", "SQLite + Alta Concorrencia = BLOCKER | MongoDB + ACID forte = WARNING"),
        ("DB_ARCH_INCOMPATIBLE", "SQLite + Microserviços = BLOCKER | MongoDB + Stored Procedures = CRITICAL"),
        ("FRONTEND_DELIVERABLE", "React: Web App, SPA, PWA | React Native: Mobile | Electron: Desktop"),
    ]
    for name, desc in matrices:
        story.append(bullet(f"<b>{name}</b>: {desc}"))

    story.append(PageBreak())

    # ========================================================================
    # 12. ARQUITETURA DE AGENTES IA
    # ========================================================================
    story.append(h1("12. Arquitetura de Agentes IA"))
    story.append(hr())

    story.append(h2("12.1 Pipeline de 8 Agentes"))
    story.append(p(
        "O sistema utiliza 8 agentes especializados powered by Claude (Anthropic SDK) "
        "para transformar o questionário em OCG. Os agentes P1-P7 executam em <b>paralelo</b>."
    ))
    story.append(spacer())

    agents = [
        ("Agent 0", "Analyzer", "Classifica respostas por pilar, extrai metadados, identifica anomalias", "Orquestrador"),
        ("Agent 1", "P1 - Business", "ROI, stakeholders, timeline, budget, KPIs", "Especialista"),
        ("Agent 2", "P2 - Rules", "LGPD/GDPR, residência dados, auditoria", "Especialista"),
        ("Agent 3", "P3 - Features", "MVP, escopo, integrações, scope creep", "Especialista"),
        ("Agent 4", "P4 - Non-Functional", "Performance, escalabilidade, observabilidade", "Especialista"),
        ("Agent 5", "P5 - Architecture", "Stack, patterns, tecnologias", "Especialista"),
        ("Agent 6", "P6 - Data", "Banco, schema, persistência", "Especialista"),
        ("Agent 7", "P7 - Security", "Segurança, testes, vulnerabilidades", "Especialista"),
        ("Agent 8", "Consolidator", "Agrega scores, recomenda stack, gera OCG final", "Consolidador"),
    ]
    story.append(make_table(
        ["Agente", "Nome", "Responsabilidade", "Tipo"],
        agents,
        col_widths=[2 * cm, 3.5 * cm, W - 8 * cm, 2.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("12.2 Scoring e Status"))
    scoring = [
        ("90-100", "Excelente", "Estrategia clara, alta aderencia"),
        ("70-89", "Bom", "Cobertura boa, gaps menores"),
        ("50-69", "Regular", "Areas vagas ou incompletas"),
        ("< 50", "Critico", "Gaps criticos que impedem prosseguimento"),
    ]
    story.append(make_table(
        ["Score", "Nivel", "Descrição"],
        scoring,
        col_widths=[2.5 * cm, 3 * cm, W - 5.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("12.3 Status do OCG"))
    ocg_status = [
        ("READY", "Aprovado para geração de código"),
        ("NEEDS_REVIEW", "Requer revisao em areas especificas"),
        ("AT_RISK", "Riscos identificados, prosseguir com cautela"),
        ("BLOCKED", "P7 < 70 ou bloqueadores criticos. Código NAO pode ser gerado."),
    ]
    story.append(make_table(
        ["Status", "Descrição"],
        ocg_status,
        col_widths=[3.5 * cm, W - 3.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("12.4 Regra de Bloqueio P7"))
    story.append(note(
        "<b>REGRA CRITICA:</b> Se o score do Pilar 7 (Security) for inferior a 70, "
        "o OCG recebe status BLOCKED e is_blocking=True. Nenhuma geração de código e permitida "
        "ate que os gaps de segurança sejam resolvidos e o questionário reavaliado."
    ))

    story.append(PageBreak())

    # ========================================================================
    # 13. INFRAESTRUTURA
    # ========================================================================
    story.append(h1("13. Infraestrutura e Deploy"))
    story.append(hr())

    story.append(h2("13.1 Docker Compose (5 serviços)"))
    services = [
        ("postgres", "PostgreSQL 16 Alpine", "5432", "Banco principal, health check"),
        ("redis", "Redis 7 Alpine", "6379", "Cache, filas (interno)"),
        ("backend", "Python/FastAPI", "8000", "API REST, depends: pg+redis"),
        ("frontend", "Node 20/React+Vite", "5173", "SPA, build+preview"),
        ("n8n", "n8n", "5678", "Workflows, análise IA"),
    ]
    story.append(make_table(
        ["Serviço", "Imagem", "Porta", "Notas"],
        services,
        col_widths=[2.5 * cm, 4 * cm, 2 * cm, W - 8.5 * cm]
    ))
    story.append(spacer())

    story.append(h2("13.2 Produção"))
    story.append(bullet("<b>Servidor:</b> Maquina local (i5-13400, 40GB RAM, NVMe + SSD)"))
    story.append(bullet("<b>SO:</b> Linux Mint 22.3 Zena"))
    story.append(bullet("<b>Proxy:</b> Cloudflare Tunnel (reverse proxy, HTTPS, DDoS)"))
    story.append(bullet("<b>Auto-start:</b> systemd user service + loginctl linger"))
    story.append(bullet("<b>Restart:</b> unless-stopped em todos containers"))
    story.append(spacer())

    story.append(h2("13.3 URLs de Produção"))
    story.append(bullet("<b>Frontend:</b> https://gca.code-auditor.com.br"))
    story.append(bullet("<b>API:</b> https://api.code-auditor.com.br"))
    story.append(bullet("<b>n8n:</b> https://n8n.code-auditor.com.br"))
    story.append(spacer())

    story.append(h2("13.4 Deploy"))
    story.append(p(
        "O deploy e manual: git pull no servidor + docker compose rebuild. "
        "NAO e cloud-hosted. Cloudflare apenas faz proxy reverso para a maquina local."
    ))

    story.append(PageBreak())

    # ========================================================================
    # 14. GLOSSARIO
    # ========================================================================
    story.append(h1("14. Glossário"))
    story.append(hr())

    glossary = [
        ("GCA", "Gestão de Codificação Assistida - Sistema principal"),
        ("OCG", "Objeto Contexto Global - Resultado da análise dos 7 pilares gerado por 8 agentes IA"),
        ("GP", "Gestor de Projeto - Usuário responsavel pelo projeto"),
        ("P1-P7", "Os 7 Pilares de qualidade: Business, Rules, Features, NFR, Architecture, Data, Security"),
        ("Questionário", "Formulário técnico de 54 campos (Q1-Q54) preenchido pelo GP para iniciar análise"),
        ("Technology Verification", "Pipeline de 8 fases que valida consistência do questionário antes do OCG"),
        ("BLOCKER", "Severidade maxima que impede geração do OCG ate correcao"),
        ("InvitationToken", "Token temporário (2h) para convite de novos usuários com senha temporária"),
        ("First Access", "Fluxo obrigatório de troca de senha no primeiro login"),
        ("Multi-Tenant", "Isolamento de dados por projeto via schemas PostgreSQL separados"),
        ("Tenant", "Schema PostgreSQL isolado criado para cada projeto aprovado (proj_{slug}_*)"),
        ("n8n", "Plataforma de automação de workflows usada para análise IA enriquecida"),
        ("Claude", "Modelo de IA da Anthropic utilizado nos 8 agentes especializados"),
        ("Analyzer", "Agent 0 - Classifica respostas do questionário por pilar e extrai metadados"),
        ("Consolidator", "Agent 8 - Agrega resultados dos 7 pilares e gera OCG final"),
        ("Adherence Score", "Pontuacao de aderencia (0-100) calculada pela verificação tecnológica"),
        ("Cross-Pillar", "Validacao cruzada entre pilares para detectar contradições"),
        ("JWT", "JSON Web Token - Mecanismo de autenticação (access + refresh tokens)"),
        ("RBAC", "Role-Based Access Control - Controle de acesso baseado em papeis"),
        ("Artifact", "Artefato de software avaliado contra os 7 pilares"),
        ("Gatekeeper", "Modulo de avaliação de qualidade que pontua artefatos por pilar"),
        ("CodeGen", "Modulo de geração de código usando provedores LLM"),
        ("SPA", "Single Page Application - Aplicacao frontend de pagina unica (React)"),
        ("Tailwind", "Framework CSS utility-first usado no frontend"),
        ("FastAPI", "Framework Python async para API REST (backend)"),
        ("Zustand", "Gerenciador de estado leve para React (frontend)"),
        ("Cloudflare Tunnel", "Serviço de proxy reverso que expoe serviços locais via HTTPS"),
    ]
    story.append(make_table(
        ["Termo", "Definição"],
        glossary,
        col_widths=[4 * cm, W - 4 * cm]
    ))

    # ========================================================================
    # RODAPE FINAL
    # ========================================================================
    story.append(Spacer(1, 2 * cm))
    story.append(hr())
    story.append(Paragraph(
        "Documento gerado automaticamente pelo GCA em 08/04/2026.<br/>"
        "Luiz Carlos Pielak | gca.code-auditor.com.br",
        ParagraphStyle("Footer", parent=style_body, fontSize=9, textColor=GRAY_TEXT, alignment=TA_CENTER)
    ))

    # ========================================================================
    # BUILD
    # ========================================================================
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"\n{'='*60}")
    print(f"  PDF gerado com sucesso!")
    print(f"  Arquivo: {OUTPUT_PATH}")
    print(f"  Secoes: 14")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    build_document()
