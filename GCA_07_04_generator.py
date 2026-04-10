#!/usr/bin/env python3
"""
GCA - Documento de Analise de Requisitos
Gerado em 07/04/2026
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import os

# ============================================================================
# COLORS
# ============================================================================
VIOLET = HexColor("#7c3aed")
VIOLET_DARK = HexColor("#5b21b6")
VIOLET_LIGHT = HexColor("#ede9fe")
EMERALD = HexColor("#10b981")
EMERALD_LIGHT = HexColor("#d1fae5")
SLATE_700 = HexColor("#334155")
SLATE_500 = HexColor("#64748b")
SLATE_100 = HexColor("#f1f5f9")
SLATE_200 = HexColor("#e2e8f0")
RED_500 = HexColor("#ef4444")
RED_LIGHT = HexColor("#fee2e2")
AMBER_500 = HexColor("#f59e0b")
AMBER_LIGHT = HexColor("#fef3c7")
BLUE_500 = HexColor("#3b82f6")
BLUE_LIGHT = HexColor("#dbeafe")
DARK_BG = HexColor("#1a1a2e")
WHITE = white
BLACK = black

# ============================================================================
# STYLES
# ============================================================================
styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "DocTitle", parent=styles["Title"],
    fontSize=28, leading=34, textColor=VIOLET_DARK,
    spaceAfter=6*mm, alignment=TA_CENTER,
    fontName="Helvetica-Bold"
)

SUBTITLE_STYLE = ParagraphStyle(
    "DocSubtitle", parent=styles["Normal"],
    fontSize=14, leading=18, textColor=SLATE_500,
    spaceAfter=12*mm, alignment=TA_CENTER,
    fontName="Helvetica"
)

H1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontSize=20, leading=26, textColor=VIOLET_DARK,
    spaceBefore=10*mm, spaceAfter=5*mm,
    fontName="Helvetica-Bold",
    borderWidth=0, borderPadding=0,
    leftIndent=0
)

H2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontSize=15, leading=20, textColor=SLATE_700,
    spaceBefore=7*mm, spaceAfter=3*mm,
    fontName="Helvetica-Bold"
)

H3 = ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontSize=12, leading=16, textColor=VIOLET,
    spaceBefore=4*mm, spaceAfter=2*mm,
    fontName="Helvetica-Bold"
)

BODY = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=10, leading=14, textColor=SLATE_700,
    spaceAfter=3*mm, alignment=TA_JUSTIFY,
    fontName="Helvetica"
)

BODY_BOLD = ParagraphStyle(
    "BodyBold", parent=BODY,
    fontName="Helvetica-Bold"
)

BULLET = ParagraphStyle(
    "Bullet", parent=BODY,
    leftIndent=12*mm, bulletIndent=6*mm,
    spaceAfter=1.5*mm
)

SMALL = ParagraphStyle(
    "Small", parent=BODY,
    fontSize=8, leading=11, textColor=SLATE_500
)

CODE_STYLE = ParagraphStyle(
    "Code", parent=BODY,
    fontSize=8, leading=11,
    fontName="Courier",
    textColor=SLATE_700,
    backColor=SLATE_100,
    leftIndent=6*mm, rightIndent=6*mm,
    spaceBefore=2*mm, spaceAfter=2*mm,
    borderPadding=4
)

TABLE_HEADER_STYLE = ParagraphStyle(
    "TableHeader", parent=BODY,
    fontSize=9, leading=12,
    fontName="Helvetica-Bold",
    textColor=WHITE
)

TABLE_CELL_STYLE = ParagraphStyle(
    "TableCell", parent=BODY,
    fontSize=9, leading=12,
    spaceAfter=0
)

TABLE_CELL_SMALL = ParagraphStyle(
    "TableCellSmall", parent=BODY,
    fontSize=8, leading=10,
    spaceAfter=0
)

# ============================================================================
# HELPERS
# ============================================================================

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=SLATE_200,
                       spaceBefore=3*mm, spaceAfter=3*mm)

def spacer(h=4):
    return Spacer(1, h*mm)

def p(text, style=BODY):
    return Paragraph(text, style)

def h1(text):
    return Paragraph(text, H1)

def h2(text):
    return Paragraph(text, H2)

def h3(text):
    return Paragraph(text, H3)

def bullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", BULLET)

def make_table(headers, rows, col_widths=None):
    """Create a styled table with violet header."""
    w = col_widths or [None] * len(headers)
    header_cells = [Paragraph(h, TABLE_HEADER_STYLE) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), TABLE_CELL_STYLE) for c in row])

    t = Table(data, colWidths=w, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), VIOLET),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_200),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_100]),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def make_small_table(headers, rows, col_widths=None):
    """Smaller table variant."""
    w = col_widths or [None] * len(headers)
    header_cells = [Paragraph(h, TABLE_HEADER_STYLE) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), TABLE_CELL_SMALL) for c in row])

    t = Table(data, colWidths=w, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), VIOLET),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, SLATE_200),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_100]),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


# ============================================================================
# PAGE TEMPLATE
# ============================================================================

def header_footer(canvas, doc):
    canvas.saveState()
    # Header line
    canvas.setStrokeColor(VIOLET)
    canvas.setLineWidth(2)
    canvas.line(20*mm, A4[1] - 15*mm, A4[0] - 20*mm, A4[1] - 15*mm)

    # Header text
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(VIOLET)
    canvas.drawString(20*mm, A4[1] - 13*mm, "GCA - Gestao de Codificacao Assistida")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SLATE_500)
    canvas.drawRightString(A4[0] - 20*mm, A4[1] - 13*mm, "Documento de Analise de Requisitos")

    # Footer
    canvas.setStrokeColor(SLATE_200)
    canvas.setLineWidth(0.5)
    canvas.line(20*mm, 15*mm, A4[0] - 20*mm, 15*mm)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SLATE_500)
    canvas.drawString(20*mm, 10*mm, "GCA Software - Confidencial")
    canvas.drawCentredString(A4[0]/2, 10*mm, f"Versao 1.0 - {datetime.now().strftime('%d/%m/%Y')}")
    canvas.drawRightString(A4[0] - 20*mm, 10*mm, f"Pagina {doc.page}")

    canvas.restoreState()


# ============================================================================
# DOCUMENT CONTENT
# ============================================================================

def build_document():
    output_path = "/home/luiz/GCA/GCA_07_04.pdf"
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=22*mm, bottomMargin=22*mm,
        title="GCA - Documento de Analise de Requisitos",
        author="GCA Software",
    )

    story = []
    W = A4[0] - 40*mm  # usable width

    # ========================================================================
    # COVER PAGE
    # ========================================================================
    story.append(Spacer(1, 40*mm))
    story.append(p("GCA", TITLE_STYLE))
    story.append(p("Gestao de Codificacao Assistida", ParagraphStyle(
        "CoverSub", parent=SUBTITLE_STYLE, fontSize=18, textColor=VIOLET)))
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="60%", thickness=2, color=VIOLET,
                             spaceBefore=0, spaceAfter=0, hAlign="CENTER"))
    story.append(Spacer(1, 10*mm))
    story.append(p("Documento de Analise de Requisitos", SUBTITLE_STYLE))
    story.append(Spacer(1, 30*mm))

    cover_data = [
        ["Versao", "1.0"],
        ["Data", "07/04/2026"],
        ["Autor", "Luiz Carlos Pielak"],
        ["Organizacao", "GCA Software"],
        ["Classificacao", "Confidencial"],
        ["Status", "Em desenvolvimento"],
    ]
    cover_table = Table(cover_data, colWidths=[50*mm, 80*mm])
    cover_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), SLATE_500),
        ("TEXTCOLOR", (1, 0), (1, -1), SLATE_700),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, SLATE_200),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    story.append(cover_table)
    story.append(PageBreak())

    # ========================================================================
    # TABLE OF CONTENTS (manual)
    # ========================================================================
    story.append(h1("Sumario"))
    toc_items = [
        ("1.", "Introducao e Visao Geral"),
        ("2.", "Arquitetura do Sistema"),
        ("3.", "Requisitos Funcionais"),
        ("4.", "Requisitos Nao Funcionais"),
        ("5.", "Regras de Negocio"),
        ("6.", "Sistema de Questionario (54 Campos)"),
        ("7.", "Pipeline OCG (8 Agentes)"),
        ("8.", "Geracao de Codigo"),
        ("9.", "Seguranca e Autenticacao"),
        ("10.", "Mapa de Paginas do Frontend"),
        ("11.", "Endpoints da API"),
        ("12.", "Modelo de Dados"),
        ("13.", "Integracoes Externas"),
        ("14.", "Estrategia de Testes"),
        ("15.", "Glossario"),
        ("A.", "Anexo A: Fluxos Detalhados para Prototipacao"),
        ("B.", "Anexo B: Wireframes Textuais das Telas"),
        ("C.", "Anexo C: Referencia Cruzada JSON-Regras"),
    ]
    for num, title in toc_items:
        story.append(p(f"<b>{num}</b>  {title}", ParagraphStyle(
            "TOC", parent=BODY, fontSize=11, leading=18, leftIndent=5*mm)))
    story.append(PageBreak())

    # ========================================================================
    # 1. INTRODUCAO
    # ========================================================================
    story.append(h1("1. Introducao e Visao Geral"))
    story.append(p(
        "O <b>GCA (Gestao de Codificacao Assistida)</b> e uma plataforma end-to-end que automatiza "
        "o ciclo de vida de projetos de software, desde a analise de requisitos ate a geracao de codigo. "
        "O sistema utiliza inteligencia artificial (Claude Opus 4.6) para avaliar questionarios tecnicos, "
        "gerar um <b>Objeto Contexto Global (OCG)</b> com recomendacoes de stack e arquitetura, "
        "e produzir codigo-fonte alinhado com as melhores praticas de mercado."
    ))
    story.append(spacer(3))
    story.append(h2("1.1 Objetivos"))
    objectives = [
        "Padronizar a analise de requisitos com questionario estruturado de 54 campos",
        "Automatizar avaliacao tecnica via 8 agentes de IA especializados (7 pilares)",
        "Gerar codigo-fonte com contexto completo (OCG) e compliance integrado",
        "Fornecer governanca com trilhas de auditoria, RBAC e bloqueio por seguranca (P7 < 70)",
        "Integrar com GitHub, n8n, provedores de IA (Anthropic, OpenAI, DeepSeek, Gemini, Grok)",
        "Suportar multi-tenancy com isolamento por schema PostgreSQL",
    ]
    for obj in objectives:
        story.append(bullet(obj))

    story.append(h2("1.2 Stack Tecnologico"))
    stack_rows = [
        ["Backend", "Python 3.11+ / FastAPI / SQLAlchemy 2.0 async / Pydantic v2"],
        ["Frontend", "React 18.3 / TypeScript 5.6 / Vite 6.0 / Tailwind CSS 3.4 / Zustand"],
        ["Banco de Dados", "PostgreSQL 16 (26 tabelas, 325 colunas) + Redis 7"],
        ["IA/LLM", "Anthropic SDK (Claude Opus 4.6) / OpenAI / DeepSeek / Gemini / Grok"],
        ["Autenticacao", "JWT (RS256/HS256) / Bcrypt / Token refresh"],
        ["Infraestrutura", "Docker / Kubernetes / GitHub Actions / Cloudflare"],
        ["Automacao", "n8n (webhooks, workflows) / Piloter API"],
        ["Testes", "Pytest + pytest-asyncio (54 testes, 100% passando)"],
    ]
    story.append(make_table(["Camada", "Tecnologias"], stack_rows, [35*mm, W-35*mm]))
    story.append(PageBreak())

    # ========================================================================
    # 2. ARQUITETURA
    # ========================================================================
    story.append(h1("2. Arquitetura do Sistema"))
    story.append(p(
        "O GCA segue uma arquitetura em camadas com multi-tenancy por schema. "
        "Cada projeto possui seu proprio schema PostgreSQL isolado (<i>proj_{slug}_*</i>), "
        "enquanto usuarios, organizacoes e dados globais residem no schema publico."
    ))

    story.append(h2("2.1 Fluxo Principal"))
    flow_text = (
        "<b>Questionario (49Q)</b> &rarr; <b>Analise Built-in</b> (20 regras) &rarr; "
        "<b>Pipeline OCG</b> (8 agentes IA) &rarr; <b>Geracao de Codigo</b> (LLM) &rarr; "
        "<b>Validacao</b> (syntax, quality, security) &rarr; <b>GitHub</b> (branch, commit, PR)"
    )
    story.append(p(flow_text))

    story.append(h2("2.2 Diagrama de Componentes"))
    arch_rows = [
        ["React Frontend", "SPA com Vite, 20+ paginas, Zustand state management"],
        ["FastAPI Backend", "16 routers, 20 services, async/await nativo"],
        ["PostgreSQL", "Schema global + schemas isolados por projeto"],
        ["Redis", "Cache de sessoes, rate limiting, pub/sub"],
        ["Anthropic SDK", "8 agentes (Analyzer + 7 Pilares + Consolidator)"],
        ["n8n", "Orquestracao de workflows, webhooks, analise enriquecida"],
        ["GitHub API", "Branches, commits, PRs, deploy via Actions"],
        ["Email (SMTP)", "Convites, reset de senha, notificacoes"],
    ]
    story.append(make_table(["Componente", "Descricao"], arch_rows, [35*mm, W-35*mm]))
    story.append(PageBreak())

    # ========================================================================
    # 3. REQUISITOS FUNCIONAIS
    # ========================================================================
    story.append(h1("3. Requisitos Funcionais"))

    # RF-001 a RF-015
    rf_data = [
        ["RF-001", "Autenticacao e Primeiro Acesso",
         "Login com email/senha, JWT com refresh token. Primeiro acesso obriga troca de senha via modal. Bootstrap do primeiro admin."],
        ["RF-002", "Gestao de Usuarios e Perfis (RBAC)",
         "Admin gerencia usuarios. Perfis: admin, gp, tech_lead, dev, dev_senior, dev_pleno, qa, compliance, viewer. Bloqueio apos 5 tentativas."],
        ["RF-003", "Organizacoes e Multi-Tenancy",
         "Criar organizacoes com membros (admin, member, viewer). Cada projeto tem schema isolado (proj_{slug})."],
        ["RF-004", "Gestao de Projetos",
         "Ciclo: solicitacao (GP) -> aprovacao (Admin) -> provisionamento (schema) -> onboarding (5 etapas) -> ativo."],
        ["RF-005", "Sistema de Convites",
         "Convite por email com token de 7 dias. Criacao automatica de usuario. Aceitacao vincula ao projeto com perfil."],
        ["RF-006", "Questionario Tecnico (54 campos)",
         "9 blocos (A.1-A.8 + A.12). 49 perguntas do GP + 5 campos de retorno dos agentes. Validacao com 20+ regras. Score de aderencia (85%)."],
        ["RF-007", "Pipeline OCG (8 Agentes)",
         "Analyzer classifica por pilar. 7 especialistas avaliam em paralelo (P1-P7). Consolidator gera OCG final com score composto."],
        ["RF-008", "Geracao de Codigo com IA",
         "Gera codigo usando LLM (Anthropic, OpenAI, etc) enriquecido com contexto OCG. Suporta Python, Node.js, Java, Go, C#, PHP, Kotlin."],
        ["RF-009", "Validacao de Codigo",
         "Validacao de sintaxe, metricas de qualidade (complexidade ciclomatica), scan de seguranca (SAST), cobertura de testes."],
        ["RF-010", "Avaliacao por 7 Pilares",
         "Cada artefato avaliado contra 7 pilares com pesos configuraveis. P7 (Seguranca) < 70 = BLOQUEIO. Score composto determina aprovacao."],
        ["RF-011", "Integracao GitHub",
         "Autenticar, listar repos, criar branches, fazer commits, criar PRs, deploy via GitHub Actions."],
        ["RF-012", "Onboarding em 5 Etapas",
         "1) Repositorio 2) SMTP 3) Equipe 4) Arquitetura 5) Stack. Progresso persistido no banco."],
        ["RF-013", "Dashboard e Metricas",
         "Metricas de projeto, timeline de geracoes, custos por provedor LLM, resumo executivo."],
        ["RF-014", "Sistema de Tickets (SAC)",
         "Abertura de tickets com severidade. Respostas do admin. Tracking de SLA (primeiro response, resolucao)."],
        ["RF-015", "Auditoria e Alertas",
         "Audit log global com hash chain. Alertas para Teams/Slack/Email. Deteccao de acesso suspeito."],
    ]
    story.append(make_small_table(
        ["ID", "Requisito", "Descricao"],
        rf_data,
        [18*mm, 45*mm, W-63*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # 4. REQUISITOS NAO FUNCIONAIS
    # ========================================================================
    story.append(h1("4. Requisitos Nao Funcionais"))

    rnf_data = [
        ["RNF-001", "Performance", "API: P95 < 500ms. OCG pipeline: < 5 min. Code gen: < 30s (mocked). Health check: < 100ms."],
        ["RNF-002", "Escalabilidade", "Suportar 5000+ usuarios concorrentes. Agentes OCG executam em paralelo. Pool de conexoes DB: 20 + overflow 10."],
        ["RNF-003", "Disponibilidade", "SLA 99.5%+ (meta 99.9%). Health check em /health. Monitoramento com alertas automaticos."],
        ["RNF-004", "Seguranca", "JWT RS256, bcrypt, senha 10+ chars (upper + digit + special). Criptografia em transito (TLS). Vault para secrets. CORS restrito."],
        ["RNF-005", "Observabilidade", "Structlog (JSON), metricas por endpoint, tracing de agentes, health checks, dashboard operacional."],
        ["RNF-006", "Portabilidade", "Docker + Docker Compose (dev), Kubernetes (prod). Multi-cloud: AWS, GCP, Azure."],
        ["RNF-007", "Manutenibilidade", "Clean Architecture, DI, tipagem forte (Pydantic v2), 54 testes automatizados, CI/CD com GitHub Actions."],
        ["RNF-008", "Compliance", "LGPD (dados pessoais, consentimento, exclusao). Audit log com 365 dias de retencao. Trilhas imutaveis (hash chain)."],
        ["RNF-009", "Backup e Recuperacao", "Backup diario PostgreSQL. RPO: 24h. RTO: 1h. Backup de configuracoes em S3."],
        ["RNF-010", "Internacionalizacao", "Interface em Portugues-BR. Mensagens de erro localizadas. Suporte futuro a Ingles."],
    ]
    story.append(make_small_table(
        ["ID", "Categoria", "Descricao"],
        rnf_data,
        [18*mm, 30*mm, W-48*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # 5. REGRAS DE NEGOCIO
    # ========================================================================
    story.append(h1("5. Regras de Negocio"))

    story.append(h2("5.1 Autenticacao e Senha"))
    rn_auth = [
        ["RN-001", "Senha minima: 10 caracteres, 1 maiuscula, 1 digito, 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"],
        ["RN-002", "Primeiro acesso: usuario DEVE trocar senha antes de acessar o sistema (FirstAccessModal)"],
        ["RN-003", "Token de reset expira em 1 hora. Uso unico (single-use enforcement)"],
        ["RN-004", "Bloqueio de acesso apos 5 tentativas falhas consecutivas. Desbloqueio manual pelo admin"],
        ["RN-005", "Access token expira em 60 minutos. Refresh token expira em 7 dias"],
    ]
    for rn_id, desc in rn_auth:
        story.append(bullet(f"<b>{rn_id}:</b> {desc}"))

    story.append(h2("5.2 Projetos e Aprovacao"))
    rn_proj = [
        ["RN-006", "GP solicita projeto. Admin aprova ou rejeita. Aprovacao cria schema isolado automaticamente"],
        ["RN-007", "Onboarding em 5 etapas sequenciais. Etapa seguinte so habilita apos conclusao da anterior"],
        ["RN-008", "Convites expiram em 7 dias. Token de 32 bytes (secure random). Email obrigatorio"],
        ["RN-009", "Admin ve todos os projetos. GP ve apenas os seus. Viewer tem acesso somente leitura"],
    ]
    for rn_id, desc in rn_proj:
        story.append(bullet(f"<b>{rn_id}:</b> {desc}"))

    story.append(h2("5.3 Questionario e Validacao"))
    rn_quest = [
        ["RN-010", "Questionario com 49 perguntas em 8 blocos (A.1-A.8). Bloco A.2 condicional (so se Q3=Sim)"],
        ["RN-011", "Score de aderencia calculado: 100 - (conflitos x 5) - (gaps x 10) - (incompatibilidades x 5). Aprovacao >= 85"],
        ["RN-012", "20+ regras de validacao: conflitos logicos (React+Flutter), gaps (web sem frontend), compatibilidade de stack"],
        ["RN-013", "Bloco A.12 (Q50-Q54) preenchido APENAS pelos agentes de IA, nao pelo GP"],
        ["RN-014", "Status: 'OK para ingestao' -> Admin notificado. 'Pendente de ajustes' ou 'Inconsistente' -> GP deve corrigir"],
    ]
    for rn_id, desc in rn_quest:
        story.append(bullet(f"<b>{rn_id}:</b> {desc}"))

    story.append(h2("5.4 OCG e Pilares"))
    rn_ocg = [
        ["RN-015", "Pilar 7 (Seguranca) com score < 70 = BLOQUEIO. Impede geracao de codigo ate resolucao"],
        ["RN-016", "Pilar 2 (Compliance) com score < 70 e LGPD/GDPR aplicavel = BLOQUEIO"],
        ["RN-017", "Score composto: P1(10%) + P2(15%) + P3(20%) + P4(20%) + P5(15%) + P6(10%) + P7(10%)"],
        ["RN-018", "Status OCG: READY (>=90), NEEDS_REVIEW (>=75), AT_RISK (<75), BLOCKED (P7<70 ou P2<70)"],
    ]
    for rn_id, desc in rn_ocg:
        story.append(bullet(f"<b>{rn_id}:</b> {desc}"))

    story.append(h2("5.5 Geracao de Codigo"))
    rn_code = [
        ["RN-019", "Geracao usa contexto OCG: findings criticos, requisitos de teste, checklist de compliance"],
        ["RN-020", "Provedor LLM configuravel: Anthropic (padrao), OpenAI, DeepSeek, Gemini, Grok"],
        ["RN-021", "Temperature 0.3 (baixa aleatoriedade). Max 4096 tokens por geracao"],
        ["RN-022", "Codigo gerado e armazenado como artefato no schema do projeto"],
    ]
    for rn_id, desc in rn_code:
        story.append(bullet(f"<b>{rn_id}:</b> {desc}"))
    story.append(PageBreak())

    # ========================================================================
    # 6. QUESTIONARIO
    # ========================================================================
    story.append(h1("6. Sistema de Questionario (54 Campos)"))
    story.append(p(
        "O questionario e o ponto de entrada do pipeline GCA. Sao <b>49 perguntas</b> preenchidas pelo GP "
        "(Gestor de Projeto), organizadas em <b>8 blocos tematicos</b>, mais <b>5 campos de retorno</b> "
        "(bloco A.12) preenchidos automaticamente pelos agentes de IA apos a analise."
    ))

    quest_blocks = [
        ["A.1", "Informacoes Gerais", "Q1-Q6", "Nome, slug, tipo de iniciativa, criticidade, classificacao"],
        ["A.2", "Projetos Existentes", "Q7-Q14", "Repositorio, acesso, objetivo, escopo de analise n8n (condicional: Q3=Sim)"],
        ["A.3", "Perfil de Entrega", "Q15-Q20", "Entregavel, arquitetura, modelo execucao, multi-tenant, HA, async"],
        ["A.4", "Frontend", "Q21-Q25", "Tem frontend?, tipo, stack, linguagem, requisitos"],
        ["A.5", "Backend e APIs", "Q26-Q30", "Tem backend?, linguagem, framework, tipo, requisitos"],
        ["A.6", "Dados e Mensageria", "Q31-Q38", "Banco, perfil uso, Redis, mensageria, n8n"],
        ["A.7", "IA, Seguranca, Obs.", "Q39-Q44", "Uso de IA, provedor, restricoes, controles seguranca, observabilidade"],
        ["A.8", "Testes e Entregaveis", "Q45-Q49", "Tipos teste, quality gate, QA, entregaveis pipeline, formato"],
        ["A.12", "Retorno dos Agentes", "Q50-Q54", "Restricoes, observacoes, % respondido, status, agentes validadores"],
    ]
    story.append(make_table(
        ["Bloco", "Tema", "Perguntas", "Conteudo"],
        quest_blocks,
        [14*mm, 35*mm, 18*mm, W-67*mm]
    ))

    story.append(spacer(4))
    story.append(h2("6.1 Mapeamento Pergunta -> Pilar"))
    pillar_map = [
        ["P1 - Negocio", "Q1, Q2, Q3, Q4, Q5"],
        ["P2 - Compliance", "Q6, Q42, Q46, Q47"],
        ["P3 - Escopo", "Q11, Q15, Q18-Q21, Q25, Q26, Q37, Q38, Q48, Q49"],
        ["P4 - NFR", "Q17, Q19, Q32, Q44"],
        ["P5 - Arquitetura", "Q7-Q10, Q13, Q16, Q22-Q24, Q27-Q30, Q39-Q41"],
        ["P6 - Dados", "Q31-Q36"],
        ["P7 - Seguranca", "Q43, Q45"],
    ]
    story.append(make_table(["Pilar", "Perguntas Mapeadas"], pillar_map, [35*mm, W-35*mm]))

    story.append(h2("6.2 Regras de Validacao (20+ regras)"))
    val_rules = [
        ["Conflito", "React + Flutter selecionados simultaneamente (Q23)", "Blocker"],
        ["Conflito", "Monolito + Microsservicos selecionados (Q16)", "Blocker"],
        ["Conflito", "Frontend=Sim (Q21) mas sem stack (Q23)", "Blocker"],
        ["Conflito", "Backend=Sim (Q26) mas sem linguagem (Q27)", "Blocker"],
        ["Conflito", "Microsservicos sem mensageria (Q16 vs Q35)", "Warning"],
        ["Conflito", "Multi-tenant sem RBAC (Q18 vs Q30)", "Blocker"],
        ["Conflito", "Info Restrita/Confidencial sem criptografia (Q6 vs Q43)", "Blocker"],
        ["Gap", "App web/Dashboard sem frontend habilitado (Q15 vs Q21)", "Blocker"],
        ["Gap", "API/Microsservico sem backend habilitado (Q15 vs Q26)", "Blocker"],
        ["Gap", "App persistente sem banco de dados (Q15 vs Q31)", "Blocker"],
        ["Gap", "IA nao habilitada - obrigatoria no GCA (Q39)", "Blocker"],
        ["Gap", "IA habilitada sem provedor selecionado (Q39 vs Q41)", "Blocker"],
        ["Gap", "Sem controles de seguranca selecionados (Q43)", "Blocker"],
        ["Gap", "Sem testes definidos (Q45)", "Blocker"],
        ["Gap", "Projeto existente sem repositorio (Q3 vs Q8)", "Blocker"],
    ]
    story.append(make_small_table(
        ["Tipo", "Regra", "Severidade"],
        val_rules,
        [18*mm, W-40*mm, 22*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # 7. PIPELINE OCG
    # ========================================================================
    story.append(h1("7. Pipeline OCG (8 Agentes)"))
    story.append(p(
        "O OCG (Objeto Contexto Global) e o artefato central do GCA. E gerado por um pipeline de "
        "<b>8 agentes de IA</b> que analisam o questionario e produzem um documento completo com "
        "scores por pilar, recomendacoes de stack, findings criticos, requisitos de teste e checklist de compliance."
    ))

    story.append(h2("7.1 Agentes"))
    agents = [
        ["Agent 0", "Analyzer", "Classifica respostas por pilar, extrai metadata, identifica anomalias"],
        ["Agent 1", "P1 - Negocio", "ROI, stakeholders, timeline, metricas de sucesso"],
        ["Agent 2", "P2 - Compliance", "LGPD/GDPR, PCI-DSS, regulamentacoes, residencia de dados"],
        ["Agent 3", "P3 - Escopo", "MVP, features, integracoes, risco de scope creep"],
        ["Agent 4", "P4 - NFR", "Performance, escalabilidade, SLA, monitoramento"],
        ["Agent 5", "P5 - Arquitetura", "Design patterns, stack, deployment, API design"],
        ["Agent 6", "P6 - Dados", "Banco, volumes, backup/recovery, indexacao"],
        ["Agent 7", "P7 - Seguranca", "Autenticacao, criptografia, threat model, SAST/DAST. BLOQUEANTE se < 70"],
        ["Agent 8", "Consolidator", "Agrega scores, calcula composto, gera stack recommendations, OCG final"],
    ]
    story.append(make_table(["Agente", "Especialidade", "Responsabilidade"], agents, [18*mm, 30*mm, W-48*mm]))

    story.append(h2("7.2 Score Composto"))
    story.append(p("<b>Formula:</b> P1(10%) + P2(15%) + P3(20%) + P4(20%) + P5(15%) + P6(10%) + P7(10%)"))
    score_rules = [
        ["READY", ">= 90", "Aprovado para geracao de codigo"],
        ["NEEDS_REVIEW", "75-89", "Gaps menores, pode prosseguir com cautela"],
        ["AT_RISK", "< 75", "Gaps significativos, recomenda correcoes"],
        ["BLOCKED", "P7<70 ou P2<70", "Bloqueado - seguranca ou compliance insuficiente"],
    ]
    story.append(make_table(["Status", "Criterio", "Acao"], score_rules, [28*mm, 30*mm, W-58*mm]))

    story.append(h2("7.3 Saida do OCG"))
    ocg_sections = [
        "PROJECT_PROFILE - Metadata do projeto (nome, tipo, equipe, timeline)",
        "PILLAR_SCORES - Score individual de cada pilar (0-100) com peso e status",
        "COMPOSITE_SCORE - Score geral, status de aprovacao, explicacao",
        "STACK_RECOMMENDATION - Backend, frontend, banco, cache, infra com justificativa",
        "CRITICAL_FINDINGS - Achados de alta severidade com acoes requeridas",
        "TESTING_REQUIREMENTS - Estrategia de testes (unit, integration, security, performance)",
        "COMPLIANCE_CHECKLIST - LGPD, PCI-DSS, GDPR com implementacoes detalhadas",
        "DELIVERABLES - Estrutura de codigo, documentacao, infraestrutura, testes",
        "ARCHITECTURE_OVERVIEW - Componentes, patterns, diagrama de fluxo",
        "RISK_ANALYSIS - Areas de alto risco, dependencias, riscos de timeline",
        "APPROVAL_STATUS - Pode gerar codigo? Revisao admin necessaria? Bloqueadores?",
    ]
    for s in ocg_sections:
        story.append(bullet(s))
    story.append(PageBreak())

    # ========================================================================
    # 8. GERACAO DE CODIGO
    # ========================================================================
    story.append(h1("8. Geracao de Codigo"))
    story.append(p(
        "O Code Generator do GCA utiliza LLM (Large Language Models) para gerar codigo-fonte "
        "enriquecido com o contexto completo do OCG. O fluxo integra findings criticos, "
        "requisitos de seguranca e estrategia de testes no prompt de geracao."
    ))

    story.append(h2("8.1 Fluxo"))
    codegen_steps = [
        "1. Buscar contexto do projeto (ProjectRequest, artefatos, OCG)",
        "2. Obter recomendacoes de stack (PiloterService + OCG)",
        "3. Construir prompt dinamico com metadata + OCG findings + compliance + testes",
        "4. Chamar LLM (Anthropic Claude Opus 4.6, temp=0.3, max_tokens=4096)",
        "5. Validar codigo gerado (sintaxe, qualidade, seguranca)",
        "6. Armazenar como artefato no schema do projeto",
        "7. Opcionalmente: criar branch + commit + PR no GitHub",
    ]
    for step in codegen_steps:
        story.append(bullet(step))

    story.append(h2("8.2 Provedores LLM"))
    llm_rows = [
        ["Anthropic", "Claude Opus 4.6", "Primario", "Melhor raciocinio e qualidade de codigo"],
        ["OpenAI", "GPT-4 Turbo", "Secundario", "Alternativa com bom desempenho"],
        ["DeepSeek", "DeepSeek V3", "Alternativo", "Custo menor para tarefas simples"],
        ["Gemini", "Gemini Pro", "Alternativo", "Integracao Google Cloud"],
        ["Grok", "Grok-3-mini", "Default (config)", "Equilibrio custo/qualidade"],
    ]
    story.append(make_table(["Provedor", "Modelo", "Prioridade", "Uso"], llm_rows, [22*mm, 28*mm, 22*mm, W-72*mm]))
    story.append(PageBreak())

    # ========================================================================
    # 9. SEGURANCA
    # ========================================================================
    story.append(h1("9. Seguranca e Autenticacao"))

    story.append(h2("9.1 Autenticacao"))
    story.append(p(
        "O sistema utiliza JWT (JSON Web Tokens) com algoritmo RS256 ou HS256. "
        "Access tokens expiram em 60 minutos. Refresh tokens em 7 dias. "
        "Senhas sao armazenadas com bcrypt hash."
    ))

    story.append(h2("9.2 Politica de Senha"))
    pwd_rules = [
        "Minimo 10 caracteres",
        "Pelo menos 1 letra maiuscula (A-Z)",
        "Pelo menos 1 digito (0-9)",
        "Pelo menos 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)",
    ]
    for rule in pwd_rules:
        story.append(bullet(rule))

    story.append(h2("9.3 Controles de Seguranca"))
    sec_controls = [
        ["Bloqueio de acesso", "5 tentativas falhas -> conta bloqueada. Desbloqueio manual pelo admin"],
        ["CORS restrito", "Apenas origens autorizadas: localhost:3000, :5173, gca.code-auditor.com.br"],
        ["Audit trail", "Todas operacoes registradas com hash chain imutavel (365 dias retencao)"],
        ["Criptografia", "TLS em transito. Tokens de webhook encriptados no banco"],
        ["P7 Blocking", "Pilar 7 (Seguranca) < 70 = artefato BLOQUEADO, geracao de codigo impedida"],
        ["Deteccao suspeita", "Tentativas de acesso nao autorizado rastreadas e alertas enviados"],
    ]
    story.append(make_table(["Controle", "Descricao"], sec_controls, [35*mm, W-35*mm]))
    story.append(PageBreak())

    # ========================================================================
    # 10. MAPA DE PAGINAS
    # ========================================================================
    story.append(h1("10. Mapa de Paginas do Frontend"))
    story.append(p(
        "O frontend do GCA e uma SPA (Single Page Application) construida com React 18, TypeScript e Tailwind CSS. "
        "A navegacao e organizada em areas: <b>publica</b> (login/reset), <b>admin</b> (gestao), "
        "<b>dashboard</b> (visao geral) e <b>projeto</b> (detalhe do projeto com 11 sub-paginas)."
    ))

    story.append(h2("10.1 Paginas Publicas (sem autenticacao)"))
    pub_pages = [
        ["/login", "LoginPage", "Autenticacao com email/senha. Validacao em tempo real. Eye toggle para senha."],
        ["/reset-password", "ResetPasswordPage", "2 etapas: solicitar email -> confirmar nova senha com token."],
    ]
    story.append(make_table(["Rota", "Componente", "Funcionalidade"], pub_pages, [30*mm, 32*mm, W-62*mm]))

    story.append(h2("10.2 Paginas Admin (/admin)"))
    admin_pages = [
        ["/admin", "AdminDashboardPage", "Metricas do sistema: usuarios ativos, projetos, tickets, alertas. Graficos de uso."],
        ["/admin/users", "AdminUsersPage", "Lista de GPs com contexto de projetos. Bloquear/desbloquear. Ver detalhes."],
        ["/admin/projects", "AdminProjectsPage", "Solicitacoes pendentes. Aprovar/rejeitar projetos. Provisionamento de schema."],
        ["/admin/audit", "AdminAuditPage", "Log de auditoria global. Filtros por tipo, ator, data. Hash chain imutavel."],
    ]
    story.append(make_table(["Rota", "Componente", "Funcionalidade"], admin_pages, [30*mm, 36*mm, W-66*mm]))

    story.append(h2("10.3 Paginas Gerais (autenticado)"))
    gen_pages = [
        ["/dashboard", "DashboardPage", "Visao geral do usuario: projetos recentes, metricas, atalhos rapidos."],
        ["/projects", "ProjectListPage", "Lista de projetos do usuario. Admin ve todos, GP ve os seus."],
        ["/settings", "SettingsPage", "Configuracoes pessoais: perfil, notificacoes, tema."],
        ["/security", "SecurityPage", "Configuracao de seguranca: alterar senha, sessoes ativas."],
        ["/integrations", "IntegrationsPage", "Configurar integracoes: GitHub, Slack, Teams, webhooks."],
        ["/tickets", "TicketsPage", "Abertura e acompanhamento de tickets de suporte (SAC)."],
    ]
    story.append(make_table(["Rota", "Componente", "Funcionalidade"], gen_pages, [30*mm, 32*mm, W-62*mm]))

    story.append(h2("10.4 Paginas de Projeto (/projects/:id)"))
    proj_pages = [
        ["/projects/:id", "ProjectDashPage", "Overview: metricas, equipe, status, ultimas atividades."],
        ["/projects/:id/team", "ProjectTeamPage", "Gerenciar equipe: convidar membros, atribuir perfis, revogar acesso."],
        ["/projects/:id/ocg", "OCGPage", "Visualizacao OCG com 11 dimensoes: identidade, IA, repo, integracoes, stack, compliance, artefatos, QA, equipe, entrega, historico."],
        ["/projects/:id/ingestion", "IngestionPage", "Upload de artefatos: documentos, diagramas, codigo legado."],
        ["/projects/:id/gatekeeper", "GatekeeperPage", "Avaliacao por 7 pilares. Visualizar scores, findings, bloqueios."],
        ["/projects/:id/merge", "MergeEnginePage", "Engine de merge: resolucao de conflitos, code review."],
        ["/projects/:id/arguider", "ArguiderPage", "Documentacao de decisoes tecnicas e justificativas."],
        ["/projects/:id/codegen", "CodeGeneratorPage", "Interface de geracao de codigo: selecionar linguagem, executar, revisar."],
        ["/projects/:id/qa", "QAReadinessPage", "Status de QA: cobertura, testes pendentes, quality gates."],
        ["/projects/:id/legacy", "LegacyPage", "Analise de sistema legado: scan de repo, riscos, modernizacao."],
        ["/projects/:id/roadmap", "RoadmapPage", "Roadmap do projeto: sprints, milestones, dependencias."],
        ["/projects/:id/docs", "LiveDocsPage", "Documentacao viva: gerada e atualizada automaticamente."],
    ]
    story.append(make_small_table(["Rota", "Componente", "Funcionalidade"], proj_pages, [35*mm, 32*mm, W-67*mm]))

    story.append(h2("10.5 Componentes Transversais"))
    transversal = [
        ["AppLayout", "Layout principal com sidebar de navegacao. Menu contextual por area."],
        ["Sidebar", "Menu lateral: Dashboard, Projetos, Admin (se admin), Configuracoes, Tickets."],
        ["FirstAccessModal", "Modal obrigatorio no primeiro login. Forca troca de senha. Nao e uma pagina."],
        ["ErrorBoundary", "Captura de erros React. Fallback gracioso com opcao de retry."],
        ["StatusBadge / RoleBadge", "Indicadores visuais de status (ativo, pendente, bloqueado) e perfil."],
    ]
    story.append(make_table(["Componente", "Descricao"], transversal, [35*mm, W-35*mm]))

    story.append(h2("10.6 Fluxo de Navegacao do Usuario"))
    story.append(p("<b>Primeiro acesso (novo usuario):</b>"))
    story.append(p(
        "Email de convite &rarr; /login &rarr; FirstAccessModal (troca senha) &rarr; /dashboard &rarr; /projects/:id"
    ))
    story.append(p("<b>Fluxo normal (usuario existente):</b>"))
    story.append(p(
        "/login &rarr; /dashboard &rarr; /projects (lista) &rarr; /projects/:id (detalhe) &rarr; sub-paginas"
    ))
    story.append(p("<b>Fluxo admin:</b>"))
    story.append(p(
        "/login &rarr; /admin (dashboard) &rarr; /admin/projects (aprovar) &rarr; /admin/users (gerenciar) &rarr; /admin/audit"
    ))
    story.append(p("<b>Fluxo GP (submissao de questionario):</b>"))
    story.append(p(
        "/projects/:id &rarr; /projects/:id/ocg (preencher questionario) &rarr; Aguardar analise &rarr; "
        "/projects/:id/gatekeeper (ver resultado) &rarr; /projects/:id/codegen (gerar codigo)"
    ))
    story.append(PageBreak())

    # ========================================================================
    # 11. ENDPOINTS DA API
    # ========================================================================
    story.append(h1("11. Endpoints da API"))
    story.append(p("Base URL: <b>/api/v1</b>. Total: <b>40+ endpoints</b> em 16 routers."))

    api_rows = [
        ["POST", "/auth/bootstrap-admin", "Criar primeiro admin (sistema vazio)"],
        ["POST", "/auth/login", "Autenticacao email/senha"],
        ["POST", "/auth/refresh", "Renovar access token"],
        ["GET", "/auth/me", "Perfil do usuario autenticado"],
        ["POST", "/auth/change-password", "Alterar senha"],
        ["POST", "/auth/reset-password", "Solicitar reset de senha"],
        ["POST", "/auth/change-first-password", "Troca obrigatoria no primeiro acesso"],
        ["GET", "/auth/password-requirements", "Regras de senha para UI"],
        ["GET", "/admin/users", "Listar todos usuarios"],
        ["POST", "/admin/projects", "Criar solicitacao de projeto"],
        ["GET", "/admin/projects/pending", "Listar projetos pendentes"],
        ["POST", "/admin/projects/:id/approve", "Aprovar projeto (cria schema)"],
        ["POST", "/admin/projects/:id/reject", "Rejeitar projeto"],
        ["POST", "/questionnaires/", "Submeter questionario (54 campos)"],
        ["GET", "/questionnaires/:id/status", "Status com resultado da analise"],
        ["POST", "/agents/analyze", "Agent 0: Classificar questionario"],
        ["POST", "/agents/pillar/:id", "Agents 1-7: Analisar pilar especifico"],
        ["POST", "/agents/consolidate", "Agent 8: Consolidar OCG final"],
        ["GET", "/ocg/", "Listar OCGs gerados"],
        ["POST", "/code-generation/project", "Gerar codigo completo do projeto"],
        ["POST", "/code-generation/module", "Gerar modulo especifico"],
        ["POST", "/code-generation/validate-provider", "Validar configuracao LLM"],
        ["GET", "/code-generation/history/:id", "Historico de geracoes"],
        ["POST", "/validation/syntax", "Validar sintaxe"],
        ["POST", "/validation/quality", "Metricas de qualidade"],
        ["POST", "/validation/security", "Scan de seguranca"],
        ["GET", "/projects/", "Listar projetos"],
        ["POST", "/projects/:id/invite", "Convidar membro"],
        ["POST", "/projects/:id/accept-invite", "Aceitar convite"],
        ["POST", "/webhooks/questionnaire", "Webhook n8n para analise"],
        ["POST", "/webhooks/ocg-result", "Callback de resultado OCG"],
        ["GET", "/dashboard/metrics", "Metricas do projeto"],
        ["GET", "/dashboard/summary", "Resumo executivo"],
        ["POST", "/github/auth/token", "Autenticar GitHub"],
        ["POST", "/github/commits/create", "Criar commit"],
        ["POST", "/github/pullrequests/create", "Criar PR"],
        ["GET", "/health", "Health check"],
    ]
    story.append(make_small_table(
        ["Metodo", "Endpoint", "Descricao"],
        api_rows,
        [14*mm, 55*mm, W-69*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # 12. MODELO DE DADOS
    # ========================================================================
    story.append(h1("12. Modelo de Dados"))
    story.append(p("PostgreSQL 16 com <b>26 tabelas</b> e <b>325+ colunas</b>. Dois tipos de schema:"))
    story.append(bullet("<b>Schema global (public):</b> users, organizations, projects, questionnaires, ocg, audit_log_global, etc."))
    story.append(bullet("<b>Schema por projeto (proj_{slug}):</b> artifacts, artifact_evaluations, pillar_configuration, ogc_versions, audit_log"))

    story.append(h2("12.1 Tabelas Principais"))
    db_tables = [
        ["users", "11 cols", "Usuarios globais. Email unico, bcrypt hash, first_access, admin flag"],
        ["organizations", "7 cols", "Multi-tenancy. Owner, membros com roles"],
        ["projects", "10 cols", "Metadata. Status: DRAFT -> PROVISIONING -> ACTIVE -> ARCHIVED"],
        ["project_requests", "14 cols", "Solicitacoes de criacao. Aprovacao cria schema isolado"],
        ["project_members", "10 cols", "Equipe do projeto. Roles: gp, tech_lead, dev, qa, compliance, viewer"],
        ["questionnaires", "15 cols", "Respostas JSON, score aderencia, validacoes, status"],
        ["ocg", "16 cols", "Scores P1-P7, score geral, OCG JSON completo, status"],
        ["ocg_analysis_log", "8 cols", "Audit trail dos agentes: tokens usados, latencia, erros"],
        ["artifacts", "14 cols", "Documentos, codigo, testes. Status: DRAFT -> REVIEW -> APPROVED"],
        ["artifact_evaluations", "18 cols", "Scores por pilar, pesos, p7_blocked, code_gen_allowed"],
        ["onboarding_progress", "30 cols", "5 etapas com status individual e dados de config"],
        ["team_invites", "12 cols", "Convites com token, expiracao, aceitacao"],
        ["support_tickets", "11 cols", "SAC com severidade, SLA, respostas do admin"],
        ["audit_log_global", "9 cols", "Trail imutavel com hash chain. 365 dias retencao"],
    ]
    story.append(make_small_table(
        ["Tabela", "Colunas", "Descricao"],
        db_tables,
        [32*mm, 14*mm, W-46*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # 13. INTEGRACOES
    # ========================================================================
    story.append(h1("13. Integracoes Externas"))

    integrations = [
        ["Anthropic (Claude)", "SDK Python", "8 agentes OCG, geracao de codigo, analise de artefatos"],
        ["OpenAI / DeepSeek / Gemini / Grok", "HTTP API", "Provedores LLM alternativos para geracao de codigo"],
        ["GitHub", "REST API + Webhooks", "Autenticacao, repos, branches, commits, PRs, deploy (Actions)"],
        ["n8n", "Webhooks", "Orquestracao de analise: questionario -> agentes -> OCG -> notificacoes"],
        ["SMTP (Email)", "Python smtplib", "Convites, reset de senha, aprovacoes, notificacoes"],
        ["Redis", "redis-py", "Cache de sessoes, rate limiting, pub/sub, locks distribuidos"],
        ["Piloter API", "HTTP", "Analise de codigo legado, recomendacoes de stack"],
        ["Slack / Teams", "Bot API", "Alertas de sistema, notificacoes de seguranca"],
        ["Cloudflare", "Reverse Proxy", "CDN, SSL, protecao DDoS. gca.code-auditor.com.br"],
    ]
    story.append(make_table(
        ["Integracao", "Protocolo", "Uso"],
        integrations,
        [38*mm, 28*mm, W-66*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # 14. ESTRATEGIA DE TESTES
    # ========================================================================
    story.append(h1("14. Estrategia de Testes"))
    story.append(p(
        "O GCA possui <b>54 testes automatizados</b> (100% passando) distribuidos em 5 suites. "
        "A estrategia segue a piramide de testes: unitarios na base, integracao no meio, E2E no topo."
    ))

    test_suites = [
        ["test_admin_service.py", "28", "Unitario", "CRUD de usuarios, tickets, dashboard, webhooks, alertas"],
        ["test_auth_reset_password.py", "8", "Integracao", "Login, reset senha, convites, questionario webhook, conflitos"],
        ["test_e2e_pipeline_fase6.py", "6", "E2E", "Pipeline completo: Questionario -> OCG -> CodeGen. Benchmarks."],
        ["test_ocg_codegen_integration.py", "5", "Integracao", "OCG context no CodeGen, backward compatibility, error handling"],
        ["test_ocg_e2e.py", "7", "E2E", "Pipeline OCG: Analyzer -> Pilares (paralelo) -> Consolidator"],
    ]
    story.append(make_table(
        ["Suite", "Testes", "Tipo", "Cobertura"],
        test_suites,
        [42*mm, 12*mm, 20*mm, W-74*mm]
    ))

    story.append(h2("14.1 Cobertura por Area"))
    coverage = [
        ["Autenticacao", "Login, refresh, reset, first access, password validation", "100%"],
        ["Admin", "CRUD usuarios, projetos, tickets, metricas, webhooks", "100%"],
        ["Questionario", "Submissao, validacao 20+ regras, formato numerico + legado", "100%"],
        ["OCG Pipeline", "Analyzer, 7 pilares paralelos, consolidator, saving", "100%"],
        ["Code Generation", "Com OCG, sem OCG, error handling, mock LLM", "100%"],
        ["Webhooks", "Analise questionario, deteccao conflitos, retorno A.12", "100%"],
    ]
    story.append(make_table(["Area", "Cenarios", "Pass Rate"], coverage, [28*mm, W-50*mm, 22*mm]))
    story.append(PageBreak())

    # ========================================================================
    # 15. GLOSSARIO
    # ========================================================================
    story.append(h1("15. Glossario"))

    glossary = [
        ["GCA", "Gestao de Codificacao Assistida - a plataforma"],
        ["OCG", "Objeto Contexto Global - documento gerado pelos 8 agentes com scores, stack, findings"],
        ["GP", "Gestor de Projeto - responsavel pelo preenchimento do questionario"],
        ["Pilar", "Uma das 7 dimensoes de avaliacao: Negocio, Compliance, Escopo, NFR, Arquitetura, Dados, Seguranca"],
        ["Score Composto", "Media ponderada dos 7 pilares. Formula: P1(10%)+P2(15%)+P3(20%)+P4(20%)+P5(15%)+P6(10%)+P7(10%)"],
        ["BLOQUEIO (P7)", "Quando Pilar 7 (Seguranca) tem score < 70, impede geracao de codigo"],
        ["Score de Aderencia", "Pontuacao do questionario: 100 - penalidades. Aprovacao >= 85"],
        ["Bloco A.12", "Campos Q50-Q54 preenchidos pelos agentes apos analise (restricoes, obs, status)"],
        ["Multi-Tenancy", "Isolamento por schema PostgreSQL: cada projeto tem schema proprio (proj_{slug})"],
        ["n8n", "Ferramenta de automacao de workflows usada para orquestrar analise de questionarios"],
        ["Piloter", "API externa para analise de codigo legado e recomendacoes de stack"],
        ["RBAC", "Role-Based Access Control - controle de acesso baseado em perfis"],
        ["LLM", "Large Language Model - modelo de linguagem (Claude, GPT-4, etc) usado para geracao de codigo"],
        ["JWT", "JSON Web Token - padrao de autenticacao usado pelo GCA (RS256/HS256)"],
        ["LGPD", "Lei Geral de Protecao de Dados - legislacao brasileira de privacidade"],
    ]
    story.append(make_table(["Termo", "Definicao"], glossary, [30*mm, W-30*mm]))
    story.append(PageBreak())

    # ========================================================================
    # ANEXO A: FLUXOS DETALHADOS (PARA FIGMA MAKE)
    # ========================================================================
    story.append(h1("Anexo A: Fluxos Detalhados para Prototipacao"))
    story.append(p(
        "Este anexo detalha cada fluxo de usuario com nivel suficiente para geracao de telas no Figma Make. "
        "Cada step inclui: <b>tela</b>, <b>campos com validacao</b>, <b>estados</b>, <b>transicoes</b>, "
        "<b>mensagens de erro/sucesso</b> e <b>regras de negocio vinculadas</b>. "
        "O arquivo <b>GCA_FIGMA_SPEC.json</b> contem estas mesmas definicoes em formato estruturado para importacao direta."
    ))

    # --- FLOW 1: PRIMEIRO ACESSO ---
    story.append(h2("A.1 Fluxo: Primeiro Acesso (Convite ate Senha Definitiva)"))
    story.append(p("<b>Regras vinculadas:</b> RN-001, RN-002, RN-005, RN-008"))
    story.append(p("<b>Atores:</b> Admin/GP (convida), Usuario convidado (aceita), Sistema (valida)"))
    story.append(spacer(2))

    flow1_steps = [
        ["1", "Admin/GP", "Envia convite",
         "<b>Pagina:</b> ProjectTeamPage (/projects/:id/team)\n"
         "<b>Campos:</b> Email* (email), Papel* (select: tech_lead, dev_senior, dev_pleno, qa, compliance)\n"
         "<b>Botao:</b> 'Convidar' (disabled se email vazio)\n"
         "<b>API:</b> POST /projects/:id/invite\n"
         "<b>Resultado:</b> team_invites criado (token 32 bytes, expira 7 dias). Email enviado com link + senha temporaria.\n"
         "<b>Sucesso:</b> Toast verde 'Convite enviado com sucesso!'\n"
         "<b>Erro:</b> Mensagem inline vermelha"],

        ["2", "Convidado", "Clica link no email",
         "<b>Pagina:</b> N/A (redirect externo)\n"
         "<b>API:</b> POST /projects/:id/accept-invite { token }\n"
         "<b>Validacoes:</b> Token valido? Nao expirado? Nao usado?\n"
         "<b>Se OK:</b> Usuario criado (first_access_completed=false), project_member vinculado. Redirect -> /login\n"
         "<b>Se erro:</b> Pagina de erro: 'Convite expirado ou invalido. Solicite um novo convite ao GP.'"],

        ["3", "Convidado", "Faz login",
         "<b>Pagina:</b> LoginPage (/login)\n"
         "<b>Campos:</b> Email (preenchido do convite), Senha (temporaria do email)\n"
         "<b>API:</b> POST /auth/login { email, password }\n"
         "<b>Resposta:</b> { access_token, user: { first_access_completed: false } }\n"
         "<b>Transicao:</b> Sistema detecta first_access_completed=false -> abre FirstAccessModal"],

        ["4", "Convidado", "Define senha definitiva",
         "<b>Componente:</b> FirstAccessModal (modal, nao pagina)\n"
         "<b>Overlay:</b> Fundo escuro, click-outside bloqueado\n"
         "<b>Titulo:</b> 'Definir Senha Segura'\n"
         "<b>Warning box:</b> Amarelo: 'Esta acao e obrigatoria...'\n"
         "<b>Campo 1:</b> Nova Senha* (password, eye toggle)\n"
         "  Validacao em tempo real com icones:\n"
         "  - CheckCircle2 verde: regra atendida\n"
         "  - AlertCircle vermelho: regra nao atendida\n"
         "  Regras: 10+ chars | 1 maiuscula | 1 digito | 1 especial\n"
         "<b>Campo 2:</b> Confirmar Senha* (password, eye toggle)\n"
         "  Validacao: deve ser identica ao Campo 1\n"
         "<b>Botao:</b> 'Salvar e Continuar' (disabled ate validacao completa)\n"
         "<b>API:</b> POST /auth/change-first-password { temporary_password, new_password }\n"
         "<b>Sucesso:</b> Modal fecha, toast 'Senha alterada!', redirect /dashboard\n"
         "<b>Erro:</b> Box vermelho dentro do modal com mensagem"],

        ["5", "Sistema", "Atualiza estado",
         "<b>Acoes do backend:</b>\n"
         "- first_access_completed = true\n"
         "- password_hash atualizado (bcrypt)\n"
         "- password_changed_at = agora\n"
         "- Senha temporaria invalidada\n"
         "<b>Proximo:</b> Usuario acessa /dashboard normalmente"],
    ]
    story.append(make_small_table(
        ["Step", "Ator", "Acao", "Detalhes da Tela / API / Validacao"],
        flow1_steps,
        [10*mm, 18*mm, 22*mm, W-50*mm]
    ))
    story.append(PageBreak())

    # --- FLOW 2: RESET DE SENHA ---
    story.append(h2("A.2 Fluxo: Recuperacao de Senha"))
    story.append(p("<b>Regras vinculadas:</b> RN-001, RN-003"))
    story.append(p("<b>Pagina:</b> ResetPasswordPage (/reset-password) com 3 estados internos"))
    story.append(spacer(2))

    flow2_steps = [
        ["Estado 1\n'request'", "Solicitar reset",
         "<b>Titulo:</b> 'Recuperar Senha'\n"
         "<b>Subtitulo:</b> 'Informe seu email para receber o link'\n"
         "<b>Campo:</b> Email* (type=email, required)\n"
         "<b>Botao:</b> 'Enviar Link de Recuperacao' (icon: Mail)\n"
         "<b>API:</b> POST /auth/reset-password { email }\n"
         "<b>Resposta:</b> Mensagem generica (seguranca): 'Se o email existir, voce recebera um link'\n"
         "<b>Nota:</b> NUNCA revelar se email existe ou nao (OWASP)\n"
         "<b>Side-effect:</b> reset_tokens criado (token 32 bytes, expira 1 hora, uso unico)"],

        ["Estado 2\n'verify'", "Verificar token",
         "<b>Trigger:</b> URL contem ?token=xyz\n"
         "<b>Acao automatica:</b> POST /auth/verify-reset-token { token }\n"
         "<b>UI:</b> Spinner 'Verificando token...'\n"
         "<b>Se valido:</b> Avanca para Estado 3\n"
         "<b>Se invalido:</b> Box vermelho: 'Token invalido ou expirado. Solicite um novo link.' Botao: 'Voltar'"],

        ["Estado 3\n'confirm'", "Definir nova senha",
         "<b>Titulo:</b> 'Definir Nova Senha'\n"
         "<b>Campo 1:</b> Nova Senha* (password, eye toggle)\n"
         "  Validacao identica ao FirstAccessModal:\n"
         "  10+ chars, maiuscula, digito, especial\n"
         "  Indicadores em tempo real (CheckCircle2 / AlertCircle)\n"
         "<b>Campo 2:</b> Confirmar Senha* (match validation)\n"
         "<b>Botao:</b> 'Alterar Senha' (icon: Lock, disabled se invalido)\n"
         "<b>API:</b> POST /auth/reset-password-confirm { token, new_password }\n"
         "<b>Sucesso:</b> Toast verde, redirect /login em 2 segundos\n"
         "<b>Erro:</b> Box vermelho com mensagem da API"],
    ]
    story.append(make_small_table(
        ["Estado", "Acao", "Detalhes Completos"],
        flow2_steps,
        [20*mm, 25*mm, W-45*mm]
    ))
    story.append(PageBreak())

    # --- FLOW 3: CRIACAO DE PROJETO ---
    story.append(h2("A.3 Fluxo: Criacao e Aprovacao de Projeto"))
    story.append(p("<b>Regras vinculadas:</b> RN-006, RN-007, RN-009"))
    story.append(spacer(2))

    flow3_steps = [
        ["1", "GP", "Solicita projeto",
         "<b>Pagina:</b> Formulario de nova solicitacao\n"
         "<b>Campos:</b>\n"
         "  - Nome do Projeto* (text, max 100 chars)\n"
         "  - Slug* (auto-gerado do nome, editavel)\n"
         "  - Descricao (textarea, max 500 chars)\n"
         "  - Output Profile (select: web_app, api, desktop, mobile, improvement)\n"
         "<b>API:</b> POST /admin/projects\n"
         "<b>Resultado:</b> project_requests com status=PENDING"],

        ["2", "Admin", "Visualiza e aprova/rejeita",
         "<b>Pagina:</b> AdminProjectsPage (/admin/projects)\n"
         "<b>Secao 'Pendentes':</b> Alert box azul com Clock icon\n"
         "  Para cada solicitacao:\n"
         "  - Nome, descricao, solicitante, output, data\n"
         "  - Botao 'Rejeitar' (vermelho, XCircle) -> Confirm dialog -> POST /reject\n"
         "  - Botao 'Aprovar e Liberar' (verde, CheckCircle) -> POST /approve\n"
         "<b>Apos aprovacao:</b> Spinner 'Provisionando schema...' -> Status PROVISIONING -> ACTIVE"],

        ["3", "Sistema", "Provisiona schema isolado",
         "<b>Acoes automaticas:</b>\n"
         "- Cria schema PostgreSQL: proj_{slug}\n"
         "- Cria tabelas tenant: artifacts, evaluations, pillar_config, audit_log\n"
         "- Gera senha inicial para GP (bcrypt)\n"
         "- project.status = ACTIVE\n"
         "- Envia email ao GP com credenciais"],

        ["4", "GP", "Onboarding 5 etapas",
         "<b>Regra RN-007:</b> Etapa seguinte BLOQUEADA ate anterior concluida\n"
         "<b>Etapa 1 - Repositorio:</b>\n"
         "  Campos: Provider (GitHub/GitLab), URL do repo, Access Token\n"
         "  Validacao: API call para verificar token\n"
         "<b>Etapa 2 - SMTP:</b>\n"
         "  Campos: Host, Port, User, Password, From Email\n"
         "  Validacao: Email de teste enviado\n"
         "<b>Etapa 3 - Equipe:</b>\n"
         "  Formulario de convite (reutiliza ProjectTeamPage)\n"
         "  Repeatable: pode convidar N membros\n"
         "<b>Etapa 4 - Arquitetura:</b>\n"
         "  Campos: Pattern, Deploy model, Scalability\n"
         "  Trigger: Analise n8n/Piloter\n"
         "<b>Etapa 5 - Stack:</b>\n"
         "  Campos: Language, Framework, Database, Frontend\n"
         "  Conclusao: onboarding_progress.is_completed = true"],
    ]
    story.append(make_small_table(
        ["Step", "Ator", "Acao", "Detalhes da Tela / API / Validacao"],
        flow3_steps,
        [10*mm, 14*mm, 24*mm, W-48*mm]
    ))
    story.append(PageBreak())

    # --- FLOW 4: QUESTIONARIO -> OCG -> CODIGO ---
    story.append(h2("A.4 Fluxo: Questionario -> OCG -> Geracao de Codigo"))
    story.append(p("<b>Regras vinculadas:</b> RN-010 a RN-022"))
    story.append(p("Este e o fluxo principal do GCA. Detalha cada tela e decisao do pipeline."))
    story.append(spacer(2))

    flow4_steps = [
        ["1", "GP", "Preenche questionario",
         "<b>Pagina:</b> OCGPage (/projects/:id/ocg)\n"
         "<b>Layout:</b> Wizard multi-step com 8 blocos\n"
         "<b>Navegacao:</b> Tabs ou stepper horizontal (A.1 -> A.8)\n"
         "<b>Cada bloco:</b>\n"
         "  - Titulo e descricao do bloco\n"
         "  - Perguntas com tipo (text, single-select, multi-select)\n"
         "  - Indicador de preenchimento (X/Y respondidas)\n"
         "  - Botao 'Proximo' / 'Anterior' / 'Salvar rascunho'\n"
         "<b>Bloco A.2:</b> Visivel APENAS se Q3='Sim' (projeto existente)\n"
         "<b>Ultimo bloco:</b> Botao 'Enviar para Analise' (submit)\n"
         "<b>API:</b> POST /questionnaires/ { project_id, gp_email, responses }\n"
         "<b>Formato responses:</b> { '1': 'valor', '2': 'valor', ... '49': ['opcao1', 'opcao2'] }"],

        ["2", "Sistema", "Valida e calcula score",
         "<b>Processamento (servidor):</b>\n"
         "- 20+ regras de conflito/gap aplicadas\n"
         "- Score calculado: 100 - penalidades\n"
         "- Campos problematicos destacados (highlightedFields)\n\n"
         "<b>Retorno A.12 (campos 50-54):</b>\n"
         "  Q50: Restricoes identificadas\n"
         "  Q51: Observacoes + acoes necessarias para o GP\n"
         "  Q52: Percentual respondido\n"
         "  Q53: Status ('OK para ingestao' | 'Pendente de ajustes' | 'Inconsistente')\n"
         "  Q54: Agentes validadores\n\n"
         "<b>Decisao:</b>\n"
         "  Se Q53='OK para ingestao': Admin notificado, pipeline OCG inicia\n"
         "  Se Q53='Pendente': GP ve observacoes e corrige campos\n"
         "  Se Q53='Inconsistente': GP ve erros blockers com sugestoes de correcao"],

        ["3", "Sistema", "Pipeline OCG (8 agentes)",
         "<b>Pagina:</b> OCGPage com indicador de progresso\n"
         "<b>UI durante processamento:</b>\n"
         "  - Progress bar geral\n"
         "  - Status por agente: 'Analisando...', 'Concluido', 'Aguardando'\n"
         "  - Tempo estimado: 2-5 minutos\n\n"
         "<b>Pipeline:</b>\n"
         "  1. Agent 0 (Analyzer): Classifica por pilar -> 10s\n"
         "  2. Agents 1-7 (Paralelo): Avaliam pilares -> 30-60s cada\n"
         "  3. Agent 8 (Consolidator): Gera OCG final -> 30-60s\n\n"
         "<b>Saida:</b> OCG completo salvo no banco"],

        ["4", "GP/Admin", "Revisa OCG no Gatekeeper",
         "<b>Pagina:</b> GatekeeperPage (/projects/:id/gatekeeper)\n"
         "<b>Secoes da tela:</b>\n"
         "  1. Radar chart com 7 pilares (scores 0-100)\n"
         "  2. Score composto com badge (READY/NEEDS_REVIEW/AT_RISK/BLOCKED)\n"
         "  3. Stack recomendado (backend, frontend, DB, cache, infra)\n"
         "  4. Findings criticos com severidade e acoes\n"
         "  5. Checklist de compliance (LGPD, PCI-DSS)\n"
         "  6. Requisitos de teste\n\n"
         "<b>RN-015:</b> Se P7 < 70, badge VERMELHO 'BLOCKED'\n"
         "  Botao 'Gerar Codigo' DESABILITADO com tooltip explicativo\n"
         "  Mensagem: 'Seguranca insuficiente. Corrija os findings de P7.'"],

        ["5", "GP", "Gera codigo",
         "<b>Pagina:</b> CodeGeneratorPage (/projects/:id/codegen)\n"
         "<b>Pre-condicao:</b> OCG com status READY ou NEEDS_REVIEW (nao BLOCKED)\n"
         "<b>Campos:</b>\n"
         "  - Linguagem (auto-filled do OCG, editavel)\n"
         "  - Arquitetura (auto-filled do OCG, editavel)\n"
         "  - Provedor LLM (select: Anthropic, OpenAI, DeepSeek, Gemini, Grok)\n"
         "  - ocg_id (auto-filled, hidden)\n"
         "<b>Botao:</b> 'Gerar Codigo' -> POST /code-generation/project\n"
         "<b>UI durante geracao:</b> Spinner + log de progresso\n"
         "<b>Resultado:</b> Code viewer com syntax highlighting\n"
         "<b>Acoes pos-geracao:</b>\n"
         "  - 'Copiar Codigo' -> clipboard\n"
         "  - 'Salvar como Artefato' -> salva no schema\n"
         "  - 'Publicar no GitHub' -> cria branch + commit + PR"],
    ]
    story.append(make_small_table(
        ["Step", "Ator", "Acao", "Detalhes Completos (Tela / API / Validacao / UI States)"],
        flow4_steps,
        [10*mm, 14*mm, 24*mm, W-48*mm]
    ))
    story.append(PageBreak())

    # ========================================================================
    # ANEXO B: WIREFRAMES TEXTUAIS
    # ========================================================================
    story.append(h1("Anexo B: Wireframes Textuais das Telas"))
    story.append(p(
        "Wireframes textuais (ASCII) de cada tela principal para referencia rapida. "
        "Use junto com GCA_FIGMA_SPEC.json para geracao no Figma Make."
    ))

    story.append(h2("B.1 LoginPage"))
    story.append(Paragraph("""<font face="Courier" size="7" color="#334155">
