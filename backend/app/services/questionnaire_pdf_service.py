"""
Serviço de geração + leitura de PDF editável (AcroForm) do questionário técnico GCA.

generate_pdf() → PDF com checkboxes reais, dropdowns, campo "Outros" por pergunta.
extract_answers_from_pdf() → lê campos AcroForm preenchidos e devolve Dict.

Layout:
  - Single select → dropdown (combo AcroForm)
  - Multi select → checkboxes individuais + checkbox "Outros" + campo texto
  - Text → textfield
  - Nome/slug do projeto pré-preenchidos (vieram do wizard de solicitação)
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas


# ──────────────────────────────────────────────────────────────────
# Dados das perguntas
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
# Cores e layout
# ──────────────────────────────────────────────────────────────────

VIOLET = colors.HexColor("#7C3AED")
VIOLET_LIGHT = colors.HexColor("#DDD6FE")
SLATE_DARK = colors.HexColor("#1E293B")
SLATE_MID = colors.HexColor("#64748B")
SLATE_BORDER = colors.HexColor("#CBD5E1")
FIELD_BG = colors.HexColor("#F8FAFC")
WHITE = colors.HexColor("#FFFFFF")

PAGE_W, PAGE_H = A4
ML = 2.0 * cm   # margin left
MR = 2.0 * cm   # margin right
MT = 2.0 * cm   # margin top
MB = 2.5 * cm   # margin bottom
USABLE_W = PAGE_W - ML - MR

CB_SIZE = 10     # checkbox size
CB_GAP = 3       # gap between checkbox and label
COL_GAP = 8      # gap between columns of checkboxes
ROW_H = 16       # row height for checkbox rows
FIELD_H = 18     # textfield height
Q_GAP = 14       # gap between questions
BLOCK_GAP = 18   # gap between blocks


def _new_page(c: Canvas) -> float:
    c.showPage()
    return PAGE_H - MT


def _need_space(c: Canvas, y: float, needed: float) -> float:
    if y - needed < MB:
        return _new_page(c)
    return y


# ──────────────────────────────────────────────────────────────────
# Geração do PDF
# ──────────────────────────────────────────────────────────────────

def generate_pdf(
    project_name: str,
    deliverable_type: str = "",
    project_slug: str = "",
) -> bytes:
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(f"Questionário Técnico GCA — {project_name}")
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
    c.drawString(ML, y, "Questionário Técnico do Projeto")
    y -= 20

    if project_name:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(VIOLET)
        c.drawString(ML, y, project_name)
        y -= 16
    if deliverable_type:
        c.setFont("Helvetica", 9)
        c.setFillColor(SLATE_MID)
        c.drawString(ML, y, f"Tipo: {deliverable_type}    |    Slug: {project_slug}")
        y -= 18

    # Linha separadora
    c.setStrokeColor(VIOLET)
    c.setLineWidth(1.5)
    c.line(ML, y, PAGE_W - MR, y)
    y -= 16

    # Instruções
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(SLATE_DARK)
    c.drawString(ML, y, "INSTRUÇÕES DE PREENCHIMENTO")
    y -= 13
    c.setFont("Helvetica", 8)
    c.setFillColor(SLATE_MID)
    instrucoes = [
        "1. Abra no Adobe Reader, Foxit ou Preview. Preencha os campos diretamente.",
        "2. Perguntas de seleção única: use o dropdown (combo). Múltipla: marque os checkboxes.",
        '3. Se marcar "Outros", preencha o campo de texto ao lado com sua descrição.',
        "4. Mínimo 80% de perguntas respondidas para aprovação automática.",
        "5. Bloco A.2 só se aplica se Q3 = 'Sim'. Salve e faça upload no GCA.",
    ]
    for line in instrucoes:
        c.drawString(ML, y, line)
        y -= 11
    y -= 8

    c.setStrokeColor(SLATE_BORDER)
    c.setLineWidth(0.5)
    c.line(ML, y, PAGE_W - MR, y)
    y -= BLOCK_GAP

    # ── Blocos de perguntas ──
    for block in BLOCKS:
        y = _need_space(c, y, 60)

        # Título do bloco (faixa violeta)
        c.setFillColor(VIOLET)
        c.rect(ML, y - 4, USABLE_W, 18, fill=True, stroke=False)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(ML + 6, y, block["title"])
        y -= 22

        for q in block["questions"]:
            q_type = q["type"]
            options = q.get("options", [])

            # Calcular espaço necessário
            if q_type == "text":
                needed = 30 + Q_GAP
            elif q_type == "single":
                needed = 30 + Q_GAP
            else:
                cols = 2 if len(options) <= 12 else 3
                rows = -(-len(options) // cols)  # ceil division
                # +1 row para "Outros" + campo texto
                needed = 18 + (rows + 1) * ROW_H + FIELD_H + Q_GAP + 6

            y = _need_space(c, y, needed)

            # Label da pergunta
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(SLATE_DARK)
            c.drawString(ML, y, f"Q{q['id']}. {q['label']}")
            y -= 14

            if q_type == "text":
                # Pré-preencher nome e slug
                prefill = ""
                if q["id"] == "1":
                    prefill = project_name
                elif q["id"] == "2":
                    prefill = project_slug

                form.textfield(
                    name=f"q{q['id']}",
                    x=ML, y=y - FIELD_H, width=USABLE_W, height=FIELD_H,
                    fontSize=9,
                    value=prefill,
                    borderColor=SLATE_BORDER, fillColor=FIELD_BG,
                    textColor=SLATE_DARK,
                )
                y -= FIELD_H + Q_GAP

            elif q_type == "single":
                # Dropdown (combo)
                form.choice(
                    name=f"q{q['id']}",
                    x=ML, y=y - FIELD_H, width=min(USABLE_W, 280), height=FIELD_H,
                    fontSize=9,
                    options=["Selecione..."] + options,
                    value="Selecione...",
                    borderColor=SLATE_BORDER, fillColor=FIELD_BG,
                    textColor=SLATE_DARK,
                )
                y -= FIELD_H + Q_GAP

            elif q_type == "multi":
                # Checkboxes em grid
                cols = 2 if len(options) <= 12 else 3
                col_w = USABLE_W / cols

                for idx, opt in enumerate(options):
                    col = idx % cols
                    row = idx // cols
                    cx = ML + col * col_w
                    cy = y - row * ROW_H

                    if cy < MB + 40:
                        y = _new_page(c)
                        cy = y

                    cb_name = f"q{q['id']}_cb_{idx}"
                    form.checkbox(
                        name=cb_name,
                        x=cx, y=cy - CB_SIZE,
                        size=CB_SIZE,
                        borderColor=SLATE_BORDER,
                        fillColor=FIELD_BG,
                        buttonStyle="check",
                        checked=False,
                    )
                    c.setFont("Helvetica", 8)
                    c.setFillColor(SLATE_DARK)
                    c.drawString(cx + CB_SIZE + CB_GAP, cy - 8, opt[:35])

                rows_used = -(-len(options) // cols)
                y -= rows_used * ROW_H + 4

                y = _need_space(c, y, ROW_H + FIELD_H + 8)

                # Checkbox "Outros"
                form.checkbox(
                    name=f"q{q['id']}_cb_outros",
                    x=ML, y=y - CB_SIZE,
                    size=CB_SIZE,
                    borderColor=colors.HexColor("#F59E0B"),
                    fillColor=colors.HexColor("#FFFBEB"),
                    buttonStyle="check",
                    checked=False,
                )
                c.setFont("Helvetica-Oblique", 8)
                c.setFillColor(colors.HexColor("#D97706"))
                c.drawString(ML + CB_SIZE + CB_GAP, y - 8, "Outros (descreva abaixo se marcar esta opção):")
                y -= ROW_H

                # Campo de texto para "Outros"
                form.textfield(
                    name=f"q{q['id']}_outros",
                    x=ML, y=y - FIELD_H, width=USABLE_W, height=FIELD_H,
                    fontSize=8,
                    borderColor=colors.HexColor("#FDE68A"),
                    fillColor=colors.HexColor("#FFFBEB"),
                    textColor=SLATE_DARK,
                )
                y -= FIELD_H + Q_GAP

    # Rodapé
    y = _need_space(c, y, 40)
    y -= 12
    c.setStrokeColor(SLATE_BORDER)
    c.line(ML, y, PAGE_W - MR, y)
    y -= 14
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(SLATE_MID)
    c.drawString(ML, y, "GCA — Gerenciador Central de Arquiteturas • Questionário técnico gerado automaticamente")
    y -= 11
    c.drawString(ML, y, "Após preencher, salve e faça upload na tela Questionário do seu projeto no GCA.")

    c.save()
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────
# Extração de respostas do PDF preenchido
# ──────────────────────────────────────────────────────────────────

def _normalize_response_keys(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza chaves JSONB: converte "1" → "Q1", "42" → "Q42", etc.

    Mantém chaves já com prefixo "Q" como estão.
    """
    normalized = {}
    for key, value in answers.items():
        # Se é numérico puro, adiciona prefixo "Q"
        if isinstance(key, str) and key.isdigit():
            normalized_key = f"Q{key}"
        else:
            normalized_key = key
        normalized[normalized_key] = value
    return normalized


