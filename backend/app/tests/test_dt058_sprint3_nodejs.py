"""DT-058 Sprint 3 ext — testes dos scaffolders Node.js (NestJS + Express).

Padrão idêntico aos demais scaffolders. NestJS é o default de Node.js
no despacho — Express é a alternativa minimalista quando o GP marca
explicitamente Express no Q28.
"""
import json

import pytest

from app.services.scaffolders import (
    ScaffoldFile,
    ScaffoldSpec,
    scaffold_nodejs_nestjs,
    scaffold_nodejs_express,
    dispatch_scaffold,
)


def _by_path(files, path: str) -> ScaffoldFile:
    for f in files:
        if f.path == path:
            return f
    raise AssertionError(f"Não gerado: {path}. Gerados: {[f.path for f in files]}")


# ===========================================================================
# NestJS
# ===========================================================================

def test_nestjs_scaffold_minimal_files():
    spec = ScaffoldSpec(project_name="DemoNest", project_slug="demo-nest", package="com.gca.demo")
    files = scaffold_nodejs_nestjs(spec)
    paths = {f.path for f in files}
    assert "package.json" in paths
    assert "tsconfig.json" in paths
    assert "nest-cli.json" in paths
    assert "src/main.ts" in paths
    assert "src/app.module.ts" in paths
    assert "src/app.controller.ts" in paths
    assert "src/app.service.ts" in paths
    assert "src/app.controller.spec.ts" in paths


def test_nestjs_package_json_is_valid():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_nodejs_nestjs(spec)
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "@nestjs/core" in pkg["dependencies"]
    assert "@nestjs/common" in pkg["dependencies"]
    assert "typescript" in pkg["devDependencies"]
    assert pkg["scripts"]["start:dev"].startswith("nest start")


def test_nestjs_includes_typeorm_when_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_nodejs_nestjs(spec)
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "@nestjs/typeorm" in pkg["dependencies"]
    assert "typeorm" in pkg["dependencies"]
    assert "pg" in pkg["dependencies"]
    # AppModule importa TypeOrmModule.forRoot
    app_module = _by_path(files, "src/app.module.ts").content
    assert "TypeOrmModule" in app_module
    assert "DATABASE_URL" in app_module


def test_nestjs_includes_cache_when_requires_redis():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_redis=True)
    files = scaffold_nodejs_nestjs(spec)
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "@nestjs/cache-manager" in pkg["dependencies"]
    assert "ioredis" in pkg["dependencies"]


def test_nestjs_includes_passport_when_requires_security():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", requires_security=True)
    files = scaffold_nodejs_nestjs(spec)
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "@nestjs/passport" in pkg["dependencies"]
    assert "@nestjs/jwt" in pkg["dependencies"]
    assert "passport-jwt" in pkg["dependencies"]


def test_nestjs_controller_has_health_and_greeting():
    spec = ScaffoldSpec(project_name="X", project_slug="x-app", package="com.gca.x")
    files = scaffold_nodejs_nestjs(spec)
    ctrl = _by_path(files, "src/app.controller.ts").content
    assert "@HealthCheck()" in ctrl
    assert "@Get('health')" in ctrl
    assert "@Get('api/greeting')" in ctrl
    assert "x-app" in ctrl  # slug no greeting


def test_nestjs_idempotent():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL", requires_redis=True)
    a = scaffold_nodejs_nestjs(spec)
    b = scaffold_nodejs_nestjs(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]


# ===========================================================================
# Express
# ===========================================================================

def test_express_scaffold_minimal_files():
    spec = ScaffoldSpec(project_name="DemoExp", project_slug="demo-exp", package="com.gca.demo")
    files = scaffold_nodejs_express(spec)
    paths = {f.path for f in files}
    assert "package.json" in paths
    assert "tsconfig.json" in paths
    assert "src/server.ts" in paths
    assert "src/app.ts" in paths
    assert "src/routes/health.ts" in paths
    assert "src/__tests__/app.test.ts" in paths


def test_express_package_json_uses_express():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_nodejs_express(spec)
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "express" in pkg["dependencies"]
    assert "helmet" in pkg["dependencies"]
    assert "cors" in pkg["dependencies"]
    # Não inclui NestJS deps
    assert "@nestjs/core" not in pkg["dependencies"]


def test_express_includes_pg_when_postgres():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL")
    files = scaffold_nodejs_express(spec)
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "pg" in pkg["dependencies"]
    assert "@types/pg" in pkg["devDependencies"]


def test_express_app_uses_helmet_and_cors():
    spec = ScaffoldSpec(project_name="X", project_slug="x-app", package="com.gca.x")
    files = scaffold_nodejs_express(spec)
    app = _by_path(files, "src/app.ts").content
    assert "import helmet" in app
    assert "import cors" in app
    assert "app.use(helmet())" in app
    assert "x-app" in app  # slug no greeting


def test_express_idempotent():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x", database="PostgreSQL", requires_security=True)
    a = scaffold_nodejs_express(spec)
    b = scaffold_nodejs_express(spec)
    assert [(f.path, f.content) for f in a] == [(f.path, f.content) for f in b]


# ===========================================================================
# Despacho — Node.js routing
# ===========================================================================

@pytest.mark.parametrize("language", ["Node.js", "node.js", "nodejs", "node"])
def test_dispatch_node_default_uses_nestjs(language):
    """Node.js sem hint → NestJS (default enterprise)."""
    stack = {"backend": {"language": language}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "nodejs_nestjs"


def test_dispatch_node_with_nestjs_explicit():
    stack = {"backend": {"language": "Node.js", "framework": "NestJS"}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "nodejs_nestjs"


def test_dispatch_node_with_express_explicit():
    """Express explícito (sem NestJS) → minimalista."""
    stack = {"backend": {"language": "Node.js", "framework": "Express"}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "nodejs_express"


def test_dispatch_node_with_both_frameworks_picks_nestjs():
    """Se framework lista contém ambos, NestJS prevalece (mais opinionado)."""
    stack = {"backend": {"language": "Node.js", "framework": ["NestJS", "Express"]}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "nodejs_nestjs"


def test_dispatch_typescript_alias_routes_to_nestjs():
    """Q24 do questionário tem TypeScript como linguagem frontend; se
    aparecer no backend.language por engano (ou alias custom), cai no
    despacho Node.js também."""
    stack = {"backend": {"language": "TypeScript"}}
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    name, _ = result
    assert name == "nodejs_nestjs"


def test_dispatch_node_propagates_postgres_to_nestjs():
    stack = {
        "backend": {"language": "Node.js"},
        "database": {"engine": "PostgreSQL"},
    }
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    _, files = result
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "@nestjs/typeorm" in pkg["dependencies"]
    assert "pg" in pkg["dependencies"]


def test_dispatch_node_propagates_redis_to_nestjs():
    stack = {
        "backend": {"language": "Node.js"},
        "cache": {"enabled": True},
    }
    result = dispatch_scaffold(stack, "Demo", "demo")
    assert result is not None
    _, files = result
    pkg = json.loads(_by_path(files, "package.json").content)
    assert "ioredis" in pkg["dependencies"]