+---------------------------+-------------------------------+<br/>
|   [Code2 icon]            |                               |<br/>
|   GCA                     |   Email                       |<br/>
|   Gestao de Codificacao   |   [_____________________]     |<br/>
|                           |                               |<br/>
|   * 7 Pilares             |   Senha          [Eye toggle] |<br/>
|   * Code Gen com IA       |   [_____________________]     |<br/>
|   * QA Automatizado       |                               |<br/>
|   * Multi-tenant          |   Requisitos:                 |<br/>
|                           |   * 10+ caracteres            |<br/>
|                           |   * 1 maiuscula               |<br/>
|                           |   * 1 numero                  |<br/>
|                           |   * 1 especial                |<br/>
|                           |                               |<br/>
|                           |   [====== Entrar ======]      |<br/>
|                           |                               |<br/>
|                           |   Esqueci minha senha &gt;       |<br/>
+---------------------------+-------------------------------+<br/>
</font>""", CODE_STYLE))

    story.append(h2("B.2 FirstAccessModal (sobrepoe qualquer pagina)"))
    story.append(Paragraph("""<font face="Courier" size="7" color="#334155">
+-- Overlay escuro (bloqueado) --------------------------+<br/>
|                                                        |<br/>
|   +------ Modal (500px, centralizado) --------+       |<br/>
|   |  [Shield icon] Definir Senha Segura       |       |<br/>
|   |  Por seguranca, crie uma nova senha.      |       |<br/>
|   |                                            |       |<br/>
|   |  +-- Warning (amarelo) ---------------+   |       |<br/>
|   |  | [!] Esta acao e obrigatoria.       |   |       |<br/>
|   |  | Senha temporaria sera invalidada.  |   |       |<br/>
|   |  +------------------------------------+   |       |<br/>
|   |                                            |       |<br/>
|   |  Nova Senha *           [Eye toggle]      |       |<br/>
|   |  [_________________________]               |       |<br/>
|   |  [v] 10+ caracteres                       |       |<br/>
|   |  [v] 1 letra maiuscula                    |       |<br/>
|   |  [x] 1 numero            (vermelho)       |       |<br/>
|   |  [x] 1 caractere especial (vermelho)      |       |<br/>
|   |                                            |       |<br/>
|   |  Confirmar Senha *      [Eye toggle]      |       |<br/>
|   |  [_________________________]               |       |<br/>
|   |  [x] Senhas nao conferem  (vermelho)      |       |<br/>
|   |                                            |       |<br/>
|   |  [==== Salvar e Continuar ====]           |       |<br/>
|   |  (disabled ate tudo verde)                 |       |<br/>
|   +--------------------------------------------+       |<br/>
|                                                        |<br/>
+--------------------------------------------------------+<br/>
</font>""", CODE_STYLE))

    story.append(h2("B.3 Sidebar (expandida)"))
    story.append(Paragraph("""<font face="Courier" size="7" color="#334155">
