"""DT-076 Fase 2 — Gerador de DDL: schema.sql, seed.sql e migrations.

Cobre:
  - generate_ddl para PostgreSQL emite schema.sql + seed.sql
  - generate_ddl para MySQL dialeto correto (CHAR(36) em vez de UUID, etc)
  - Engine não suportado retorna lista vazia
  - Ordem topológica: users/products antes de sessions/orders (respeita FKs)
  - schema.sql contém CREATE TABLE de cada tabela
  - schema.sql termina com ALTER TABLE ADD CONSTRAINT (FKs)
  - Índices são gerados com CREATE INDEX
  - Comentários em tabela viram COMMENT ON TABLE em PG
  - BOOLEAN DEFAULT true/false é dialetizado
  - CURRENT_TIMESTAMP é preservado
  - UUID em PG vira UUID; em MySQL vira CHAR(36)
  - JSONB em PG preservado; em MySQL vira JSON
  - seed.sql usa ON CONFLICT DO NOTHING (PG) ou INSERT IGNORE (MySQL)
  - generate_migration retorna None para framework desconhecido
  - Migrations produzidas em 7 frameworks: Alembic/Flyway/Knex/TypeORM/Laravel/EFCore/go-migrate
  - Cada migration tem filename + content não-vazio e language correto
"""
from __future__ import annotations

import pytest

from app.services.data_model_inference import infer_data_model
from app.services.ddl_generator_service import (
    DDLArtifact, generate_ddl, generate_migration,
)


# ────────────────────────────────────────────────────────────────────────
# Helper: builder reutilizável
# ────────────────────────────────────────────────────────────────────────

def _sample_pg_dm():
    return infer_data_model(
        {"initiative_type": "E-commerce B2C", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )


def _sample_mysql_dm():
    return infer_data_model(
        {"initiative_type": "CRM interno", "handles_pii": True},
        {"database": {"engine": "MySQL"}},
    )


# ────────────────────────────────────────────────────────────────────────
# generate_ddl — PostgreSQL
# ────────────────────────────────────────────────────────────────────────

def test_generate_ddl_pg_emite_schema_e_seed():
    arts = generate_ddl(_sample_pg_dm())
    names = [a.filename for a in arts]
    assert "schema.sql" in names
    assert "seed.sql" in names


def test_schema_pg_cria_todas_as_tables():
    dm = _sample_pg_dm()
    schema = next(a for a in generate_ddl(dm) if a.filename == "schema.sql")
    for t in dm["tables"]:
        assert f"CREATE TABLE IF NOT EXISTS {t['name']}" in schema.content


def test_schema_pg_tem_extensao_pgcrypto():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "pgcrypto" in schema


def test_schema_pg_tem_fk_alter_table():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "ALTER TABLE" in schema
    assert "FOREIGN KEY" in schema
    assert "REFERENCES" in schema


def test_schema_pg_usa_uuid_nativo():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    # Coluna id UUID NOT NULL
    assert "id UUID NOT NULL" in schema


def test_schema_pg_usa_jsonb():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "JSONB" in schema


def test_schema_pg_timestamp_vira_timestamptz():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "TIMESTAMPTZ" in schema


def test_schema_pg_default_timestamp_preserva_current():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "DEFAULT CURRENT_TIMESTAMP" in schema


def test_schema_pg_boolean_default_dialetizado():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    # is_active TINYINT ou BOOLEAN, default TRUE
    assert "DEFAULT TRUE" in schema or "DEFAULT FALSE" in schema


def test_schema_pg_indexes_com_if_not_exists():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "CREATE INDEX IF NOT EXISTS" in schema or "CREATE UNIQUE INDEX IF NOT EXISTS" in schema


def test_schema_pg_comment_on_table():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "COMMENT ON TABLE" in schema


def test_seed_pg_usa_on_conflict():
    arts = generate_ddl(_sample_pg_dm())
    seed = next(a for a in arts if a.filename == "seed.sql").content
    assert "ON CONFLICT DO NOTHING" in seed


def test_seed_pg_tem_admin_row():
    arts = generate_ddl(_sample_pg_dm())
    seed = next(a for a in arts if a.filename == "seed.sql").content
    assert "admin@localhost" in seed
    assert "is_admin" in seed


# ────────────────────────────────────────────────────────────────────────
# generate_ddl — MySQL
# ────────────────────────────────────────────────────────────────────────

def test_generate_ddl_mysql_emite_schema():
    arts = generate_ddl(_sample_mysql_dm())
    assert any(a.filename == "schema.sql" for a in arts)


def test_schema_mysql_uuid_vira_char36():
    arts = generate_ddl(_sample_mysql_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "CHAR(36)" in schema
    assert "id UUID" not in schema  # não deve ter o canônico


def test_schema_mysql_jsonb_vira_json():
    arts = generate_ddl(_sample_mysql_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "JSONB" not in schema
    assert " JSON" in schema or "JSON NULL" in schema or "JSON," in schema


def test_schema_mysql_boolean_vira_tinyint():
    arts = generate_ddl(_sample_mysql_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "TINYINT(1)" in schema


def test_schema_mysql_boolean_default_0_ou_1():
    arts = generate_ddl(_sample_mysql_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "DEFAULT 1" in schema or "DEFAULT 0" in schema


def test_seed_mysql_usa_insert_ignore():
    arts = generate_ddl(_sample_mysql_dm())
    seed = next(a for a in arts if a.filename == "seed.sql").content
    assert "INSERT IGNORE" in seed


# ────────────────────────────────────────────────────────────────────────
# Engine não suportado
# ────────────────────────────────────────────────────────────────────────

def test_oracle_agora_gera_artefatos_em_v2():
    """MVP 11 Fase 11.6: Oracle saiu da lista vazia (V1) — agora emite DDL real."""
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "Oracle 19c"}},
    )
    artifacts = generate_ddl(dm)
    assert len(artifacts) == 2
    assert any(a.filename == "schema.sql" for a in artifacts)
    assert any(a.filename == "seed.sql" for a in artifacts)


def test_sqlite_agora_gera_artefatos_em_v2():
    """MVP 11 Fase 11.6: SQLite saiu da lista vazia (V1) — agora emite DDL real."""
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "SQLite"}},
    )
    artifacts = generate_ddl(dm)
    assert len(artifacts) == 2
    assert any(a.filename == "schema.sql" for a in artifacts)


