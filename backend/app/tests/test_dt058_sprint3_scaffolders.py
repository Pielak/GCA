"""DT-058 Sprint 3 — testes dos scaffolders Go/C#/PHP/Kotlin.

Padrão idêntico aos do Sprint 2 (Java/Spring + Quarkus): valida
estrutura, paths, deps condicionais, idempotência, cenário real.
"""
import pytest
import xml.etree.ElementTree as ET
import json

from app.services.scaffolders import (
    ScaffoldFile,
    ScaffoldSpec,
    scaffold_go,
    scaffold_csharp_aspnet,
    scaffold_php_laravel,
    scaffold_kotlin_spring,
    dispatch_scaffold,
)


def _by_path(files, path: str) -> ScaffoldFile:
    for f in files:
        if f.path == path:
            return f
    raise AssertionError(f"Não gerado: {path}. Gerados: {[f.path for f in files]}")


# ===========================================================================
# Go
# ===========================================================================

def test_go_scaffold_minimal_files():
    spec = ScaffoldSpec(project_name="DemoGo", project_slug="demo-go", package="com.gca.demo")
    files = scaffold_go(spec)
    paths = {f.path for f in files}
    assert "go.mod" in paths
    assert ".gitignore" in paths
    assert "README.md" in paths
    assert "cmd/server/main.go" in paths
    assert "internal/server/server.go" in paths
    assert "internal/server/server_test.go" in paths


def test_go_module_path_translates_package():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.financehub")
    files = scaffold_go(spec)
    gomod = _by_path(files, "go.mod").content
    # com.gca.financehub → github.com/gca/financehub
    assert "module github.com/gca/financehub" in gomod


def test_go_includes_pgx_when_database_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_go(spec)
    gomod = _by_path(files, "go.mod").content
    assert "github.com/jackc/pgx/v5" in gomod


def test_go_includes_redis_when_requires_redis():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_redis=True)
    files = scaffold_go(spec)
    gomod = _by_path(files, "go.mod").content
    assert "github.com/redis/go-redis/v9" in gomod


def test_go_main_imports_internal_server():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_go(spec)
    main = _by_path(files, "cmd/server/main.go").content
    assert "github.com/gca/x/internal/server" in main


def test_go_server_uses_chi_router():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_go(spec)
    srv = _by_path(files, "internal/server/server.go").content
    assert "github.com/go-chi/chi/v5" in srv
    assert "/health" in srv
    assert "/api/greeting" in srv


def test_go_idempotent():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    a = scaffold_go(spec)
    b = scaffold_go(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]


# ===========================================================================
# C# / ASP.NET
# ===========================================================================

def test_csharp_scaffold_minimal_files():
    spec = ScaffoldSpec(project_name="DemoCs", project_slug="demo-cs", package="com.gca.demo")
    files = scaffold_csharp_aspnet(spec)
    paths = {f.path for f in files}
    # Class name = DemoCs (PascalCase)
    assert "DemoCs.sln" in paths
    assert "src/DemoCs.Api/DemoCs.Api.csproj" in paths
    assert "src/DemoCs.Api/Program.cs" in paths
    assert "src/DemoCs.Api/appsettings.json" in paths
    assert "tests/DemoCs.Api.Tests/DemoCs.Api.Tests.csproj" in paths
    assert "tests/DemoCs.Api.Tests/HealthEndpointTests.cs" in paths


def test_csharp_csproj_targets_net8():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_csharp_aspnet(spec)
    csproj = _by_path(files, "src/X.Api/X.Api.csproj").content
    assert "<TargetFramework>net8.0</TargetFramework>" in csproj


def test_csharp_csproj_includes_npgsql_when_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_csharp_aspnet(spec)
    csproj = _by_path(files, "src/X.Api/X.Api.csproj").content
    assert "Npgsql.EntityFrameworkCore.PostgreSQL" in csproj


def test_csharp_csproj_includes_redis_when_requires_redis():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_redis=True)
    files = scaffold_csharp_aspnet(spec)
    csproj = _by_path(files, "src/X.Api/X.Api.csproj").content
    assert "StackExchange.Redis" in csproj


def test_csharp_csproj_includes_jwt_when_requires_security():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_security=True)
    files = scaffold_csharp_aspnet(spec)
    csproj = _by_path(files, "src/X.Api/X.Api.csproj").content
    assert "Microsoft.AspNetCore.Authentication.JwtBearer" in csproj


def test_csharp_program_cs_has_health_and_greeting():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_csharp_aspnet(spec)
    prog = _by_path(files, "src/X.Api/Program.cs").content
    assert 'MapHealthChecks("/health")' in prog
    assert "/api/greeting" in prog
    assert "public partial class Program" in prog  # WebApplicationFactory


def test_csharp_appsettings_includes_postgres_when_database_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_csharp_aspnet(spec)
    appsettings = _by_path(files, "src/X.Api/appsettings.json").content
    parsed = json.loads(appsettings)
    assert "ConnectionStrings" in parsed
    assert "Default" in parsed["ConnectionStrings"]


def test_csharp_idempotent():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    a = scaffold_csharp_aspnet(spec)
    b = scaffold_csharp_aspnet(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]


# ===========================================================================
# PHP / Laravel
# ===========================================================================

