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


# ---------------------------------------------------------------------------
# DT-047: TESTING_REQUIREMENTS / COMPLIANCE_CHECKLIST / DELIVERABLES /
# RISK_ANALYSIS
# ---------------------------------------------------------------------------

def test_testing_fallback_full_metadata():
    meta = {
        "test_types": ["Unitários", "Integração", "E2E", "Segurança"],
        "quality_gate": True,
        "qa_evidence": True,
        "criticality": "Alta",
    }
    t = AgentService._testing_from_metadata(meta)
    assert t["has_unit_tests"] is True
    assert t["has_integration_tests"] is True
    assert t["has_e2e_tests"] is True
    assert t["has_security_tests"] is True
    assert t["has_performance_tests"] is False  # não estava no test_types
    assert t["quality_gate_enabled"] is True
    assert t["formal_qa_enabled"] is True
    assert t["criticality"] == "Alta"
    assert t["coverage_target_pct"] == 80  # heurística para criticidade Alta
    assert t["source"] == "questionnaire_deterministic_fallback"


def test_testing_fallback_empty():
    t = AgentService._testing_from_metadata({})
    assert t["test_types"] == []
    assert t["has_unit_tests"] is False
    assert t["coverage_target_pct"] == 70  # default
    assert t["source"] == "questionnaire_deterministic_fallback"


def test_compliance_fallback_full_metadata():
    meta = {
        "security_controls": ["JWT", "HTTPS", "Cripto repouso", "Auditoria"],
        "info_classification": "Confidencial",
        "ai_restrictions": ["Anonimização"],
        "pipeline_deliverables": ["Arquitetura", "Plano segurança", "Plano testes"],
    }
    c = AgentService._compliance_from_metadata(meta)
    # 4 controles + 1 classificação + 1 restrição IA + 2 planos
    assert len(c) == 8
    controls = [item["control"] for item in c]
    assert "JWT" in controls
    assert "HTTPS" in controls
    assert "Classificação da informação: Confidencial" in controls
    assert "Restrição de IA: Anonimização" in controls
    assert "Plano segurança" in controls
    assert "Plano testes" in controls
    # Todos têm source rastreável
    assert all("source" in item for item in c)


def test_compliance_fallback_empty():
    c = AgentService._compliance_from_metadata({})
    assert c == []


def test_deliverables_fallback_full_metadata():
    meta = {
        "pipeline_deliverables": ["Arquitetura", "Stack", "Doc técnico", "Backlog"],
        "output_formats": ["Painel GCA", "Markdown", "PDF"],
    }
    d = AgentService._deliverables_from_metadata(meta)
    assert d["expected"] == ["Arquitetura", "Stack", "Doc técnico", "Backlog"]
    assert d["output_formats"] == ["Painel GCA", "Markdown", "PDF"]
    assert d["source"] == "questionnaire_deterministic_fallback"


def test_risk_fallback_from_metadata_only():
    """Sem pillar_results: riscos estruturais derivados apenas de criticidade/HA."""
    meta = {
        "criticality": "Alta",
        "high_availability": "Futuramente",
        "multi_tenant": "Sim",
        "uses_ai": True,
    }
    r = AgentService._risk_from_metadata(meta, pillar_results=None)
    assert r["high_findings"] == []
    structural = r["structural_risks"]
    assert len(structural) == 4  # criticidade alta + HA futuramente + multi-tenant + IA
    assert any("Criticidade alta" in s["risk"] for s in structural)
    assert any("Alta disponibilidade" in s["risk"] for s in structural)
    assert any("Multi-tenant" in s["risk"] for s in structural)
    assert any("IA" in s["risk"] for s in structural)


def test_risk_fallback_aggregates_pillar_findings():
    """Com pillar_results contendo findings high/critical — deve agregar."""
    from types import SimpleNamespace
    pr1 = SimpleNamespace(pillar_id=7, findings=[
        {"severity": "critical", "finding": "Falta MFA", "recommendation": "Implementar"},
        {"severity": "low", "finding": "Logo obsoleta", "recommendation": ""},
    ])
    pr2 = SimpleNamespace(pillar_id=2, findings=[
        {"severity": "high", "finding": "Sem plano LGPD", "recommendation": "Criar"},
    ])
    r = AgentService._risk_from_metadata({}, pillar_results=[pr1, pr2])
    # Só critical e high devem entrar
    assert len(r["high_findings"]) == 2
    severities = [f["severity"] for f in r["high_findings"]]
    assert "critical" in severities
    assert "high" in severities
    assert "low" not in severities


def test_testing_fallback_handles_non_dict():
    t = AgentService._testing_from_metadata(None)  # type: ignore[arg-type]
    assert t["source"] == "questionnaire_deterministic_fallback"


def test_compliance_fallback_handles_non_dict():
    assert AgentService._compliance_from_metadata(None) == []  # type: ignore[arg-type]


def test_deliverables_fallback_handles_non_dict():
    d = AgentService._deliverables_from_metadata(None)  # type: ignore[arg-type]
    assert d["source"] == "questionnaire_deterministic_fallback"


def test_risk_fallback_handles_non_dict():
    r = AgentService._risk_from_metadata(None)  # type: ignore[arg-type]
    assert r["source"] == "questionnaire_deterministic_fallback"


# ---------------------------------------------------------------------------


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
