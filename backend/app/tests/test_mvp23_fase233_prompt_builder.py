"""MVP 23 Fase 23.3 — testes do codegen_prompt_builder consumindo RNF.

Valida:
- `_detect_stack_key`: 10 stacks canônicos + fallback 'generic'.
- `_rnf_stack_hints_block`: só emite dicas para controles que o
  contrato exige; stack-aware (Python → slowapi, Node → express-rate-limit,
  Java Spring → resilience4j, etc).
- `_rnf_full_block`: vazio quando rnf vazio; combina main block + stack hints.
- `build_scaffold_prompt` com `rnf_contracts=None` não contém bloco RNF
  (backward compat).
- `build_scaffold_prompt` com RNF preenchido inclui:
    - Bloco canônico (## Requisitos Não-Funcionais)
    - Dicas por stack (## Implementação recomendada)
    - Instrução de docstring documentar contrato atendido
- `build_regenerate_file_prompt` mesma semântica.
"""
import pytest

from app.services.codegen_prompt_builder import (
    _detect_stack_key,
    _rnf_full_block,
    _rnf_stack_hints_block,
    build_regenerate_file_prompt,
    build_scaffold_prompt,
)
from app.services.rnf_contracts import (
    ComplianceItem,
    PerformanceContract,
    RnfContracts,
    SecurityContract,
)


# ===========================================================================
# _detect_stack_key
# ===========================================================================


def test_detect_python():
    assert _detect_stack_key({"backend": {"language": "Python"}}) == "python"
    assert _detect_stack_key({"backend": {"language": "python"}}) == "python"


def test_detect_node_express():
    key = _detect_stack_key({
        "backend": {"language": "Node.js", "framework": "Express"},
    })
    assert key == "node_express"


def test_detect_node_nestjs():
    key = _detect_stack_key({
        "backend": {"language": "TypeScript", "framework": "NestJS"},
    })
    assert key == "node_nestjs"


def test_detect_java_spring():
    key = _detect_stack_key({
        "backend": {"language": "Java", "framework": "Spring Boot"},
    })
    assert key == "java_spring"


def test_detect_java_quarkus():
    key = _detect_stack_key({
        "backend": {"language": "Java", "framework": "Quarkus"},
    })
    assert key == "java_quarkus"


def test_detect_kotlin_spring():
    key = _detect_stack_key({
        "backend": {"language": "Kotlin", "framework": "Spring"},
    })
    assert key == "kotlin_spring"


def test_detect_csharp():
    assert _detect_stack_key({"backend": {"language": "C#"}}) == "csharp"
    assert _detect_stack_key({"backend": {"language": ".NET"}}) == "csharp"


def test_detect_go():
    assert _detect_stack_key({"backend": {"language": "Go"}}) == "go"


def test_detect_php():
    assert _detect_stack_key({"backend": {"language": "PHP"}}) == "php"


def test_detect_cpp():
    assert _detect_stack_key({"backend": {"language": "C++"}}) == "cpp"


def test_detect_generic_quando_vazio():
    assert _detect_stack_key(None) == "generic"
    assert _detect_stack_key({}) == "generic"
    assert _detect_stack_key({"backend": {}}) == "generic"
    assert _detect_stack_key({"backend": {"language": "Rust"}}) == "generic"


# ===========================================================================
# _rnf_stack_hints_block
# ===========================================================================


def test_stack_hints_vazio_quando_rnf_vazio():
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Python"}},
        RnfContracts(),
    )
    assert block == ""


def test_stack_hints_python_rate_limit():
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Python"}}, rnf,
    )
    assert "slowapi" in block.lower()
    assert "Python" in block


def test_stack_hints_node_express_rate_limit():
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=100),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Node.js", "framework": "Express"}}, rnf,
    )
    assert "express-rate-limit" in block


def test_stack_hints_node_nestjs_throttler():
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Node.js", "framework": "NestJS"}}, rnf,
    )
    assert "throttler" in block.lower() or "Throttle" in block