def test_php_scaffold_minimal_files():
    spec = ScaffoldSpec(project_name="DemoPhp", project_slug="demo-php", package="com.gca.demo")
    files = scaffold_php_laravel(spec)
    paths = {f.path for f in files}
    assert "composer.json" in paths
    assert "artisan" in paths
    assert "public/index.php" in paths
    assert "bootstrap/app.php" in paths
    assert "routes/api.php" in paths
    assert "app/Http/Controllers/HealthController.php" in paths
    assert "phpunit.xml" in paths
    assert "tests/Feature/HealthEndpointTest.php" in paths


def test_php_composer_json_is_valid():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_php_laravel(spec)
    composer = _by_path(files, "composer.json").content
    parsed = json.loads(composer)
    assert "laravel/framework" in parsed["require"]
    assert "phpunit/phpunit" in parsed["require-dev"]


def test_php_composer_includes_sanctum_when_requires_security():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_security=True)
    files = scaffold_php_laravel(spec)
    composer = _by_path(files, "composer.json").content
    assert "laravel/sanctum" in composer


def test_php_artisan_is_executable():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_php_laravel(spec)
    artisan = _by_path(files, "artisan")
    assert artisan.executable is True


def test_php_env_includes_pgsql_when_database_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_php_laravel(spec)
    env = _by_path(files, ".env.example").content
    assert "DB_CONNECTION=pgsql" in env


def test_php_idempotent():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_security=True)
    a = scaffold_php_laravel(spec)
    b = scaffold_php_laravel(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]


# ===========================================================================
# Kotlin / Spring Boot
# ===========================================================================

def test_kotlin_scaffold_minimal_files():
    spec = ScaffoldSpec(project_name="DemoKt", project_slug="demo-kt", package="com.gca.demo")
    files = scaffold_kotlin_spring(spec)
    paths = {f.path for f in files}
    assert "build.gradle.kts" in paths
    assert "settings.gradle.kts" in paths
    assert "src/main/kotlin/com/gca/demo/DemoKtApplication.kt" in paths
    assert "src/main/resources/application.yml" in paths
    assert "src/test/kotlin/com/gca/demo/DemoKtApplicationTests.kt" in paths


def test_kotlin_build_gradle_uses_kts_dsl():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_kotlin_spring(spec)
    gradle = _by_path(files, "build.gradle.kts").content
    assert "plugins {" in gradle
    assert 'kotlin("jvm")' in gradle
    assert 'kotlin("plugin.spring")' in gradle


def test_kotlin_includes_postgres_when_database_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_kotlin_spring(spec)
    gradle = _by_path(files, "build.gradle.kts").content
    assert "spring-boot-starter-data-jpa" in gradle
    assert "org.postgresql:postgresql" in gradle


def test_kotlin_application_uses_idiomatic_kt():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_kotlin_spring(spec)
    app = _by_path(files, "src/main/kotlin/com/gca/x/XApplication.kt").content
    assert "package com.gca.x" in app
    assert "@SpringBootApplication" in app
    assert "open class XApplication" in app
    assert "fun main(args: Array<String>)" in app
    assert "runApplication<XApplication>(*args)" in app


def test_kotlin_security_config_when_requires_security():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_security=True)
    files = scaffold_kotlin_spring(spec)
    paths = {f.path for f in files}
    assert "src/main/kotlin/com/gca/x/config/XSecurityConfig.kt" in paths
    sec = _by_path(files, "src/main/kotlin/com/gca/x/config/XSecurityConfig.kt").content
    assert "open class XSecurityConfig" in sec


def test_kotlin_idempotent():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL", requires_security=True)
    a = scaffold_kotlin_spring(spec)
    b = scaffold_kotlin_spring(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]


# ===========================================================================
# Despacho — agora cobre todas as 6 linguagens
# ===========================================================================

@pytest.mark.parametrize("language, expected_scaffolder", [
    ("Java", "java_spring"),
    ("Kotlin", "kotlin_spring"),
    ("Go", "go_app"),
    ("C#", "csharp_aspnet"),
    ("PHP", "php_laravel"),
])
def test_dispatch_routes_each_language_to_correct_scaffolder(language, expected_scaffolder):
    stack = {"backend": {"language": language}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None, f"Sem scaffolder para {language}"
    name, _ = result
    assert name == expected_scaffolder


def test_dispatch_python_still_returns_none():
    """Python continua sem template — LLM-only por design (já tem ecossistema FastAPI maduro)."""
    stack = {"backend": {"language": "Python"}}
    assert dispatch_scaffold(stack, "Demo", "demo") is None


def test_dispatch_propagates_options_to_all_scaffolders():
    """Cada scaffolder respeita database/redis/security do spec."""
    full_stack = {
        "database": {"engine": "PostgreSQL"},
        "cache": {"enabled": True},
        "requires_security": True,
    }
    for lang, marker in [
        ("Java", "<artifactId>postgresql</artifactId>"),
        ("Kotlin", "org.postgresql:postgresql"),
        ("Go", "jackc/pgx/v5"),
        ("C#", "Npgsql.EntityFrameworkCore.PostgreSQL"),
    ]:
        stack = {**full_stack, "backend": {"language": lang}}
        result = dispatch_scaffold(stack, "Demo", "demo")
        assert result is not None
        _, files = result
        contents = "\n".join(f.content for f in files)
        assert marker in contents, f"{lang} não propagou postgres ({marker} ausente)"
