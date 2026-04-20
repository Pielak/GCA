"""MVP 11 Fase 11.6 — DT-076 V2 cobertura multi-DB.

Contrato §7 MVP 11 Fase 11.6:
- `ddl_generator_service` ganha Oracle, SQL Server, SQLite, MongoDB
  além dos já cobertos PostgreSQL + MySQL.
- 7 frameworks de migration (Alembic/Flyway/Knex/TypeORM/Laravel/EFCore/
  go-migrate) seguem cobertos com dialeto-específico quando aplicável.
- Laravel skipa Oracle; frameworks SQL-only skipam MongoDB.
- Testes por banco cobrindo geração básica + constraint + FK.
"""
import json

import pytest

from app.services.ddl_generator_service import (
    ALL_DIALECTS,
    SQL_DIALECTS,
    generate_ddl,
    generate_migration,
)


def _sample_data_model(engine: str) -> dict:
    """DATA_MODEL mínimo mas realista: 2 tabelas + PK + FK + index + seed."""
    return {
        "engine": engine,
        "tables": [
            {
                "name": "users",
                "comment": "Usuários do sistema",
                "primary_key": ["id"],
                "columns": [
                    {"name": "id", "type": "UUID", "nullable": False},
                    {"name": "email", "type": "VARCHAR", "nullable": False, "unique": True},
                    {"name": "is_active", "type": "BOOLEAN", "nullable": False, "default": True},
                    {"name": "created_at", "type": "TIMESTAMP", "nullable": False, "default": "CURRENT_TIMESTAMP"},
                ],
                "indexes": [
                    {"name": "idx_users_email", "columns": ["email"], "unique": True},
                ],
            },
            {
                "name": "sessions",
                "primary_key": ["id"],
                "columns": [
                    {"name": "id", "type": "UUID", "nullable": False},
                    {"name": "user_id", "type": "UUID", "nullable": False},
                    {"name": "token", "type": "TEXT", "nullable": False},
                ],
                "indexes": [],
            },
        ],
        "foreign_keys": [
            {
                "from_table": "sessions",
                "from_columns": ["user_id"],
                "to_table": "users",
                "to_columns": ["id"],
                "on_delete": "CASCADE",
            },
        ],
        "seed_data": [
            {
                "table": "users",
                "purpose": "Admin inicial",
                "rows": [
                    {"id": "00000000-0000-0000-0000-000000000001", "email": "admin@local", "is_active": True},
                ],
            },
        ],
    }


# ─── Cada dialeto emite schema.sql ou collections.json ────────────────


@pytest.mark.parametrize("engine", ["postgresql", "mysql", "sqlite", "sqlserver", "oracle"])
def test_sql_dialect_emits_schema_and_seed(engine):
    artifacts = generate_ddl(_sample_data_model(engine))
    names = {a.filename for a in artifacts}
    assert names == {"schema.sql", "seed.sql"}, f"{engine}: artefatos esperados não bateram — {names}"


def test_mongodb_emits_collections_and_seed_js():
    artifacts = generate_ddl(_sample_data_model("mongodb"))
    names = {a.filename for a in artifacts}
    assert names == {"collections.json", "seed.js"}
    # Valida que collections.json é JSON parseável e tem os validators
    coll = next(a for a in artifacts if a.filename == "collections.json")
    payload = json.loads(coll.content)
    assert "collections" in payload
    coll_names = {c["collection"] for c in payload["collections"]}
    assert coll_names == {"users", "sessions"}
    for c in payload["collections"]:
        assert "validator" in c
        assert "$jsonSchema" in c["validator"]


# ─── Schema SQL por dialeto tem assinatura dialetizada correta ─────────


def test_postgresql_schema_has_uuid_native_type():
    arts = generate_ddl(_sample_data_model("postgresql"))
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "UUID" in schema
    assert "TIMESTAMPTZ" in schema
    assert "BOOLEAN" in schema
    assert "pgcrypto" in schema
    # FK com ON DELETE CASCADE
    assert "ON DELETE CASCADE" in schema


def test_mysql_schema_uses_char36_for_uuid():
    arts = generate_ddl(_sample_data_model("mysql"))
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "CHAR(36)" in schema
    assert "TINYINT(1)" in schema
    assert "NO_ENGINE_SUBSTITUTION" in schema  # header mysql


def test_sqlite_schema_uses_text_for_uuid_and_pragma_fk():
    arts = generate_ddl(_sample_data_model("sqlite"))
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "PRAGMA foreign_keys = ON" in schema
    # UUID → TEXT em sqlite
    assert "id TEXT" in schema
    assert "ON DELETE CASCADE" in schema


def test_sqlserver_schema_uses_uniqueidentifier_and_object_id_guard():
    arts = generate_ddl(_sample_data_model("sqlserver"))
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "UNIQUEIDENTIFIER" in schema
    assert "BIT" in schema
    assert "IF OBJECT_ID" in schema  # CREATE TABLE guard T-SQL
    assert "DATETIME2" in schema


