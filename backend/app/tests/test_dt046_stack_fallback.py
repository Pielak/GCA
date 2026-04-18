"""
DT-046: Testes do fallback determinístico de STACK_RECOMMENDATION e
ARCHITECTURE_OVERVIEW no `AgentService`.

Contrato §5: "nenhum módulo deve assumir defaults invisíveis quando o OCG
estiver incompleto". Se o LLM consolidator omite esses campos, o sistema
deve reconstituir a partir de `project_metadata` (respostas do
questionário já aprovadas pelo GP).

Estes testes rodam **sem mock de LLM**: exercitam apenas os helpers
estáticos `_stack_from_metadata` e `_architecture_from_metadata`. Ficam
imunes à fixture autouse de DT-045 — são puros, determinísticos.
"""
from app.services.agent_service import AgentService


# ---------------------------------------------------------------------------
# STACK_RECOMMENDATION
# ---------------------------------------------------------------------------

def test_stack_fallback_full_metadata():
    """Metadata completo: fallback deve mapear todos os campos."""
    meta = {
        "has_frontend": True,
        "frontend_stack": ["React", "Vite+React"],
        "frontend_language": "TypeScript",
        "frontend_type": ["Web SPA", "Portal autenticado"],
        "frontend_requirements": ["i18n"],
        "has_backend": True,
        "backend_language": "Python",
        "backend_framework": ["FastAPI"],
        "backend_type": ["REST API"],
        "backend_requirements": ["Autenticação", "RBAC"],
        "database": "PostgreSQL",
        "database_profile": ["Transacional"],
        "uses_redis": True,
        "redis_purpose": ["Cache leitura"],
        "uses_messaging": False,
        "messaging_purpose": [],
        "uses_ai": True,
        "ai_provider": ["Anthropic"],
        "ai_purpose": ["Análise requisitos"],
        "ai_restrictions": ["Anonimização"],
    }

    stack = AgentService._stack_from_metadata(meta)

    # Frontend
    assert stack["frontend"]["enabled"] is True
    assert stack["frontend"]["stack"] == ["React", "Vite+React"]
    assert stack["frontend"]["language"] == "TypeScript"

    # Backend
    assert stack["backend"]["enabled"] is True
    assert stack["backend"]["language"] == "Python"
    assert stack["backend"]["framework"] == ["FastAPI"]

    # Database
    assert stack["database"]["engine"] == "PostgreSQL"

    # Cache
    assert stack["cache"]["enabled"] is True
    assert stack["cache"]["purpose"] == ["Cache leitura"]

    # Messaging desabilitado
    assert stack["messaging"]["enabled"] is False

    # AI
    assert stack["ai"]["enabled"] is True
    assert stack["ai"]["provider"] == ["Anthropic"]

    # Audit trail do fallback
    assert stack["source"] == "questionnaire_deterministic_fallback"


def test_stack_fallback_empty_metadata_returns_structure():
    """Metadata vazio: helper não pode crashar; retorna estrutura coerente."""
    stack = AgentService._stack_from_metadata({})

    assert stack["frontend"]["enabled"] is False
    assert stack["frontend"]["stack"] == []
    assert stack["backend"]["enabled"] is False
    assert stack["database"]["engine"] == ""
    assert stack["cache"]["enabled"] is False
    assert stack["ai"]["enabled"] is False
    assert stack["source"] == "questionnaire_deterministic_fallback"


def test_stack_fallback_handles_non_dict_input():
    """Defensivo: se meta não for dict, tratar como dict vazio."""
    stack = AgentService._stack_from_metadata(None)  # type: ignore[arg-type]
    assert stack["frontend"]["enabled"] is False
    assert stack["source"] == "questionnaire_deterministic_fallback"


# ---------------------------------------------------------------------------
# ARCHITECTURE_OVERVIEW
# ---------------------------------------------------------------------------

