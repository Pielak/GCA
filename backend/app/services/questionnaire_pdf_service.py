"""
Serviço de geração + leitura de PDF editável (AcroForm) do questionário técnico GCA.

Fase 1: generate_pdf(project_name, deliverable_type) → bytes do PDF com campos editáveis.
Fase 3: extract_answers(pdf_bytes) → Dict[str, Any] mapeado no formato do questionário.

O PDF usa AcroForm (campos editáveis nativos do PDF — user preenche no Adobe/Foxit/Preview
sem precisar de software especial). Cada campo tem nome = question_id (ex: "q1", "q3").

Estrutura: 9 blocos (A.1 – A.8 + instruções), 49 campos editáveis.
Perguntas de seleção única → combo dropdown.
Perguntas de seleção múltipla → checkboxes (representados como campo de texto com instrução).
Perguntas de texto → campo de texto livre.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen.canvas import Canvas


# ──────────────────────────────────────────────────────────────────
# Dados das perguntas (espelho do frontend questionnaireBlocks.ts)
# ──────────────────────────────────────────────────────────────────

BLOCKS: List[Dict] = [
    {
        "id": "A.1", "title": "A.1 — Informações Gerais do Projeto",
        "questions": [
            {"id": "1", "label": "Nome do projeto", "type": "text"},
            {"id": "2", "label": "Slug do projeto (ex: portal-cliente)", "type": "text"},
            {"id": "3", "label": "O projeto altera um projeto já existente?", "type": "single", "options": ["Sim", "Não"]},
            {"id": "4", "label": "Detalhamento da iniciativa", "type": "multi", "options": ["Novo sistema", "Melhoria em sistema existente", "Nova funcionalidade", "Refatoração técnica", "Modernização/Migração", "Integração", "Automação interna", "POC/MVP"]},
            {"id": "5", "label": "Criticidade do projeto", "type": "single", "options": ["Baixa", "Média", "Alta", "Crítica"]},
            {"id": "6", "label": "Classificação da informação", "type": "single", "options": ["Pública", "Interna", "Confidencial", "Restrita"]},
        ],
    },
    {
        "id": "A.2", "title": "A.2 — Projetos Existentes (preencher se Q3 = Sim)",
        "questions": [
            {"id": "7", "label": "Nome do sistema existente", "type": "text"},
            {"id": "8", "label": "Repositório principal (URL)", "type": "text"},
            {"id": "9", "label": "Repositórios adicionais (URLs, vírgula)", "type": "text"},
            {"id": "10", "label": "Nível de acesso ao repositório", "type": "single", "options": ["Read-only", "Read + metadata", "Read + PR", "Outro"]},
            {"id": "11", "label": "Objetivo da alteração", "type": "multi", "options": ["Correção", "Evolução funcional", "Refatoração", "Integração", "Débito técnico", "Migração", "Segurança/compliance", "Performance"]},
            {"id": "12", "label": "Autoriza análise automática do repositório?", "type": "single", "options": ["Sim", "Não"]},
            {"id": "13", "label": "Escopo da análise automática", "type": "multi", "options": ["Arquitetura", "Linguagens/frameworks", "Dependências", "Deprecated", "CI/CD", "Testes", "Riscos", "Doc ausente", "Integrações"]},
            {"id": "14", "label": "Relatório técnico esperado", "type": "multi", "options": ["Resumo executivo", "Arquitetura", "Stack", "Riscos", "Backlog", "Modernização", "Lacunas testes", "Lacunas docs"]},
        ],
    },
    {
        "id": "A.3", "title": "A.3 — Perfil de Entrega e Arquitetura",
        "questions": [
            {"id": "15", "label": "Entregável principal", "type": "multi", "options": ["Executável desktop", "Aplicação web", "API", "Microserviço", "App mobile", "Dashboard", "Job/Worker", "CLI", "Biblioteca/SDK"]},
            {"id": "16", "label": "Perfil arquitetural", "type": "multi", "options": ["Monólito", "Monólito modular", "Microserviços", "Event-driven", "Hexagonal", "Clean Architecture", "Serverless", "Desktop local"]},
            {"id": "17", "label": "Modelo de execução", "type": "multi", "options": ["Stand-alone", "On-premises", "Cloud", "Híbrido", "Containerizado", "Offline + sync"]},
            {"id": "18", "label": "Multi-tenant?", "type": "single", "options": ["Sim", "Não", "Talvez", "N/A"]},
            {"id": "19", "label": "Alta disponibilidade?", "type": "single", "options": ["Sim", "Não", "Futuramente", "N/A"]},
            {"id": "20", "label": "Processamento assíncrono/jobs?", "type": "single", "options": ["Sim", "Não", "N/A"]},
        ],
    },
    {
        "id": "A.4", "title": "A.4 — Frontend",
        "questions": [
            {"id": "21", "label": "O projeto terá frontend?", "type": "single", "options": ["Sim", "Não"]},
            {"id": "22", "label": "Tipo de frontend", "type": "multi", "options": ["Web SPA", "SSR", "PWA", "Desktop UI", "Mobile app", "Painel admin", "Portal autenticado"]},
            {"id": "23", "label": "Stack frontend", "type": "multi", "options": ["React", "Vue", "Angular", "Next.js", "Vite+React", "Electron", "Flutter", "React Native", "Sem preferência"]},
            {"id": "24", "label": "Linguagem frontend", "type": "single", "options": ["TypeScript", "JavaScript", "Outra", "N/A"]},
            {"id": "25", "label": "Requisitos frontend", "type": "multi", "options": ["Responsividade", "Acessibilidade", "Dark theme", "Formulários complexos", "Gráficos", "Upload arquivos", "Impressão/PDF", "i18n"]},
        ],
    },
    {
        "id": "A.5", "title": "A.5 — Backend e APIs",
        "questions": [
            {"id": "26", "label": "O projeto terá backend?", "type": "single", "options": ["Sim", "Não"]},
            {"id": "27", "label": "Linguagem backend", "type": "single", "options": ["Python", "Node.js", "Java", "C#", "Go", "PHP", "Kotlin", "Outra"]},
            {"id": "28", "label": "Framework backend", "type": "multi", "options": ["FastAPI", "Django", "Flask", "NestJS", "Express", "Spring Boot", "ASP.NET", "Quarkus", "Sem preferência"]},
            {"id": "29", "label": "Tipo de backend", "type": "multi", "options": ["REST API", "GraphQL", "gRPC", "WebSocket", "Batch", "Worker", "BFF", "Misto"]},
            {"id": "30", "label": "Requisitos backend", "type": "multi", "options": ["Autenticação", "RBAC", "Webhooks", "Jobs", "Auditoria", "Versionamento API", "Rate limiting", "Observabilidade", "Integração IA"]},
        ],
    },
    {
        "id": "A.6", "title": "A.6 — Dados, Cache e Mensageria",
        "questions": [
            {"id": "31", "label": "Banco de dados principal", "type": "single", "options": ["PostgreSQL", "MySQL", "SQL Server", "Oracle", "MongoDB", "SQLite", "Sem preferência", "N/A"]},
            {"id": "32", "label": "Perfil de uso do banco", "type": "multi", "options": ["Transacional", "Analítico", "Documental", "Catálogo", "Event store", "Misto"]},
            {"id": "33", "label": "Redis (cache em memória)?", "type": "single", "options": ["Sim", "Não", "Talvez", "N/A"]},
            {"id": "34", "label": "Finalidade do Redis", "type": "multi", "options": ["Cache leitura", "Sessões", "Rate limiting", "Pub/Sub", "Locks", "Filas leves"]},
            {"id": "35", "label": "Mensageria (Kafka, RabbitMQ)?", "type": "single", "options": ["Sim", "Não", "Talvez", "N/A"]},
            {"id": "36", "label": "Finalidade da mensageria", "type": "multi", "options": ["Eventos de domínio", "Integrações async", "Background", "Orquestração", "Telemetria"]},
            {"id": "37", "label": "Usa n8n (automação)?", "type": "single", "options": ["Sim", "Não", "Talvez", "N/A"]},
            {"id": "38", "label": "Finalidade do n8n", "type": "multi", "options": ["Análise de repo", "Automação", "Notificações", "Relatórios", "ETL", "Webhooks", "Aprovações"]},
        ],
    },
    {
        "id": "A.7", "title": "A.7 — IA, Segurança e Observabilidade",
        "questions": [
            {"id": "39", "label": "O projeto utilizará IA?", "type": "single", "options": ["Sim", "Não", "Talvez", "N/A"]},
            {"id": "40", "label": "Finalidade da IA", "type": "multi", "options": ["Análise requisitos", "Geração código", "Doc técnica", "Doc negocial", "Revisão código", "Testes", "Classificação", "Chat"]},
            {"id": "41", "label": "Provedor de IA", "type": "multi", "options": ["Anthropic", "OpenAI", "Gemini", "DeepSeek", "Grok", "Outro", "Sem preferência"]},
            {"id": "42", "label": "Restrições de envio de dados à IA", "type": "multi", "options": ["Mascaramento", "Anonimização", "Bloqueio total", "Envio permitido", "Avaliação por tipo"]},
            {"id": "43", "label": "Controles de segurança obrigatórios", "type": "multi", "options": ["JWT", "OAuth2", "SSO", "MFA", "HTTPS", "Cripto repouso", "Vault", "Rotação credenciais", "Auditoria"]},
            {"id": "44", "label": "Observabilidade exigida", "type": "multi", "options": ["Logs estruturados", "Métricas", "Tracing", "Health checks", "Alertas", "Dashboard ops", "Dashboard exec"]},
        ],
    },
    {
        "id": "A.8", "title": "A.8 — Testes, Validação e Entregáveis",
        "questions": [
            {"id": "45", "label": "Tipos mínimos de teste exigidos", "type": "multi", "options": ["Smoke", "Sanity", "Unitários", "Integração", "Contrato/API", "E2E", "UAT", "Regressão", "Segurança", "SAST/SCA", "DAST", "Performance", "Stress", "Resiliência", "Backup", "Acessibilidade", "Compatibilidade"]},
            {"id": "46", "label": "Quality gate automatizado?", "type": "single", "options": ["Sim", "Não", "N/A"]},
            {"id": "47", "label": "Evidência formal de QA?", "type": "single", "options": ["Sim", "Não", "N/A"]},
            {"id": "48", "label": "Entregáveis esperados do pipeline", "type": "multi", "options": ["Arquitetura", "Stack", "Doc técnico", "Doc negocial", "Gap analysis", "Backlog", "Plano testes", "Plano segurança", "Plano observabilidade", "Plano deploy"]},
            {"id": "49", "label": "Formato de retorno desejado", "type": "multi", "options": ["Painel GCA", "HTML", "Markdown", "DOCX", "PDF", "JSON", "YAML"]},
        ],
    },
]


# ──────────────────────────────────────────────────────────────────
# Fase 1: Geração do PDF editável (AcroForm)
# ──────────────────────────────────────────────────────────────────

VIOLET_HEX = "#7C3AED"
VIOLET_RGB = (0x7C / 255, 0x3A / 255, 0xED / 255)
SLATE_RGB = (0.12, 0.16, 0.22)
LIGHT_GRAY = (0.95, 0.95, 0.97)

PAGE_W, PAGE_H = A4
MARGIN_L = 2.0 * cm
MARGIN_R = 2.0 * cm
MARGIN_T = 2.0 * cm
MARGIN_B = 2.0 * cm
FIELD_W = PAGE_W - MARGIN_L - MARGIN_R


def generate_pdf(project_name: str, deliverable_type: str = "", project_slug: str = "") -> bytes:
    """Gera PDF editável (AcroForm) com as 49 perguntas do questionário.

    Returns:
        bytes: conteúdo do PDF pronto para download ou envio por email.
    """
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)

    # Habilita AcroForm
    c.setTitle(f"Questionário Técnico GCA — {project_name}")
    c.setAuthor("GCA — Gerenciador Central de Arquiteturas")
    c.setSubject("Questionário técnico para seed do OCG")

    form = c.acroForm

    y = PAGE_H - MARGIN_T

    # ── Capa simplificada ──
    c.setFillColor(colors.HexColor(VIOLET_HEX))
    c.setFont("Helvetica-Bold", 28)
    c.drawString(MARGIN_L, y, "GCA")
    y -= 14
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(MARGIN_L, y, "Gerenciador Central de Arquiteturas")
    y -= 30

    c.setFillColor(colors.HexColor("#1E293B"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN_L, y, "Questionário Técnico do Projeto")
    y -= 20

    if project_name:
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(colors.HexColor(VIOLET_HEX))
        c.drawString(MARGIN_L, y, project_name)
        y -= 18

    if deliverable_type:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(MARGIN_L, y, f"Tipo: {deliverable_type}")
        y -= 14

    if project_slug:
        c.drawString(MARGIN_L, y, f"Slug: {project_slug}")
        y -= 14

    y -= 10
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#64748B"))
    instructions = [
        "INSTRUÇÕES DE PREENCHIMENTO:",
        "",
        "1. Preencha os campos diretamente neste PDF (Adobe Reader, Foxit ou Preview).",
        "2. Para perguntas de seleção múltipla, separe as opções por vírgula.",
        "3. Campos marcados (N/A) podem ser deixados em branco se não se aplicam.",
        "4. Após preencher, salve o PDF e faça upload na tela do projeto no GCA.",
        "5. O GCA analisará suas respostas e gerará o OCG inicial automaticamente.",
        "",
        "Mínimo de 80% de perguntas respondidas para aprovação automática.",
        "Perguntas do bloco A.2 só se aplicam se Q3 = 'Sim'.",
    ]
    for line in instructions:
        c.drawString(MARGIN_L, y, line)
        y -= 12

    y -= 10
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.line(MARGIN_L, y, PAGE_W - MARGIN_R, y)
    y -= 20

    # ── Perguntas por bloco ──
    for block in BLOCKS:
        if y < 120:
            c.showPage()
            y = PAGE_H - MARGIN_T

        # Título do bloco
        c.setFillColor(colors.HexColor(VIOLET_HEX))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN_L, y, block["title"])
        y -= 6
        c.setStrokeColor(colors.HexColor(VIOLET_HEX))
        c.line(MARGIN_L, y, PAGE_W - MARGIN_R, y)
        y -= 16

        for q in block["questions"]:
            if y < 80:
                c.showPage()
                y = PAGE_H - MARGIN_T

            # Label da pergunta
            c.setFillColor(colors.HexColor("#1E293B"))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(MARGIN_L, y, f"Q{q['id']}. {q['label']}")
            y -= 4

            # Hint de opções para multi/single
            if q["type"] in ("single", "multi") and q.get("options"):
                c.setFont("Helvetica", 7)
                c.setFillColor(colors.HexColor("#94A3B8"))
                opts_hint = f"Opções: {' | '.join(q['options'])}"
                if q["type"] == "multi":
                    opts_hint += "  (separe por vírgula)"
                # Quebra se muito longo
                if len(opts_hint) > 120:
                    c.drawString(MARGIN_L + 4, y, opts_hint[:120])
                    y -= 10
                    c.drawString(MARGIN_L + 4, y, opts_hint[120:240])
                else:
                    c.drawString(MARGIN_L + 4, y, opts_hint)
                y -= 4

            y -= 2

            # Campo editável (AcroForm)
            field_name = f"q{q['id']}"
            field_height = 18 if q["type"] == "text" else 16

            form.textfield(
                name=field_name,
                x=MARGIN_L,
                y=y - field_height,
                width=FIELD_W,
                height=field_height,
                fontSize=9,
                borderColor=colors.HexColor("#CBD5E1"),
                fillColor=colors.HexColor("#F8FAFC"),
                textColor=colors.HexColor("#1E293B"),
                fieldFlags="",
            )
            y -= field_height + 10

        y -= 6  # espaço entre blocos

    # Rodapé final
    if y < 80:
        c.showPage()
        y = PAGE_H - MARGIN_T

    y -= 20
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(MARGIN_L, y, "GCA — Gerenciador Central de Arquiteturas • Questionário gerado automaticamente")
    c.drawString(MARGIN_L, y - 12, "Após preencher, faça upload do PDF no GCA → tela do questionário do projeto.")

    c.save()
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────
# Fase 3: Extração de respostas do PDF preenchido
# ──────────────────────────────────────────────────────────────────

def extract_answers_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extrai respostas dos campos AcroForm de um PDF preenchido.

    Campos são nomeados 'q1', 'q2', ..., 'q49'. Respostas de seleção
    múltipla vêm separadas por vírgula — split para lista.

    Returns:
        Dict com chaves numéricas ('1', '2', ...) e valores string ou list.
    """
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    fields = reader.get_form_text_fields() or {}

    # Também tenta campos de formulário interativos
    if not fields and reader.get_fields():
        raw_fields = reader.get_fields()
        for name, field_obj in raw_fields.items():
            if hasattr(field_obj, "value") and field_obj.value:
                fields[name] = str(field_obj.value)
            elif isinstance(field_obj, dict) and field_obj.get("/V"):
                fields[name] = str(field_obj["/V"])

    answers: Dict[str, Any] = {}
    # Mapear question_id → opções válidas para detectar multi-select
    q_types: Dict[str, str] = {}
    for block in BLOCKS:
        for q in block["questions"]:
            q_types[q["id"]] = q["type"]

    for field_name, value in fields.items():
        if not field_name.startswith("q"):
            continue
        q_id = field_name[1:]  # Remove 'q' prefix
        if not q_id.isdigit():
            continue

        value = (value or "").strip()
        if not value:
            continue

        q_type = q_types.get(q_id, "text")
        if q_type == "multi" and "," in value:
            answers[q_id] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            answers[q_id] = value

    return answers


def extract_answers_from_text(text: str) -> Dict[str, Any]:
    """Fallback: extrai respostas de texto plano (caso o PDF não tenha AcroForm).

    Procura padrões como:
        Q1. Nome do projeto: Minha Aplicação
        Q15. Entregável: API, Microserviço
    """
    import re
    answers: Dict[str, Any] = {}
    pattern = re.compile(r"Q(\d+)[.\s:]+(.+)", re.IGNORECASE)

    q_types: Dict[str, str] = {}
    for block in BLOCKS:
        for q in block["questions"]:
            q_types[q["id"]] = q["type"]

    for match in pattern.finditer(text):
        q_id = match.group(1)
        value = match.group(2).strip().rstrip(".")
        if not value:
            continue

        q_type = q_types.get(q_id, "text")
        if q_type == "multi" and "," in value:
            answers[q_id] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            answers[q_id] = value

    return answers
