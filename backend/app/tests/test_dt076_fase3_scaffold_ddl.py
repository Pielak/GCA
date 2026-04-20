"""DT-076 Fase 3 — `dispatch_scaffold` anexa artefatos DDL quando data_model
é fornecido e o engine é suportado.

Cobre:
  - Sem data_model → comportamento original preservado
  - data_model com engine não suportado → README_DDL.md placeholder
  - data_model suportado + Spring → V1__init.sql + schema.sql + seed.sql
  - data_model suportado + NestJS → TypeORM migration + schema.sql
  - data_model suportado + Laravel → PHP migration
  - data_model suportado + C# → EF Core migration
  - data_model suportado + Go → go-migrate
  - schema.sql referencia tables do OCG
  - README.md em db/ orienta ciclo
"""
from __future__ import annotations

from app.services.data_model_inference import infer_data_model
from app.services.scaffolders import dispatch_scaffold


def _spring_stack():
    return {
        "backend": {"language": "java", "framework": ["Spring Boot"]},
        "database": {"engine": "PostgreSQL"},
    }


def _nestjs_stack():
    return {
        "backend": {"language": "nodejs", "framework": ["NestJS"]},
        "database": {"engine": "PostgreSQL"},
    }


def _laravel_stack():
    return {
        "backend": {"language": "php", "framework": ["Laravel"]},
        "database": {"engine": "MySQL"},
    }


def _dm_pg():
    return infer_data_model(
        {"initiative_type": "generic", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )


# ────────────────────────────────────────────────────────────────────────
# Sem data_model preserva comportamento antigo
# ────────────────────────────────────────────────────────────────────────

def test_sem_data_model_nao_adiciona_ddl():
    result = dispatch_scaffold(_spring_stack(), "Demo", "demo")
    assert result is not None
    name, files = result
    paths = [f.path for f in files]
    assert "db/schema.sql" not in paths
    assert not any(p.startswith("src/main/resources/db/migration/") for p in paths)


def test_sem_data_model_mantem_scaffolder_name():
    name, _ = dispatch_scaffold(_spring_stack(), "Demo", "demo")
    assert name == "java_spring"


# ────────────────────────────────────────────────────────────────────────
# Engine não suportado → placeholder
# ────────────────────────────────────────────────────────────────────────

def test_engine_oracle_emite_placeholder():
    oracle_dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "Oracle 19c"}},
    )
    _, files = dispatch_scaffold(_spring_stack(), "Demo", "demo", data_model=oracle_dm)
    readme = next((f for f in files if f.path == "db/README_DDL.md"), None)
    assert readme is not None
    assert "Oracle" in readme.content
    # Sem schema.sql real (só placeholder)
    paths = [f.path for f in files]
    assert "db/schema.sql" not in paths


# ────────────────────────────────────────────────────────────────────────
# Spring (Flyway) — PostgreSQL suportado
# ────────────────────────────────────────────────────────────────────────

def test_spring_pg_gera_schema_e_seed_em_db():
    _, files = dispatch_scaffold(_spring_stack(), "Demo", "demo", data_model=_dm_pg())
    paths = [f.path for f in files]
    assert "db/schema.sql" in paths
    assert "db/seed.sql" in paths


def test_spring_pg_gera_flyway_v1():
    _, files = dispatch_scaffold(_spring_stack(), "Demo", "demo", data_model=_dm_pg())
    paths = [f.path for f in files]
    assert "src/main/resources/db/migration/V1__init.sql" in paths


def test_spring_pg_flyway_tem_create_table_users():
    _, files = dispatch_scaffold(_spring_stack(), "Demo", "demo", data_model=_dm_pg())
    flyway = next(f for f in files if f.path.endswith("V1__init.sql"))
    assert "CREATE TABLE IF NOT EXISTS users" in flyway.content
    assert "CREATE TABLE IF NOT EXISTS sessions" in flyway.content


# ────────────────────────────────────────────────────────────────────────
# NestJS (TypeORM)
# ────────────────────────────────────────────────────────────────────────

def test_nestjs_pg_gera_typeorm_migration():
    _, files = dispatch_scaffold(_nestjs_stack(), "Demo", "demo", data_model=_dm_pg())
    paths = [f.path for f in files]
    assert "src/migrations/0001-gca-init.ts" in paths


def test_nestjs_pg_typeorm_tem_classe():
    _, files = dispatch_scaffold(_nestjs_stack(), "Demo", "demo", data_model=_dm_pg())
    mig = next(f for f in files if f.path.endswith("0001-gca-init.ts"))
    assert "class GcaInit0001" in mig.content


# ────────────────────────────────────────────────────────────────────────
# Laravel (MySQL)
# ────────────────────────────────────────────────────────────────────────

def test_laravel_mysql_gera_php_migration():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "MySQL"}},
    )
    _, files = dispatch_scaffold(_laravel_stack(), "Demo", "demo", data_model=dm)
    paths = [f.path for f in files]
    assert any(p.endswith("gca_init.php") for p in paths)
    # schema.sql MySQL-specific
    schema = next(f for f in files if f.path == "db/schema.sql")
    assert "CHAR(36)" in schema.content


# ────────────────────────────────────────────────────────────────────────
# C# (EF Core)
# ────────────────────────────────────────────────────────────────────────

def test_csharp_gera_efcore_migration():
    stack = {
        "backend": {"language": "csharp", "framework": ["ASP.NET Core"]},
        "database": {"engine": "PostgreSQL"},
    }
    _, files = dispatch_scaffold(stack, "Demo", "demo", data_model=_dm_pg())
    paths = [f.path for f in files]
    assert any(p.endswith("GcaInit.cs") for p in paths)


# ────────────────────────────────────────────────────────────────────────
# Go (go-migrate)
# ────────────────────────────────────────────────────────────────────────

def test_go_gera_migrate_pair():
    stack = {
        "backend": {"language": "go", "framework": ["chi"]},
        "database": {"engine": "PostgreSQL"},
    }
    _, files = dispatch_scaffold(stack, "Demo", "demo", data_model=_dm_pg())
    paths = [f.path for f in files]
    assert "db/migrations/000001_gca_init.up.sql" in paths


# ────────────────────────────────────────────────────────────────────────
# README em db/
# ────────────────────────────────────────────────────────────────────────

def test_db_readme_orienta_ciclo():
    _, files = dispatch_scaffold(_spring_stack(), "Demo", "demo", data_model=_dm_pg())
    readme = next((f for f in files if f.path == "db/README.md"), None)
    assert readme is not None
    assert "PostgreSQL" in readme.content or "postgresql" in readme.content.lower()
    assert "flyway" in readme.content.lower()
    assert "__REPLACE_ON_BOOT__" in readme.content


# ────────────────────────────────────────────────────────────────────────
# Regression — outros testes DT-058 continuam passando
# ────────────────────────────────────────────────────────────────────────

def test_regression_dt058_spring_sem_data_model():
    """DT-058 existente: scaffolder Spring funciona sem data_model."""
    result = dispatch_scaffold(_spring_stack(), "Demo", "demo")
    assert result is not None
    name, files = result
    assert name == "java_spring"
    assert any(f.path == "pom.xml" for f in files)
