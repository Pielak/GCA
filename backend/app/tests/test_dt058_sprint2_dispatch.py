"""DT-058 Sprint 2.3 — `dispatch_scaffold` despacha por linguagem/framework.

Cobertura:
- Java sem framework hint → Spring Boot (default BR-friendly)
- Java + Spring Boot hint → Spring Boot
- Java + Quarkus hint → Quarkus
- Python/Go/C# (sem template ainda) → None
- Estrutura DT-046 vs legacy
- Resiliência a tipos errados / dados ausentes
"""
from app.services.scaffolders import dispatch_scaffold


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

def test_dispatch_java_default_uses_spring():
    """Sem framework explícito, Java default vai pra Spring Boot."""
    stack = {"backend": {"language": "Java"}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, files = result
    assert name == "java_spring"
    assert any(f.path == "pom.xml" for f in files)
    assert any("src/main/java" in f.path for f in files)


def test_dispatch_java_spring_explicit():
    stack = {
        "backend": {"language": "Java", "framework": "Spring Boot"},
    }
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, files = result
    assert name == "java_spring"
    pom = next(f for f in files if f.path == "pom.xml")
    assert "spring-boot-starter-parent" in pom.content


def test_dispatch_java_quarkus_explicit():
    stack = {
        "backend": {"language": "Java", "framework": "Quarkus"},
    }
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, files = result
    assert name == "java_quarkus"
    pom = next(f for f in files if f.path == "pom.xml")
    assert "quarkus-bom" in pom.content


def test_dispatch_java_with_framework_list():
    """OCG real persiste framework como lista (Q28 é multi-select)."""
    stack = {
        "backend": {"language": "Java", "framework": ["Quarkus", "Sem preferência"]},
    }
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "java_quarkus"


def test_dispatch_java_propagates_db_and_redis():
    stack = {
        "backend": {"language": "Java", "framework": "Spring Boot"},
        "database": {"engine": "PostgreSQL"},
        "cache": {"enabled": True, "purpose": ["Cache leitura"]},
    }
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    _, files = result
    pom = next(f for f in files if f.path == "pom.xml").content
    assert "<artifactId>postgresql</artifactId>" in pom
    assert "spring-boot-starter-data-redis" in pom


# ---------------------------------------------------------------------------
# Linguagens sem template ainda
# ---------------------------------------------------------------------------

def test_dispatch_python_returns_none():
    """Python ainda não tem scaffolder determinístico — caller cai no LLM."""
    stack = {"backend": {"language": "Python", "framework": "FastAPI"}}
    assert dispatch_scaffold(stack, "Demo", "demo") is None


def test_dispatch_go_returns_none():
    stack = {"backend": {"language": "Go"}}
    assert dispatch_scaffold(stack, "Demo", "demo") is None


def test_dispatch_csharp_returns_none():
    stack = {"backend": {"language": "C#"}}
    assert dispatch_scaffold(stack, "Demo", "demo") is None


def test_dispatch_unknown_language_returns_none():
    stack = {"backend": {"language": "Cobol"}}
    assert dispatch_scaffold(stack, "Demo", "demo") is None


# ---------------------------------------------------------------------------
# Estrutura legacy / vazia
# ---------------------------------------------------------------------------

def test_dispatch_legacy_primary_language_java():
    """OCG histórico (pre-DT-046) com `primary_language` no topo."""
    stack = {"primary_language": "Java"}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "java_spring"


def test_dispatch_empty_stack_returns_none():
    assert dispatch_scaffold({}, "Demo", "demo") is None


def test_dispatch_none_stack_returns_none():
    assert dispatch_scaffold(None, "Demo", "demo") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Default package — derivado do slug
# ---------------------------------------------------------------------------

def test_dispatch_default_package_from_slug():
    stack = {"backend": {"language": "Java"}}
    _, files = dispatch_scaffold(stack, "Automação Jurídica", "automacao-juridica")
    # Package esperado: com.gca.automacaojuridica
    pom = next(f for f in files if f.path == "pom.xml").content
    assert "<groupId>com.gca.automacaojuridica</groupId>" in pom
    # Arquivo Application.java com path correspondente
    assert any(
        "src/main/java/com/gca/automacaojuridica/" in f.path
        for f in files
    )


def test_dispatch_explicit_package_overrides_default():
    stack = {"backend": {"language": "Java"}}
    _, files = dispatch_scaffold(
        stack, "Demo", "demo-app", package="br.gov.juridico.demo"
    )
    pom = next(f for f in files if f.path == "pom.xml").content
    assert "<groupId>br.gov.juridico.demo</groupId>" in pom
    assert any(
        "src/main/java/br/gov/juridico/demo/" in f.path
        for f in files
    )


# ---------------------------------------------------------------------------
# Cenário real: Automação Jurídica em "modo Java"
# ---------------------------------------------------------------------------

def test_dispatch_full_real_project_in_java_mode():
    """Reproduz o que o GP da Automação Jurídica receberia se tivesse
    marcado Java/Spring (em vez de Python/FastAPI) no questionário.

    Stack vem com TODAS as opções do projeto real após DT-046/047:
    PostgreSQL, Redis, JWT/Auth, AI Anthropic.
    """
    stack = {
        "frontend": {"enabled": True, "stack": ["React", "Vite+React"]},
        "backend": {
            "enabled": True,
            "language": "Java",
            "framework": "Spring Boot",
            "type": "REST API",
        },
        "database": {"engine": "PostgreSQL", "profile": "Transacional"},
        "cache": {"enabled": True, "purpose": ["Cache leitura", "Sessões"]},
        "ai": {"enabled": True, "provider": ["Anthropic"]},
        "requires_security": True,
    }
    result = dispatch_scaffold(
        stack,
        "Automação Jurídica Assistida",
        "automacao-juridica-assistida",
    )
    assert result is not None
    name, files = result
    assert name == "java_spring"

    pom = next(f for f in files if f.path == "pom.xml").content
    # Tudo que o GP marcou está refletido
    assert "<artifactId>postgresql</artifactId>" in pom
    assert "spring-boot-starter-data-redis" in pom
    assert "spring-boot-starter-security" in pom

    # Estrutura mínima Spring Boot
    paths = {f.path for f in files}
    assert "pom.xml" in paths
    assert any(p.endswith("Application.java") for p in paths)
    assert "src/main/resources/application.yml" in paths