def test_architecture_fallback_full_metadata():
    """Metadata completo: mapeia arquitetura, execução, HA e async."""
    meta = {
        "architecture": ["Monólito modular", "Clean Architecture"],
        "execution_model": ["On-premises", "Containerizado"],
        "multi_tenant": "Não",
        "high_availability": "Futuramente",
        "async_processing": "Sim",
        "deliverables": ["Aplicação web", "API"],
    }

    arch = AgentService._architecture_from_metadata(meta)

    assert arch["architectural_profile"] == ["Monólito modular", "Clean Architecture"]
    assert arch["execution_model"] == ["On-premises", "Containerizado"]
    assert arch["multi_tenant"] == "Não"
    assert arch["high_availability"] == "Futuramente"
    assert arch["async_processing"] == "Sim"
    assert arch["deliverables"] == ["Aplicação web", "API"]
    assert arch["source"] == "questionnaire_deterministic_fallback"


def test_architecture_fallback_empty_metadata():
    """Sem metadata: retorna estrutura vazia mas consistente."""
    arch = AgentService._architecture_from_metadata({})
    assert arch["architectural_profile"] == []
    assert arch["execution_model"] == []
    assert arch["source"] == "questionnaire_deterministic_fallback"


def test_architecture_fallback_handles_non_dict_input():
    arch = AgentService._architecture_from_metadata(None)  # type: ignore[arg-type]
    assert arch["source"] == "questionnaire_deterministic_fallback"


# ---------------------------------------------------------------------------
# Regressão do projeto real (Automação Jurídica Assistida)
# ---------------------------------------------------------------------------

def test_stack_fallback_reads_project_profile_aliases():
    """DT-046 variante: aceitar nomes do PROJECT_PROFILE (pós-consolidação).

    `ocg_service` monta `project_metadata` com `architecture` /
    `redis_purpose` / `ai_purpose` / `deliverables`. Após salvar no OCG,
    o PROJECT_PROFILE carrega `architectural_profile` / `redis_usage` /
    `ai_use_cases` / `main_deliverable`. O helper deve aceitar os dois
    nomes para funcionar tanto no caminho consolidator quanto no script
    de re-aplicação a OCGs existentes.
    """
    meta = {
        "architectural_profile": ["Monólito modular", "Clean Architecture"],
        "redis_usage": ["Cache leitura", "Sessões"],
        "ai_use_cases": ["Análise requisitos", "Chat"],
        "main_deliverable": ["Aplicação web", "API"],
        "uses_redis": True,
        "uses_ai": True,
    }

    stack = AgentService._stack_from_metadata(meta)
    assert stack["cache"]["purpose"] == ["Cache leitura", "Sessões"]
    assert stack["ai"]["purpose"] == ["Análise requisitos", "Chat"]

    arch = AgentService._architecture_from_metadata(meta)
    assert arch["architectural_profile"] == ["Monólito modular", "Clean Architecture"]
    assert arch["deliverables"] == ["Aplicação web", "API"]


def test_stack_fallback_matches_real_project_automacao_juridica():
    """Reproduz as respostas reais do projeto 'Automação Jurídica Assistida'
    (questionnaire e67653fd) para garantir que o fallback produz a stack
    que o GP espera ver na UI (ao invés do '{}' atual)."""
    meta = {
        "project_name": "Automação Jurídica Assistida",
        "has_frontend": True,
        "frontend_stack": ["React", "Vite+React"],
        "frontend_language": "TypeScript",
        "frontend_type": ["Web SPA", "Portal autenticado"],
        "has_backend": True,
        "backend_language": "Python",
        "backend_framework": ["FastAPI"],
        "backend_type": ["REST API"],
        "database": "PostgreSQL",
        "database_profile": ["Transacional"],
        "uses_redis": True,
        "redis_purpose": ["Cache leitura", "Sessões"],
        "uses_ai": True,
        "ai_provider": ["Anthropic"],
    }

    stack = AgentService._stack_from_metadata(meta)

    # O GP verá React + FastAPI + PostgreSQL + Anthropic — não "{}"
    assert "React" in stack["frontend"]["stack"]
    assert stack["backend"]["language"] == "Python"
    assert "FastAPI" in stack["backend"]["framework"]
    assert stack["database"]["engine"] == "PostgreSQL"
    assert stack["ai"]["provider"] == ["Anthropic"]
