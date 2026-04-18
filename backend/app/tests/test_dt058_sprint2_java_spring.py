"""
DT-058 Sprint 2.1 — Scaffolder Java/Spring Boot.

Testes determinísticos: validam estrutura, paths, packages, deps e
conteúdo crítico dos arquivos gerados. Não testam o output do LLM —
o scaffolder não chama LLM por design.
"""
import pytest
import xml.etree.ElementTree as ET

from app.services.scaffolders import (
    ScaffoldFile,
    ScaffoldSpec,
    scaffold_java_spring,
)
from app.services.scaffolders.java_spring import (
    _class_name_from_slug,
    _package_to_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _by_path(files, path: str) -> ScaffoldFile:
    for f in files:
        if f.path == path:
            return f
    raise AssertionError(f"Arquivo não gerado: {path}. Gerados: {[f.path for f in files]}")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def test_class_name_from_slug_pascal_case():
    assert _class_name_from_slug("automacao-juridica") == "AutomacaoJuridica"
    assert _class_name_from_slug("financehub-pro") == "FinancehubPro"
    assert _class_name_from_slug("simple") == "Simple"
    assert _class_name_from_slug("with_underscore_too") == "WithUnderscoreToo"
    assert _class_name_from_slug("") == "Application"  # fallback


def test_package_to_path_replaces_dots():
    assert _package_to_path("com.acme.app") == "com/acme/app"
    assert _package_to_path("br.com.gca.financehub") == "br/com/gca/financehub"


# ---------------------------------------------------------------------------
# Estrutura mínima — sem deps opcionais
# ---------------------------------------------------------------------------

def test_scaffold_minimal_generates_required_files():
    spec = ScaffoldSpec(
        project_name="Demo",
        project_slug="demo-app",
        package="com.example.demo",
    )
    files = scaffold_java_spring(spec)

    paths = {f.path for f in files}
    assert "pom.xml" in paths
    assert ".gitignore" in paths
    assert "README.md" in paths
    assert "src/main/java/com/example/demo/DemoAppApplication.java" in paths
    assert "src/main/resources/application.yml" in paths
    assert "src/test/java/com/example/demo/DemoAppApplicationTests.java" in paths
    # SecurityConfig só quando requires_security=True
    assert not any("SecurityConfig" in p for p in paths)


def test_scaffold_files_have_gca_auto_marker():
    """Todos os arquivos gerados devem carregar o marcador `[gca:auto]`
    para que regenerações posteriores saibam quais sobrescrever."""
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_spring(spec)

    # README e .gitignore têm comentários no estilo deles; os código devem ter
    code_or_config = [
        "pom.xml", ".gitignore", "src/main/resources/application.yml",
        "src/main/java/com/x/y/DemoApplication.java",
        "src/test/java/com/x/y/DemoApplicationTests.java",
    ]
    for p in code_or_config:
        f = _by_path(files, p)
        assert "[gca:auto]" in f.content, f"{p} sem marcador [gca:auto]"


# ---------------------------------------------------------------------------
# pom.xml — XML válido + dependências
# ---------------------------------------------------------------------------

def test_pom_xml_is_well_formed():
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml")

    # Deve parsear como XML — guard contra erro de escape/quebra
    root = ET.fromstring(pom.content)
    assert root.tag.endswith("project"), "Root tag deve ser <project>"


def test_pom_includes_postgres_when_database_postgres():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        database="PostgreSQL",
    )
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml").content
    assert "<artifactId>postgresql</artifactId>" in pom
    assert "spring-boot-starter-data-jpa" in pom


def test_pom_omits_postgres_when_database_other():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        database="MySQL",
    )
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml").content
    assert "<artifactId>postgresql</artifactId>" not in pom


def test_pom_includes_redis_when_requires_redis():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        requires_redis=True,
    )
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml").content
    assert "spring-boot-starter-data-redis" in pom


def test_pom_includes_security_when_requires_security():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        requires_security=True,
    )
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml").content
    assert "spring-boot-starter-security" in pom