def test_sem_engine_retorna_lista_vazia():
    dm = infer_data_model({}, {})
    assert generate_ddl(dm) == []


def test_engine_desconhecido_retorna_lista_vazia():
    """Engine fora dos 6 suportados (5 SQL + mongo) continua vazio."""
    dm = {"engine": "foobar", "tables": [], "foreign_keys": [], "seed_data": []}
    assert generate_ddl(dm) == []


# ────────────────────────────────────────────────────────────────────────
# Ordem topológica
# ────────────────────────────────────────────────────────────────────────

def test_users_antes_de_sessions_no_schema():
    """FK sessions.user_id → users exige users criar antes."""
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    pos_users = schema.find("CREATE TABLE IF NOT EXISTS users")
    pos_sessions = schema.find("CREATE TABLE IF NOT EXISTS sessions")
    assert pos_users > 0
    assert pos_sessions > pos_users


def test_customers_antes_de_orders_em_ecommerce():
    arts = generate_ddl(_sample_pg_dm())
    schema = next(a for a in arts if a.filename == "schema.sql").content
    pos_customers = schema.find("CREATE TABLE IF NOT EXISTS customers")
    pos_orders = schema.find("CREATE TABLE IF NOT EXISTS orders")
    assert pos_customers > 0
    assert pos_orders > pos_customers


# ────────────────────────────────────────────────────────────────────────
# Migrations — frameworks suportados
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("framework,expected_path,expected_lang", [
    ("alembic",   "alembic/versions/001_gca_init.py",          "python"),
    ("fastapi",   "alembic/versions/001_gca_init.py",          "python"),
    ("flyway",    "src/main/resources/db/migration/V1__init.sql", "sql"),
    ("spring",    "src/main/resources/db/migration/V1__init.sql", "sql"),
    ("kotlin-spring", "src/main/resources/db/migration/V1__init.sql", "sql"),
    ("knex",      "migrations/001_gca_init.js",                "javascript"),
    ("typeorm",   "src/migrations/0001-gca-init.ts",           "typescript"),
    ("laravel",   "database/migrations/2026_04_20_000001_gca_init.php", "php"),
    ("efcore",    "Migrations/20260420000001_GcaInit.cs",      "csharp"),
    ("go-migrate", "db/migrations/000001_gca_init.up.sql",     "sql"),
])
def test_migration_por_framework(framework, expected_path, expected_lang):
    dm = _sample_pg_dm()
    art = generate_migration(dm, framework)
    assert art is not None, f"framework {framework} não gerou migration"
    assert art.filename == expected_path
    assert art.language == expected_lang
    assert art.purpose == "migration"
    assert len(art.content) > 100
    # Todo migration path precisa referir às tables (schema embutido ou referência)
    assert "users" in art.content


def test_migration_framework_desconhecido_retorna_none():
    art = generate_migration(_sample_pg_dm(), "framework-que-nao-existe")
    assert art is None


def test_migration_alembic_tem_revision_id():
    art = generate_migration(_sample_pg_dm(), "alembic")
    assert "revision = " in art.content
    assert "down_revision = None" in art.content


def test_migration_typeorm_tem_classe():
    art = generate_migration(_sample_pg_dm(), "typeorm")
    assert "class GcaInit0001" in art.content
    assert "implements MigrationInterface" in art.content


def test_migration_laravel_tem_return_new_class():
    art = generate_migration(_sample_pg_dm(), "laravel")
    assert "return new class extends Migration" in art.content