def test_oracle_schema_uses_raw16_and_exception_guard():
    arts = generate_ddl(_sample_data_model("oracle"))
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "RAW(16)" in schema
    assert "EXCEPTION WHEN OTHERS" in schema  # ORA-00955 tolerance
    assert "TIMESTAMP WITH TIME ZONE" in schema
    assert "SYSTIMESTAMP" in schema  # default NOW mapeado


# ─── Seed idempotente por dialeto ─────────────────────────────────────


def test_seed_dialect_specific_idempotency_clauses():
    pg = next(a for a in generate_ddl(_sample_data_model("postgresql")) if a.filename == "seed.sql")
    assert "ON CONFLICT DO NOTHING" in pg.content

    my = next(a for a in generate_ddl(_sample_data_model("mysql")) if a.filename == "seed.sql")
    assert "INSERT IGNORE" in my.content

    sl = next(a for a in generate_ddl(_sample_data_model("sqlite")) if a.filename == "seed.sql")
    assert "INSERT OR IGNORE" in sl.content

    ss = next(a for a in generate_ddl(_sample_data_model("sqlserver")) if a.filename == "seed.sql")
    assert "IF NOT EXISTS (SELECT 1 FROM" in ss.content

    ora = next(a for a in generate_ddl(_sample_data_model("oracle")) if a.filename == "seed.sql")
    assert "WHERE NOT EXISTS (SELECT 1 FROM" in ora.content and "FROM DUAL" in ora.content


# ─── MongoDB seed.js usa upsert idempotente ───────────────────────────


def test_mongodb_seed_uses_upsert():
    arts = generate_ddl(_sample_data_model("mongodb"))
    seed = next(a for a in arts if a.filename == "seed.js")
    assert "updateOne" in seed.content
    assert "upsert: true" in seed.content
    assert "$setOnInsert" in seed.content


# ─── FK + constraint presente em todos os dialetos SQL ────────────────


@pytest.mark.parametrize("engine", list(SQL_DIALECTS))
def test_fk_constraint_rendered_in_all_sql_dialects(engine):
    arts = generate_ddl(_sample_data_model(engine))
    schema = next(a for a in arts if a.filename == "schema.sql").content
    assert "ALTER TABLE sessions ADD CONSTRAINT" in schema
    assert "FOREIGN KEY (user_id) REFERENCES users(id)" in schema


# ─── Matriz framework × dialeto ───────────────────────────────────────


@pytest.mark.parametrize("engine", list(SQL_DIALECTS))
@pytest.mark.parametrize("framework", ["alembic", "flyway", "knex", "typeorm", "efcore", "go-migrate"])
def test_migration_frameworks_support_all_sql_dialects(framework, engine):
    """Alembic/Flyway/Knex/TypeORM/EFCore/go-migrate: todos os 5 SQL dialetos."""
    dm = _sample_data_model(engine)
    artifact = generate_migration(dm, framework)
    assert artifact is not None, f"{framework} × {engine} deveria emitir migration"
    assert artifact.content, "conteúdo vazio"


@pytest.mark.parametrize("engine", ["postgresql", "mysql", "sqlite", "sqlserver"])
def test_laravel_covers_supported_dialects(engine):
    """Laravel cobre pg/mysql/sqlite/sqlsrv; Oracle é skipado."""
    artifact = generate_migration(_sample_data_model(engine), "laravel")
    assert artifact is not None


def test_laravel_skipa_oracle():
    """Laravel não suporta Oracle nativo → retorna None."""
    assert generate_migration(_sample_data_model("oracle"), "laravel") is None


def test_sql_only_frameworks_skipam_mongo():
    """Alembic/Flyway/Knex/Laravel/go-migrate são SQL-only — mongo retorna None."""
    for f in ["alembic", "flyway", "knex", "laravel", "go-migrate"]:
        assert generate_migration(_sample_data_model("mongodb"), f) is None, f"{f} com mongo deveria ser None"


def test_typeorm_mongo_emits_create_collection_stub():
    """TypeORM com mongodb emite stub usando db.createCollection."""
    artifact = generate_migration(_sample_data_model("mongodb"), "typeorm")
    assert artifact is not None
    assert "createCollection" in artifact.content
    assert "users" in artifact.content
    assert "sessions" in artifact.content


def test_efcore_mongo_emits_cosmos_noop():
    """EFCore com mongodb emite stub Cosmos (container lazy)."""
    artifact = generate_migration(_sample_data_model("mongodb"), "efcore")
    assert artifact is not None
    assert "Cosmos" in artifact.content or "collections.json" in artifact.content


# ─── ALL_DIALECTS tem os 6 esperados ──────────────────────────────────


def test_all_dialects_declaration_has_six_entries():
    assert set(ALL_DIALECTS) == {"postgresql", "mysql", "sqlite", "sqlserver", "oracle", "mongodb"}
    assert set(SQL_DIALECTS) == {"postgresql", "mysql", "sqlite", "sqlserver", "oracle"}
