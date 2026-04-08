"""
Questionnaire Schema — 54 campos organizados em 9 blocos

Blocos A.1–A.8 (Q1–Q49): Preenchidos pelo GP no formulário.
Bloco A.12 (Q50–Q54): Retorno dos agentes de IA após análise.

Cada pergunta usa o número (1–54) como chave no dict de responses.
Campos texto: valor string.
Campos seleção única: valor string.
Campos seleção múltipla: lista de strings.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Enums de opções válidas para cada pergunta de seleção
# ============================================================================

# A.1 — Informações gerais do projeto

class ProjetoExistente(str, Enum):
    SIM = "Sim"
    NAO = "Não"


class TipoIniciativa(str, Enum):
    NOVO_SISTEMA = "Novo sistema"
    MELHORIA = "Melhoria em sistema existente"
    NOVA_FUNCIONALIDADE = "Nova funcionalidade em sistema existente"
    REFATORACAO = "Refatoração técnica"
    MODERNIZACAO = "Modernização/Migração"
    INTEGRACAO = "Integração"
    AUTOMACAO = "Automação interna"
    POC_MVP = "POC/MVP"


class Criticidade(str, Enum):
    BAIXA = "Baixa"
    MEDIA = "Média"
    ALTA = "Alta"
    CRITICA = "Crítica"


class ClassificacaoInformacao(str, Enum):
    PUBLICA = "Pública"
    INTERNA = "Interna"
    CONFIDENCIAL = "Confidencial"
    RESTRITA = "Restrita"


# A.2 — Bloco obrigatório para projetos existentes

class NivelAcesso(str, Enum):
    READ_ONLY = "Read-only"
    READ_METADATA = "Read + metadata"
    READ_PR = "Read + PR"
    OUTRO = "Outro"


class ObjetivoAlteracao(str, Enum):
    CORRECAO = "Correção"
    EVOLUCAO = "Evolução funcional"
    REFATORACAO = "Refatoração"
    INTEGRACAO = "Integração"
    DEBITO_TECNICO = "Redução de débito técnico"
    MIGRACAO = "Migração de arquitetura"
    SEGURANCA_COMPLIANCE = "Adequação de segurança/compliance"
    PERFORMANCE = "Performance"


class AutorizaN8n(str, Enum):
    SIM = "Sim"
    NAO = "Não"


class AnaliseN8n(str, Enum):
    ARQUITETURA = "Arquitetura atual"
    LINGUAGENS = "Linguagens e frameworks"
    DEPENDENCIAS = "Dependências e versões"
    DEPRECATED = "Itens deprecated"
    CICD = "Pipelines CI/CD"
    TESTES = "Testes existentes"
    RISCOS = "Riscos técnicos"
    DOCUMENTACAO = "Documentação ausente"
    INTEGRACOES = "Integrações detectadas"


class RelatorioTecnico(str, Enum):
    RESUMO_EXECUTIVO = "Resumo executivo"
    ARQUITETURA = "Arquitetura identificada"
    STACK = "Stack detectada"
    RISCOS = "Riscos técnicos"
    BACKLOG = "Sugestão de backlog"
    MODERNIZACAO = "Sugestão de modernização"
    LACUNAS_TESTES = "Lacunas de testes"
    LACUNAS_DOCS = "Lacunas de documentação"


# A.3 — Perfil de entrega e arquitetura alvo

class EntregavelPrincipal(str, Enum):
    EXECUTAVEL_DESKTOP = "Executável desktop"
    APLICACAO_WEB = "Aplicação web"
    API = "API"
    MICROSERVICO = "Microserviço"
    APP_MOBILE = "Aplicativo mobile"
    DASHBOARD = "Dashboard"
    JOB_WORKER = "Job/Worker"
    CLI = "CLI"
    BIBLIOTECA_SDK = "Biblioteca/SDK"


class PerfilArquitetural(str, Enum):
    MONOLITO = "Monólito"
    MONOLITO_MODULAR = "Monólito modular"
    MICROSERVICOS = "Microserviços"
    EVENT_DRIVEN = "Event-driven"
    HEXAGONAL = "Hexagonal"
    CLEAN_ARCHITECTURE = "Clean Architecture"
    SERVERLESS = "Serverless"
    DESKTOP_LOCAL = "Desktop local"


class ModeloExecucao(str, Enum):
    STANDALONE = "Stand-alone"
    ON_PREMISES = "On-premises"
    CLOUD = "Cloud"
    HIBRIDO = "Híbrido"
    CONTAINERIZADO = "Containerizado"
    OFFLINE_SYNC = "Offline com sincronização posterior"


class SimNaoTalvez(str, Enum):
    SIM = "Sim"
    NAO = "Não"
    TALVEZ = "Talvez"


class SimNaoFuturamente(str, Enum):
    SIM = "Sim"
    NAO = "Não"
    FUTURAMENTE = "Futuramente"


class SimNao(str, Enum):
    SIM = "Sim"
    NAO = "Não"


# A.4 — Frontend

class TipoFrontend(str, Enum):
    WEB_SPA = "Web SPA"
    SSR = "SSR"
    PWA = "PWA"
    DESKTOP_UI = "Desktop UI"
    MOBILE_APP = "Mobile app"
    PAINEL_ADMIN = "Painel administrativo"
    PORTAL_AUTENTICADO = "Portal autenticado"


class StackFrontend(str, Enum):
    REACT = "React"
    VUE = "Vue"
    ANGULAR = "Angular"
    NEXTJS = "Next.js"
    VITE_REACT = "Vite + React"
    ELECTRON = "Electron"
    FLUTTER = "Flutter"
    REACT_NATIVE = "React Native"
    SEM_PREFERENCIA = "Sem preferência"


class LinguagemFrontend(str, Enum):
    TYPESCRIPT = "TypeScript"
    JAVASCRIPT = "JavaScript"
    OUTRA = "Outra"


class RequisitosFrontend(str, Enum):
    RESPONSIVIDADE = "Responsividade"
    ACESSIBILIDADE = "Acessibilidade"
    DARK_THEME = "Dark theme"
    FORMULARIOS_COMPLEXOS = "Formulários complexos"
    GRAFICOS = "Gráficos"
    UPLOAD_ARQUIVOS = "Upload de arquivos"
    IMPRESSAO_PDF = "Impressão/PDF"
    INTERNACIONALIZACAO = "Internacionalização"


# A.5 — Backend e APIs

class LinguagemBackend(str, Enum):
    PYTHON = "Python"
    NODEJS = "Node.js"
    JAVA = "Java"
    CSHARP = "C#"
    GO = "Go"
    PHP = "PHP"
    KOTLIN = "Kotlin"
    OUTRA = "Outra"


class FrameworkBackend(str, Enum):
    FASTAPI = "FastAPI"
    DJANGO = "Django"
    FLASK = "Flask"
    NESTJS = "NestJS"
    EXPRESS = "Express"
    SPRING_BOOT = "Spring Boot"
    ASPNET = "ASP.NET"
    QUARKUS = "Quarkus"
    SEM_PREFERENCIA = "Sem preferência"


class TipoBackend(str, Enum):
    REST_API = "REST API"
    GRAPHQL = "GraphQL"
    GRPC = "gRPC"
    WEBSOCKET = "WebSocket"
    BATCH = "Batch"
    WORKER = "Worker"
    BFF = "BFF"
    MISTO = "Misto"


class RequisitosBackend(str, Enum):
    AUTENTICACAO = "Autenticação"
    RBAC = "RBAC"
    WEBHOOKS = "Webhooks"
    JOBS = "Jobs"
    AUDITORIA = "Auditoria"
    VERSIONAMENTO_API = "Versionamento de API"
    RATE_LIMITING = "Rate limiting"
    OBSERVABILIDADE = "Observabilidade"
    INTEGRACAO_IA = "Integração com IA"


# A.6 — Dados, cache, mensageria e automação

class PersistenciaPrincipal(str, Enum):
    POSTGRESQL = "PostgreSQL"
    MYSQL = "MySQL"
    SQL_SERVER = "SQL Server"
    ORACLE = "Oracle"
    MONGODB = "MongoDB"
    SQLITE = "SQLite"
    SEM_PREFERENCIA = "Sem preferência"


class PerfilUsoBanco(str, Enum):
    TRANSACIONAL = "Transacional"
    ANALITICO = "Analítico"
    DOCUMENTAL = "Documental"
    CATALOGO = "Catálogo"
    EVENT_STORE = "Event store"
    MISTO = "Misto"


class FinalidadeRedis(str, Enum):
    CACHE_LEITURA = "Cache de leitura"
    SESSOES = "Sessões"
    RATE_LIMITING = "Rate limiting"
    PUB_SUB = "Pub/Sub"
    LOCKS_DISTRIBUIDOS = "Locks distribuídos"
    FILAS_LEVES = "Filas leves"


class FinalidadeMensageria(str, Enum):
    EVENTOS_DOMINIO = "Eventos de domínio"
    INTEGRACOES_ASYNC = "Integrações assíncronas"
    BACKGROUND = "Processamento em background"
    ORQUESTRACAO = "Orquestração entre serviços"
    TELEMETRIA = "Telemetria"


class FinalidadeN8n(str, Enum):
    LEITURA_REPO = "Leitura/análise de repositório legado"
    AUTOMACAO = "Automação de integrações"
    NOTIFICACOES = "Notificações"
    RELATORIOS = "Geração de relatórios"
    ETL = "ETL"
    WEBHOOKS = "Disparo de webhooks"
    APROVACOES = "Aprovações"


# A.7 — IA, segurança e observabilidade

class FinalidadeIA(str, Enum):
    ANALISE_REQUISITOS = "Análise de requisitos"
    GERACAO_CODIGO = "Geração de código"
    DOC_TECNICA = "Documentação técnica"
    DOC_NEGOCIAL = "Documentação negocial"
    REVISAO_CODIGO = "Revisão de código"
    TESTES_AUTOMATIZADOS = "Testes automatizados"
    CLASSIFICACAO_ARTEFATOS = "Classificação de artefatos"
    CHAT_ASSISTIVO = "Chat assistivo"


class ProvedorIA(str, Enum):
    ANTHROPIC = "Anthropic"
    OPENAI = "OpenAI"
    GEMINI = "Gemini"
    DEEPSEEK = "DeepSeek"
    GROK = "Grok"
    OUTRO = "Outro"
    SEM_PREFERENCIA = "Sem preferência"


class RestricoesIA(str, Enum):
    MASCARAMENTO = "Mascaramento"
    ANONIMIZACAO = "Anonimização"
    BLOQUEIO_TOTAL = "Bloqueio total"
    ENVIO_PERMITIDO = "Envio permitido por política"
    AVALIACAO_TIPO_DADO = "Avaliação por tipo de dado"


class ControlesSeguranca(str, Enum):
    JWT = "JWT"
    OAUTH2 = "OAuth2"
    SSO = "SSO"
    MFA = "MFA"
    CRIPTO_TRANSITO = "Criptografia em trânsito"
    CRIPTO_REPOUSO = "Criptografia em repouso"
    VAULT = "Vault de segredos"
    ROTACAO_CREDENCIAIS = "Rotação de credenciais"
    TRILHAS_AUDITORIA = "Trilhas de auditoria"


class Observabilidade(str, Enum):
    LOGS_ESTRUTURADOS = "Logs estruturados"
    METRICAS = "Métricas"
    TRACING = "Tracing"
    HEALTH_CHECKS = "Health checks"
    ALERTAS = "Alertas"
    DASHBOARD_OPERACIONAL = "Dashboard operacional"
    DASHBOARD_EXECUTIVO = "Dashboard executivo"


# A.8 — Testes, validação e entregáveis

class TiposTeste(str, Enum):
    SMOKE = "Smoke"
    SANITY = "Sanity"
    UNITARIOS = "Unitários"
    INTEGRACAO = "Integração"
    CONTRATO_API = "Contrato/API"
    E2E = "E2E"
    UAT = "UAT"
    REGRESSAO = "Regressão"
    SEGURANCA = "Segurança"
    SAST_SCA = "SAST/SCA"
    DAST = "DAST"
    PERFORMANCE_CARGA = "Performance/Carga"
    STRESS_SOAK = "Stress/Soak"
    RESILIENCIA_RECUPERACAO = "Resiliência/Recuperação"
    BACKUP_RESTORE = "Backup/Restore"
    ACESSIBILIDADE = "Acessibilidade"
    COMPATIBILIDADE = "Compatibilidade"


class EntregaveisPipeline(str, Enum):
    SUGESTAO_ARQUITETURA = "Sugestão de arquitetura"
    SUGESTAO_STACK = "Sugestão de stack"
    DOC_TECNICO = "Documento técnico consolidado"
    DOC_NEGOCIAL = "Documento negocial consolidado"
    GAP_ANALYSIS = "Gap analysis"
    BACKLOG = "Backlog inicial"
    PLANO_TESTES = "Plano de testes"
    PLANO_SEGURANCA = "Plano de segurança"
    PLANO_OBSERVABILIDADE = "Plano de observabilidade"
    PLANO_DEPLOY = "Plano de deploy"


class FormatoRetorno(str, Enum):
    PAINEL_GCA = "Painel no GCA"
    HTML = "HTML"
    MARKDOWN = "Markdown"
    DOCX = "DOCX"
    PDF = "PDF"
    JSON = "JSON estruturado"
    YAML = "YAML"


# A.12 — Retorno dos agentes (campos 50–54, preenchidos pela IA)

class StatusQuestionario(str, Enum):
    OK_INGESTAO = "OK para ingestão"
    PENDENTE_AJUSTES = "Pendente de ajustes"
    INCONSISTENTE = "Inconsistente - revisar"


class AgentesValidadores(str, Enum):
    NEGOCIO = "Negócio"
    ARQUITETURA = "Arquitetura"
    DESENVOLVIMENTO = "Desenvolvimento"
    QA = "QA"
    SEGURANCA = "Segurança"
    INFRAESTRUTURA = "Infraestrutura"
    COMPLIANCE = "Compliance"


# ============================================================================
# Mapeamento pergunta → campo nomeado
# ============================================================================

QUESTION_FIELD_MAP: Dict[str, str] = {
    # A.1 — Informações gerais
    "1": "project_name",
    "2": "project_slug",
    "3": "is_existing_project",
    "4": "initiative_type",
    "5": "criticality",
    "6": "information_classification",
    # A.2 — Projetos existentes
    "7": "existing_system_name",
    "8": "main_repository",
    "9": "additional_repositories",
    "10": "repository_access_level",
    "11": "change_objective",
    "12": "authorize_n8n_analysis",
    "13": "n8n_analysis_scope",
    "14": "expected_technical_report",
    # A.3 — Perfil de entrega e arquitetura
    "15": "main_deliverable",
    "16": "architectural_profile",
    "17": "execution_model",
    "18": "multi_tenant",
    "19": "high_availability",
    "20": "async_processing",
    # A.4 — Frontend
    "21": "has_frontend",
    "22": "frontend_type",
    "23": "frontend_stack",
    "24": "frontend_language",
    "25": "frontend_requirements",
    # A.5 — Backend e APIs
    "26": "has_backend",
    "27": "backend_language",
    "28": "backend_framework",
    "29": "backend_type",
    "30": "backend_requirements",
    # A.6 — Dados, cache, mensageria
    "31": "primary_database",
    "32": "database_usage_profile",
    "33": "needs_redis",
    "34": "redis_purpose",
    "35": "needs_messaging",
    "36": "messaging_purpose",
    "37": "uses_n8n",
    "38": "n8n_purpose",
    # A.7 — IA, segurança, observabilidade
    "39": "uses_ai",
    "40": "ai_purpose",
    "41": "ai_provider",
    "42": "ai_restrictions",
    "43": "security_controls",
    "44": "observability",
    # A.8 — Testes, validação, entregáveis
    "45": "test_types",
    "46": "automated_quality_gate",
    "47": "formal_qa_evidence",
    "48": "pipeline_deliverables",
    "49": "output_format",
    # A.12 — Retorno dos agentes (preenchido pela IA)
    "50": "agent_restrictions",
    "51": "agent_observations",
    "52": "completion_percentage",
    "53": "questionnaire_status",
    "54": "validating_agents",
}

# Mapeamento inverso: campo → pergunta
FIELD_QUESTION_MAP: Dict[str, str] = {v: k for k, v in QUESTION_FIELD_MAP.items()}

# Perguntas de texto livre (não seleção)
TEXT_QUESTIONS = {"1", "2", "7", "8", "9", "50", "51", "52"}

# Perguntas de seleção única
SINGLE_SELECT_QUESTIONS = {
    "3", "5", "6", "10", "12", "17", "18", "19", "20",
    "21", "24", "26", "27", "31", "33", "35", "37", "39",
    "46", "47", "53",
}

# Perguntas de seleção múltipla
MULTI_SELECT_QUESTIONS = {
    "4", "11", "13", "14", "15", "16", "22", "23", "25",
    "28", "29", "30", "32", "34", "36", "38", "40", "41",
    "42", "43", "44", "45", "48", "49", "54",
}

# Perguntas preenchidas pelos agentes (não pelo GP)
AGENT_RESPONSE_QUESTIONS = {"50", "51", "52", "53", "54"}

# Bloco A.2 só é obrigatório se pergunta 3 == "Sim"
EXISTING_PROJECT_QUESTIONS = {"7", "8", "9", "10", "11", "12", "13", "14"}


# ============================================================================
# Mapeamento de perguntas para pilares do OCG
# ============================================================================

QUESTION_PILLAR_MAP: Dict[str, str] = {
    # P1: Business Context
    "1": "P1", "2": "P1", "3": "P1", "4": "P1", "5": "P1",
    # P2: Rules & Compliance
    "6": "P2", "42": "P2", "46": "P2", "47": "P2",
    # P3: Features & Scope
    "11": "P3", "15": "P3", "18": "P3", "19": "P3", "20": "P3",
    # P4: Non-Functional Requirements
    "17": "P4", "19": "P4", "32": "P4", "44": "P4",
    # P5: Architecture & Design
    "16": "P5", "22": "P5", "23": "P5", "24": "P5",
    "27": "P5", "28": "P5", "29": "P5",
    # P6: Data & Persistence
    "31": "P6", "32": "P6", "33": "P6", "34": "P6",
    "35": "P6", "36": "P6",
    # P7: Security & Protection
    "43": "P7", "45": "P7",
    # Cross-cutting / Projetos existentes
    "7": "P5", "8": "P5", "9": "P5", "10": "P5",
    "12": "P3", "13": "P5", "14": "P3",
    # IA & Automação
    "37": "P3", "38": "P3", "39": "P5", "40": "P5", "41": "P5",
    # Frontend
    "21": "P3", "25": "P3",
    # Backend
    "26": "P3", "30": "P5",
    # Entregáveis
    "48": "P3", "49": "P3",
}


def extract_named_fields(responses: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte responses com chaves numéricas (1-49) em campos nomeados.
    Suporta também respostas já em formato nomeado (retrocompatível).
    """
    named = {}

    # Se já vier com campos nomeados, retorna direto
    if any(key in responses for key in ("project_name", "frontend_stack", "has_frontend")):
        return responses

    # Converte chaves numéricas → campos nomeados
    for q_num, field_name in QUESTION_FIELD_MAP.items():
        if q_num in responses:
            named[field_name] = responses[q_num]

    return named