+-- Sidebar (240px) --------+<br/>
| [Code2] GCA         [&lt;]  |<br/>
| Gestao de Codigo          |<br/>
+---------------------------+<br/>
| [Avatar] Rafael Mendes    |<br/>
| [Admin badge]             |<br/>
+---------------------------+<br/>
| ADMINISTRACAO             |<br/>
| [=] Dashboard Global      |<br/>
| [F] Projetos              |<br/>
| [U] Usuarios              |<br/>
| [S] Auditoria Global      |<br/>
+---------------------------+<br/>
| MEUS PROJETOS        [v]  |<br/>
| * E-Commerce         [oo] |<br/>
|   |- Dashboard             |<br/>
|   |- OCG                   |<br/>
|   |- M4 Ingestao           |<br/>
|   |- M5 Gatekeeper         |<br/>
|   |- M6 Merge              |<br/>
|   |- M7 Arguidor           |<br/>
|   |- M8 Code Gen           |<br/>
|   |- M9 QA                 |<br/>
|   |- M10 Legado            |<br/>
|   |- M11 Roadmap           |<br/>
|   |- M12 Docs              |<br/>
| * Outro Projeto       [o]  |<br/>
| &gt; Ver todos os projetos    |<br/>
+---------------------------+<br/>
| [LogOut] Sair             |<br/>
+---------------------------+<br/>
</font>""", CODE_STYLE))

    story.append(h2("B.4 ProjectTeamPage (Convites)"))
    story.append(Paragraph("""<font face="Courier" size="7" color="#334155">