def test_stack_hints_java_spring_resilience4j():
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Java", "framework": "Spring Boot"}}, rnf,
    )
    assert "resilience4j" in block.lower()


def test_stack_hints_python_cwe_89():
    rnf = RnfContracts(
        security=SecurityContract(required_cwe_protections=("CWE-89",)),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Python"}}, rnf,
    )
    assert "CWE-89" in block
    assert "SQLAlchemy" in block or "parametriz" in block.lower()


def test_stack_hints_python_cwe_798_hardcoded_secrets():
    rnf = RnfContracts(
        security=SecurityContract(required_cwe_protections=("CWE-798",)),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Python"}}, rnf,
    )
    assert "CWE-798" in block
    assert "environ" in block or "settings" in block.lower()


def test_stack_hints_sensitive_data_pii():
    rnf = RnfContracts(
        security=SecurityContract(sensitive_data_categories=("PII", "financial")),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Python"}}, rnf,
    )
    assert "PII" in block
    assert "financial" in block


def test_stack_hints_nao_menciona_controles_nao_exigidos():
    """Contrato só com rate_limit: não aparece bloco de SQLi."""
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Python"}}, rnf,
    )
    assert "CWE-89" not in block
    assert "SQLi" not in block


def test_stack_hints_generic_vazio():
    """Stack desconhecida → sem hints específicos (retorna vazio)."""
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    block = _rnf_stack_hints_block(
        {"backend": {"language": "Rust"}}, rnf,
    )
    assert block == ""


# ===========================================================================
# _rnf_full_block
# ===========================================================================


def test_full_block_vazio_quando_rnf_none():
    assert _rnf_full_block(None, None) == ""


def test_full_block_vazio_quando_dict_vazio():
    assert _rnf_full_block({}, None) == ""


def test_full_block_combina_main_com_stack_hints():
    raw = {
        "security": {"required_cwe_protections": ["CWE-89"]},
    }
    block = _rnf_full_block(raw, {"backend": {"language": "Python"}})
    # Main block
    assert "Requisitos Não-Funcionais" in block
    # Stack hints
    assert "Implementação recomendada" in block
    assert "Python" in block


def test_full_block_so_main_quando_stack_nao_reconhecida():
    raw = {"security": {"rate_limit_rpm_public": 60}}
    block = _rnf_full_block(raw, {"backend": {"language": "Elixir"}})
    assert "Requisitos Não-Funcionais" in block
    assert "Implementação recomendada" not in block


# ===========================================================================
# build_scaffold_prompt — integração
# ===========================================================================


def _base_scaffold_args(**overrides):
    defaults = dict(
        project_name="Test Project",
        project_slug="test-proj",
        project_description="Projeto teste",
        stack={"backend": {"language": "Python", "framework": "FastAPI"}},
        architecture={"style": "Clean Architecture"},
        testing=None,
        modules=None,
        arguider_modules=None,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
    )
    defaults.update(overrides)
    return defaults


def test_scaffold_sem_rnf_contracts_nao_tem_bloco_rnf():
    """Backward compat: chamar sem rnf_contracts não quebra e não injeta bloco."""
    prompt = build_scaffold_prompt(**_base_scaffold_args())
    assert "Requisitos Não-Funcionais" not in prompt
    assert "Implementação recomendada" not in prompt


def test_scaffold_com_rnf_none_nao_tem_bloco():
    prompt = build_scaffold_prompt(**_base_scaffold_args(rnf_contracts=None))
    assert "Requisitos Não-Funcionais" not in prompt


def test_scaffold_com_rnf_vazio_dict_nao_tem_bloco():
    prompt = build_scaffold_prompt(**_base_scaffold_args(rnf_contracts={}))
    assert "Requisitos Não-Funcionais" not in prompt