def extract_answers_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extrai respostas dos campos AcroForm de um PDF preenchido.

    Mapeia:
      - q{N} (textfield/choice) → resposta direta
      - q{N}_cb_{idx} (checkbox) → coleta checked, monta lista
      - q{N}_cb_outros + q{N}_outros → adiciona "Outros: ..." à lista

    Retorna chaves normalizadas: "Q1", "Q2", etc (não "1", "2", etc)
    """
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    raw_fields = reader.get_fields() or {}

    # Normaliza campos: nome → valor
    flat: Dict[str, str] = {}
    for name, field_obj in raw_fields.items():
        val = None
        if hasattr(field_obj, "value"):
            val = field_obj.value
        elif isinstance(field_obj, dict):
            val = field_obj.get("/V")
        if val is not None:
            flat[name] = str(val).strip()

    # Também tenta text fields
    text_fields = reader.get_form_text_fields() or {}
    for name, val in text_fields.items():
        if val and val.strip():
            flat[name] = val.strip()

    # Montar respostas
    answers: Dict[str, Any] = {}

    # q_types pra saber tipo de cada pergunta
    q_meta: Dict[str, Dict] = {}
    for block in BLOCKS:
        for q in block["questions"]:
            q_meta[q["id"]] = q

    # Processar text e single (diretos)
    for q_id, meta in q_meta.items():
        field_name = f"q{q_id}"
        if meta["type"] in ("text", "single"):
            val = flat.get(field_name, "")
            if val and val != "Selecione...":
                answers[q_id] = val

    # Processar multi (checkboxes)
    for q_id, meta in q_meta.items():
        if meta["type"] != "multi":
            continue
        options = meta.get("options", [])
        selected = []
        for idx, opt in enumerate(options):
            cb_name = f"q{q_id}_cb_{idx}"
            val = flat.get(cb_name, "")
            # Checkbox checked values: /Yes, Yes, true, /1, On
            if val and val.lower().replace("/", "") in ("yes", "true", "1", "on"):
                selected.append(opt)

        # "Outros"
        outros_cb = flat.get(f"q{q_id}_cb_outros", "")
        outros_text = flat.get(f"q{q_id}_outros", "")
        if outros_cb and outros_cb.lower().replace("/", "") in ("yes", "true", "1", "on"):
            if outros_text:
                selected.append(f"Outros: {outros_text}")
            else:
                selected.append("Outros")

        if selected:
            answers[q_id] = selected

    # Normalizar chaves: "1" → "Q1", "42" → "Q42"
    return _normalize_response_keys(answers)


def extract_answers_from_text(text: str) -> Dict[str, Any]:
    """Fallback: extrai respostas de texto plano do PDF.

    Procura padrões como:
        Q1. Nome do projeto: Minha Aplicação
        Q15. Entregável: API, Microserviço

    Retorna chaves normalizadas: "Q1", "Q2", etc
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

    # Normalizar chaves: "1" → "Q1", "42" → "Q42"
    return _normalize_response_keys(answers)