+-- Convidar Novo Membro --------+<br/>
| Email do Membro *  | Papel *        | [Convidar]  |<br/>
| [dev@empresa.com ] | [Dev Pleno v]  | (disabled)  |<br/>
+----------------------------------------------------|<br/>
<br/>
+-- Convites Pendentes (2) ------+<br/>
| joao@emp.com   | [Dev Senior] | Expira: 14/04 | Pendente |<br/>
| maria@emp.com  | [QA]         | Expira: 14/04 | Pendente |<br/>
+----------------------------------------------------|<br/>
<br/>
+-- Membros da Equipe (3) ------+<br/>
| [R] Rafael   | [GP]        | Desde 01/03 | APPROVE_CODE |<br/>
| [B] Bruno    | [Tech Lead] | Desde 05/03 | OVERRIDE_GK  |<br/>
| [F] Fernanda | [Dev Senior]| Desde 10/03 |              |<br/>
+----------------------------------------------------|<br/>
<br/>
[i] Convites expiram em 7 dias. Membros receberao email.<br/>
</font>""", CODE_STYLE))

    story.append(h2("B.5 GatekeeperPage (Resultado OCG)"))
    story.append(Paragraph("""<font face="Courier" size="7" color="#334155">
+-- Score Composto: 86.7 ---- [READY] ----+<br/>
|                                          |<br/>
|  Radar Chart (7 pilares)   | Stack Rec.  |<br/>
|       P1: 88               | BE: Python  |<br/>
|      /    \\                | FW: FastAPI |<br/>
|    P7:94  P2:92            | DB: PgSQL   |<br/>
|    |        |              | Cache: Redis|<br/>
|    P6:82  P3:85            | Infra: AWS  |<br/>
|      \\    /                |             |<br/>
|       P5:86                |             |<br/>
|        P4:78 [!]           |             |<br/>
|                                          |<br/>
+-- Critical Findings ---------+<br/>
| [!] P4: Load testing nao planejado       |<br/>
| [i] P7: Seguranca forte (94)            |<br/>
| [i] P2: LGPD compliance OK              |<br/>
+------------------------------------------+<br/>
<br/>
+-- Compliance Checklist ------+<br/>
| [v] LGPD     | REQUIRED | Implementacao detalhada |<br/>
| [v] PCI-DSS  | REQUIRED | Stripe (sem cartao local)|<br/>
| [-] GDPR     | CONDICIONAL | Se usuarios EU       |<br/>
+------------------------------------------+<br/>
<br/>
[==== Gerar Codigo ====]  (habilitado se nao BLOCKED)<br/>
</font>""", CODE_STYLE))
    story.append(PageBreak())

    # ========================================================================
    # ANEXO C: MAPEAMENTO JSON -> REGRAS
    # ========================================================================
    story.append(h1("Anexo C: Referencia Cruzada JSON-Regras"))
    story.append(p(
        "O arquivo <b>GCA_FIGMA_SPEC.json</b> contem a especificacao completa de UI em formato estruturado. "
        "Cada componente referencia regras de negocio (RN-XXX) para rastreabilidade."
    ))
    story.append(spacer(2))

    json_mapping = [
        ["GCA_FIGMA_SPEC.json", "pages.loginPage", "Login com email/senha, redirecionamentos", "RN-001, RN-004"],
        ["GCA_FIGMA_SPEC.json", "pages.resetPasswordPage", "3 estados (request, verify, confirm)", "RN-001, RN-003"],
        ["GCA_FIGMA_SPEC.json", "globalComponents.firstAccessModal", "Modal obrigatorio, validacao em tempo real", "RN-001, RN-002"],
        ["GCA_FIGMA_SPEC.json", "globalComponents.sidebar", "Menu com role-based visibility", "RN-002, RN-009"],
        ["GCA_FIGMA_SPEC.json", "pages.adminProjectsPage", "Aprovacao/rejeicao de projetos", "RN-006, RN-009"],
        ["GCA_FIGMA_SPEC.json", "pages.adminUsersPage", "Gestao de GPs, bloqueio de acesso", "RN-002, RN-004"],
        ["GCA_FIGMA_SPEC.json", "pages.projectTeamPage", "Convites com token de 7 dias", "RN-005, RN-008"],
        ["GCA_FIGMA_SPEC.json", "flows.firstAccessFlow", "5 steps: convite -> login -> modal -> senha", "RN-001, RN-002, RN-005, RN-008"],
        ["GCA_FIGMA_SPEC.json", "flows.passwordResetFlow", "3 states: request -> verify -> confirm", "RN-001, RN-003"],
        ["GCA_FIGMA_SPEC.json", "flows.projectCreationFlow", "Solicitacao -> aprovacao -> onboarding", "RN-006, RN-007, RN-009"],
        ["GCA_FIGMA_SPEC.json", "flows.questionnaireToCodeFlow", "Questionario -> validacao -> OCG -> codigo", "RN-010 a RN-022"],
        ["GCA_FIGMA_SPEC.json", "validationRules.*", "Todas as regras de validacao com testes", "RN-001, RN-003, RN-004, RN-008, RN-011, RN-015"],
    ]
    story.append(make_small_table(
        ["Arquivo", "Path no JSON", "Conteudo", "Regras"],
        json_mapping,
        [30*mm, 40*mm, W-92*mm, 22*mm]
    ))

    story.append(spacer(6))
    story.append(p(
        "<b>Como usar com Figma Make:</b><br/>"
        "1. Importe GCA_FIGMA_SPEC.json como data source no Figma<br/>"
        "2. Use <i>pages.*</i> para gerar frames de cada tela<br/>"
        "3. Use <i>globalComponents.*</i> para sidebar, header, modais<br/>"
        "4. Use <i>flows.*</i> para gerar prototipos com transicoes<br/>"
        "5. Use <i>theme.*</i> para aplicar cores, fontes e espacamentos<br/>"
        "6. Use <i>validationRules.*</i> para vincular regras a componentes de form"
    ))

    story.append(Spacer(1, 20*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=VIOLET))
    story.append(Spacer(1, 5*mm))
    story.append(p(
        "<b>Fim do Documento</b><br/>"
        "GCA - Gestao de Codificacao Assistida | Versao 1.0 | 07/04/2026<br/>"
        "GCA Software - Todos os direitos reservados",
        ParagraphStyle("Footer", parent=BODY, alignment=TA_CENTER, fontSize=9, textColor=SLATE_500)
    ))

    # ========================================================================
    # BUILD PDF
    # ========================================================================
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"PDF gerado: {output_path}")
    print(f"Tamanho: {os.path.getsize(output_path) / 1024:.1f} KB")
    return output_path


if __name__ == "__main__":
    build_document()
