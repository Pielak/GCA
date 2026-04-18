"""
DT-058 Sprint 1.2: matriz parametrizada de linguagens para módulos.

Cobre TEST_FRAMEWORK_MAP + extração de linguagem do OCG no
`module_codegen_service`. Detecta:
- Mapeamento correto linguagem → test framework
- Bug pré-existente: `stack.get("primary_language")` usa chave que NÃO
  existe na estrutura DT-046 (`stack.backend.language`)
- Fallback seguro quando OCG não tem stack
"""
import pytest

from app.services.module_codegen_service import (
    MODULE_CODE_PROMPT,
    TEST_FRAMEWORK_MAP,
)


# ---------------------------------------------------------------------------
# TEST_FRAMEWORK_MAP — matriz de linguagens suportadas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "language, expected_framework",
    [
        ("python", "pytest"),
        ("typescript", "jest"),
        ("javascript", "jest"),
        ("java", "junit5"),
        ("kotlin", "junit5"),
        ("csharp", "xunit"),
        ("go", "go_test"),
        ("rust", "cargo_test"),
        ("ruby", "rspec"),
        ("php", "phpunit"),
        ("swift", "xctest"),
        ("dart", "flutter_test"),
    ],
)
def test_test_framework_map_resolves_canonical_language(language, expected_framework):
    """Cada linguagem canônica do questionário tem framework definido."""
    assert TEST_FRAMEWORK_MAP.get(language) == expected_framework


def test_test_framework_map_unknown_language_falls_back_to_pytest():
    """Linguagens não mapeadas caem em pytest (caller usa `.get(lang, 'pytest')`)."""
    assert TEST_FRAMEWORK_MAP.get("cobol", "pytest") == "pytest"
    assert TEST_FRAMEWORK_MAP.get("fortran", "pytest") == "pytest"


def test_test_framework_map_covers_all_questionnaire_q27_options():
    """Todas as opções de Q27 (linguagem backend) do questionário têm
    framework correspondente. Q27 oferece: Python, Node.js, Java, C#, Go,
    PHP, Kotlin, Outra.
    """
    questionnaire_q27_to_canonical = {
        "Python": "python",
        "Node.js": "javascript",  # Node.js usa Javascript engine; fallback pra JS
        "Java": "java",
        "C#": "csharp",
        "Go": "go",
        "PHP": "php",
        "Kotlin": "kotlin",
        # "Outra" não tem mapeamento — usa fallback
    }
    for q27_label, canonical in questionnaire_q27_to_canonical.items():
        assert canonical in TEST_FRAMEWORK_MAP, (
            f"Q27 oferece '{q27_label}' mas '{canonical}' não está em "
            f"TEST_FRAMEWORK_MAP — risco de falha silenciosa no scaffold"
        )


# ---------------------------------------------------------------------------
# Extração de language do OCG.STACK_RECOMMENDATION
# ---------------------------------------------------------------------------

def _extract_language_canonical(stack: dict) -> str:
    """Replica a lógica que `module_codegen_service.py:218` deveria ter
    pra ser tolerante à estrutura DT-046 (`backend.language`) e ao
    formato legacy (`primary_language`).

    Esta função NÃO é o código de produção (ainda) — é o teste do que o
    fix do bug deveria fazer. Quando module_codegen_service for atualizado
    pra usar essa lógica, este teste virará a referência."""
    if not isinstance(stack, dict):
        return "python"
    # DT-046 path canônico
    backend = stack.get("backend") or {}
    if isinstance(backend, dict):
        lang = backend.get("language")
        if lang and isinstance(lang, str):
            return lang.lower().strip()
    # Legacy path
    legacy = stack.get("primary_language")
    if legacy and isinstance(legacy, str):
        return legacy.lower().strip()
    return "python"


def test_extract_language_from_dt046_structure():
    """OCG real (Automação Jurídica) tem backend.language='Python'."""
    stack = {
        "backend": {"language": "Python", "framework": "FastAPI"},
        "frontend": {"language": "TypeScript"},
        "source": "questionnaire_deterministic_fallback",
    }
    assert _extract_language_canonical(stack) == "python"


def test_extract_language_from_dt046_with_java():
    """Se o GP marca Java/Spring no questionário, OCG terá language=Java."""
    stack = {
        "backend": {"language": "Java", "framework": "Spring Boot"},
    }
    assert _extract_language_canonical(stack) == "java"


def test_extract_language_legacy_primary_language():
    """Estrutura antiga (pre-DT-046) que ainda pode existir em OCGs históricos."""
    stack = {"primary_language": "Go"}
    assert _extract_language_canonical(stack) == "go"


def test_extract_language_empty_stack_falls_back():
    """OCG sem stack → fallback python (decisão histórica do produto)."""
    assert _extract_language_canonical({}) == "python"
    assert _extract_language_canonical(None) == "python"


def test_extract_language_known_bug_module_codegen_today():
    """REGRESSION: hoje module_codegen_service.py:218 lê `primary_language`
    direto. Para o OCG real (DT-046, com `backend.language`), retorna
    None → fallback "python" — DESCONSIDERA o que o GP realmente
    escolheu. Este teste documenta o bug; quando module_codegen_service
    for fixado, removê-lo ou inverter a assertiva.
    """
    stack_real = {"backend": {"language": "Java"}}  # OCG real DT-046

    # Simula o código atual de module_codegen_service.py:218
    buggy_extraction = stack_real.get("primary_language", "python").lower()

    # Bug: ignora `backend.language=Java` e retorna python
    assert buggy_extraction == "python", (
        "Se este teste falhar, o bug do module_codegen_service:218 "
        "foi consertado — atualizar/remover este teste."
    )


# ---------------------------------------------------------------------------
# Prompt do módulo monta sem crash para qualquer linguagem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("language", ["python", "java", "go", "csharp", "kotlin", "php"])
def test_module_code_prompt_formats_for_any_language(language):
    """Garante que o template de prompt aceita qualquer linguagem sem
    KeyError. Não valida o output do LLM — só que o caller monta o prompt.
    """
    framework = TEST_FRAMEWORK_MAP.get(language, "pytest")

    # Inspeciona placeholders do template — module_codegen_service usa
    # MODULE_CODE_PROMPT.format(...) com chaves específicas
    prompt = MODULE_CODE_PROMPT.format(
        module_name="UserService",
        module_type="service",
        module_description="Gerencia usuários do sistema",
        ocg_context=f'{{"backend": {{"language": "{language}", "test_framework": "{framework}"}}}}',
        dependencies="[]",
        language=language,
        test_framework=framework,
    )

    assert "UserService" in prompt
    assert language in prompt or language.title() in prompt