def test_pom_uses_spec_java_version():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        java_version="17",
    )
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml").content
    assert "<java.version>17</java.version>" in pom


def test_pom_uses_spec_framework_version():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        framework_version="3.2.5",
    )
    files = scaffold_java_spring(spec)
    pom = _by_path(files, "pom.xml").content
    assert "<version>3.2.5</version>" in pom


# ---------------------------------------------------------------------------
# Application.java — entrypoint Spring Boot
# ---------------------------------------------------------------------------

def test_application_java_has_correct_package_and_annotations():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo-app",
        package="br.com.gca.financehub",
    )
    files = scaffold_java_spring(spec)
    app = _by_path(
        files,
        "src/main/java/br/com/gca/financehub/DemoAppApplication.java",
    ).content

    assert "package br.com.gca.financehub;" in app
    assert "@SpringBootApplication" in app
    assert "public class DemoAppApplication" in app
    assert "SpringApplication.run(DemoAppApplication.class, args);" in app


# ---------------------------------------------------------------------------
# application.yml — configs por opção
# ---------------------------------------------------------------------------

def test_application_yml_has_postgres_block_when_database_postgres():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        database="PostgreSQL",
    )
    files = scaffold_java_spring(spec)
    yml = _by_path(files, "src/main/resources/application.yml").content
    assert "datasource:" in yml
    assert "postgresql" in yml.lower()
    assert "DATABASE_URL" in yml  # variabilizado por env


def test_application_yml_omits_datasource_when_no_database():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
    )
    files = scaffold_java_spring(spec)
    yml = _by_path(files, "src/main/resources/application.yml").content
    assert "datasource:" not in yml


def test_application_yml_has_actuator_health():
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_spring(spec)
    yml = _by_path(files, "src/main/resources/application.yml").content
    assert "include: health,info,metrics" in yml


# ---------------------------------------------------------------------------
# Determinismo — chamar duas vezes produz output idêntico
# ---------------------------------------------------------------------------

def test_scaffold_is_idempotent():
    spec = ScaffoldSpec(
        project_name="Automação Jurídica",
        project_slug="automacao-juridica",
        package="br.gov.juridico",
        database="PostgreSQL",
        requires_security=True,
        requires_redis=True,
    )
    first = scaffold_java_spring(spec)
    second = scaffold_java_spring(spec)

    # Mesmo número de arquivos, mesmas paths, mesmos contents
    assert len(first) == len(second)
    for f1, f2 in zip(first, second):
        assert f1.path == f2.path
        assert f1.content == f2.content


# ---------------------------------------------------------------------------
# Cenário "real" — projeto Automação Jurídica do dogfood
# ---------------------------------------------------------------------------

def test_scaffold_real_project_automacao_juridica():
    """Reproduz a config que o GP de Automação Jurídica responderia se
    tivesse marcado Java/Spring no questionário (em vez de Python/FastAPI)."""
    spec = ScaffoldSpec(
        project_name="Automação Jurídica Assistida",
        project_slug="automacao-juridica-assistida",
        package="br.com.juridico.assistida",
        database="PostgreSQL",
        requires_redis=True,  # Q33 marcou Redis
        requires_security=True,  # Q43 marcou JWT/Auth
    )
    files = scaffold_java_spring(spec)

    # Estrutura mínima esperada do dogfood
    paths = {f.path for f in files}
    assert "pom.xml" in paths
    assert any(p.endswith("Application.java") for p in paths)
    assert any("SecurityConfig.java" in p for p in paths)
    assert "src/main/resources/application.yml" in paths

    pom = _by_path(files, "pom.xml").content
    # Tudo o que o GP marcou está refletido no scaffold
    assert "spring-boot-starter-web" in pom
    assert "spring-boot-starter-data-jpa" in pom
    assert "spring-boot-starter-data-redis" in pom
    assert "spring-boot-starter-security" in pom
    assert "<artifactId>postgresql</artifactId>" in pom