def test_scaffold_com_rnf_preenchido_injeta_blocos():
    rnf = {
        "performance": {"latency_p95_ms": 200},
        "security": {
            "rate_limit_rpm_public": 60,
            "required_cwe_protections": ["CWE-89", "CWE-798"],
        },
        "compliance": [
            {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "runtime"},
        ],
    }
    prompt = build_scaffold_prompt(**_base_scaffold_args(rnf_contracts=rnf))
    # Main block
    assert "Requisitos Não-Funcionais" in prompt
    assert "200 ms" in prompt
    assert "60 req/min" in prompt
    assert "CWE-89" in prompt
    assert "LGPD" in prompt
    # Stack hints (Python)
    assert "slowapi" in prompt.lower()
    # Instrução de docstring
    assert "docstring" in prompt.lower()


def test_scaffold_stack_java_gera_hints_java():
    rnf = {"security": {"rate_limit_rpm_public": 60}}
    prompt = build_scaffold_prompt(**_base_scaffold_args(
        stack={"backend": {"language": "Java", "framework": "Spring Boot"}},
        rnf_contracts=rnf,
    ))
    assert "resilience4j" in prompt.lower() or "Bucket4j" in prompt


# ===========================================================================
# build_regenerate_file_prompt — integração
# ===========================================================================


def test_regenerate_sem_rnf_nao_tem_bloco():
    prompt = build_regenerate_file_prompt(
        project_name="Test",
        project_description="x",
        stack={"backend": {"language": "Python"}},
        architecture={},
        path="src/main.py",
        instruction=None,
        current_content=None,
    )
    assert "Requisitos Não-Funcionais" not in prompt


def test_regenerate_com_rnf_injeta_bloco():
    rnf = {
        "security": {
            "required_cwe_protections": ["CWE-89"],
            "rate_limit_rpm_public": 100,
        },
    }
    prompt = build_regenerate_file_prompt(
        project_name="Test",
        project_description="x",
        stack={"backend": {"language": "Python"}},
        architecture={},
        path="src/api.py",
        instruction=None,
        current_content=None,
        rnf_contracts=rnf,
    )
    assert "Requisitos Não-Funcionais" in prompt
    assert "CWE-89" in prompt
    assert "slowapi" in prompt.lower()


def test_regenerate_preserva_contrato_ao_reescrever():
    """Quando dev pede regeneração de arquivo existente, o contrato
    RNF do OCG ainda entra — garante que refactor não drope proteções."""
    rnf = {"security": {"required_cwe_protections": ["CWE-89"]}}
    prompt = build_regenerate_file_prompt(
        project_name="Test",
        project_description="x",
        stack={"backend": {"language": "Python"}},
        architecture={},
        path="src/db.py",
        instruction="refatore para usar async",
        current_content="def get_user(id): return db.raw(f'SELECT * FROM users WHERE id={id}')",
        rnf_contracts=rnf,
    )
    assert "CWE-89" in prompt
    assert "parametriz" in prompt.lower() or "SQLAlchemy" in prompt


# ===========================================================================
# Não quebra callers antigos
# ===========================================================================


def test_scaffold_sinatura_compativel_com_chamada_antiga():
    """Caller pré-MVP 23 que não passa rnf_contracts continua funcionando."""
    prompt = build_scaffold_prompt(
        project_name="Old",
        project_slug="old",
        project_description="old",
        stack={"backend": {"language": "Go"}},
        architecture=None,
        testing=None,
        modules=None,
        arguider_modules=None,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
        ingested_docs_context="",
    )
    # Prompt válido sem bloco RNF
    assert "Você é um engenheiro" in prompt
    assert "Requisitos Não-Funcionais" not in prompt


def test_regenerate_sinatura_compativel_com_chamada_antiga():
    prompt = build_regenerate_file_prompt(
        project_name="Old",
        project_description="old",
        stack=None,
        architecture=None,
        path="x.py",
        instruction=None,
        current_content=None,
    )
    assert "x.py" in prompt
    assert "Requisitos Não-Funcionais" not in prompt
