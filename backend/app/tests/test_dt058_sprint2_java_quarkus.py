"""DT-058 Sprint 2.2 — Scaffolder Quarkus.

Mesmo padrão do test do Spring Boot — valida estrutura, paths,
dependências, configs específicas de Quarkus (`application.properties`,
SmallRye Health, REST Jackson, etc).
"""
import xml.etree.ElementTree as ET

from app.services.scaffolders import (
    ScaffoldFile,
    ScaffoldSpec,
    scaffold_java_quarkus,
)


def _by_path(files, path: str) -> ScaffoldFile:
    for f in files:
        if f.path == path:
            return f
    raise AssertionError(f"Não gerado: {path}. Gerados: {[f.path for f in files]}")


# ---------------------------------------------------------------------------
# Estrutura mínima
# ---------------------------------------------------------------------------

def test_quarkus_scaffold_minimal_generates_required_files():
    spec = ScaffoldSpec(
        project_name="Demo Quarkus",
        project_slug="demo-quarkus",
        package="com.example.demo",
    )
    files = scaffold_java_quarkus(spec)
    paths = {f.path for f in files}

    assert "pom.xml" in paths
    assert ".gitignore" in paths
    assert "README.md" in paths
    assert "src/main/java/com/example/demo/GreetingResource.java" in paths
    assert "src/main/resources/application.properties" in paths
    assert "src/test/java/com/example/demo/GreetingResourceTest.java" in paths
    # Diferente do Spring: usa .properties, não .yml
    assert "src/main/resources/application.yml" not in paths


def test_quarkus_scaffold_files_have_gca_marker():
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_quarkus(spec)
    for f in files:
        if f.path in (".gitignore", "README.md"):
            continue
        assert "[gca:auto]" in f.content, f"{f.path} sem marcador [gca:auto]"


# ---------------------------------------------------------------------------
# pom.xml — Quarkus BOM, dependências
# ---------------------------------------------------------------------------

def test_quarkus_pom_is_well_formed():
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    root = ET.fromstring(pom)
    assert root.tag.endswith("project")


def test_quarkus_pom_has_quarkus_bom_and_plugin():
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    assert "quarkus-bom" in pom
    assert "quarkus-maven-plugin" in pom
    assert "quarkus-rest-jackson" in pom
    assert "quarkus-smallrye-health" in pom


def test_quarkus_pom_includes_postgres_when_database_postgres():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        database="PostgreSQL",
    )
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    assert "quarkus-jdbc-postgresql" in pom
    assert "quarkus-hibernate-orm-panache" in pom


def test_quarkus_pom_omits_postgres_when_database_other():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        database="MySQL",
    )
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    assert "quarkus-jdbc-postgresql" not in pom


def test_quarkus_pom_includes_redis_when_requires_redis():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        requires_redis=True,
    )
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    assert "quarkus-redis-client" in pom


def test_quarkus_pom_includes_security_when_requires_security():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        requires_security=True,
    )
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    assert "quarkus-smallrye-jwt" in pom


def test_quarkus_uses_spec_framework_version():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        framework_version="3.10.5",
    )
    files = scaffold_java_quarkus(spec)
    pom = _by_path(files, "pom.xml").content
    assert "<quarkus.platform.version>3.10.5</quarkus.platform.version>" in pom


# ---------------------------------------------------------------------------
# GreetingResource — endpoint exemplo
# ---------------------------------------------------------------------------

def test_quarkus_greeting_resource_uses_jakarta():
    """Quarkus 3.x usa Jakarta EE (não javax)."""
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo-app", package="br.com.juridico",
    )
    files = scaffold_java_quarkus(spec)
    resource = _by_path(
        files,
        "src/main/java/br/com/juridico/GreetingResource.java",
    ).content
    assert "package br.com.juridico;" in resource
    assert "import jakarta.ws.rs.GET;" in resource
    assert "import jakarta.ws.rs.Path;" in resource
    # Não pode ser javax.ws.rs
    assert "javax.ws.rs" not in resource


# ---------------------------------------------------------------------------
# application.properties — formato Quarkus (não YAML)
# ---------------------------------------------------------------------------

def test_quarkus_properties_uses_dotted_keys():
    spec = ScaffoldSpec(project_name="Demo", project_slug="demo", package="com.x.y")
    files = scaffold_java_quarkus(spec)
    props = _by_path(files, "src/main/resources/application.properties").content
    assert "quarkus.application.name=demo" in props
    assert "quarkus.http.port=" in props


def test_quarkus_properties_includes_postgres_when_database_postgres():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        database="PostgreSQL",
    )
    files = scaffold_java_quarkus(spec)
    props = _by_path(files, "src/main/resources/application.properties").content
    assert "quarkus.datasource.db-kind=postgresql" in props
    assert "DATABASE_URL" in props


def test_quarkus_properties_includes_redis_when_requires_redis():
    spec = ScaffoldSpec(
        project_name="Demo", project_slug="demo", package="com.x.y",
        requires_redis=True,
    )
    files = scaffold_java_quarkus(spec)
    props = _by_path(files, "src/main/resources/application.properties").content
    assert "quarkus.redis.hosts=" in props


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------

def test_quarkus_scaffold_is_idempotent():
    spec = ScaffoldSpec(
        project_name="X", project_slug="x", package="com.x.y",
        database="PostgreSQL", requires_security=True, requires_redis=True,
    )
    a = scaffold_java_quarkus(spec)
    b = scaffold_java_quarkus(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]
