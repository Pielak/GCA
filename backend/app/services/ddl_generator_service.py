"""DT-076 Fase 2 — Gerador de DDL a partir do DATA_MODEL do OCG.

Emite artefatos reais (não mais placeholder) pro CodeGen incluir na
entrega inicial do projeto:
  - `schema.sql` nativo do dialeto
  - Migration no formato do framework declarado no OCG
  - `seed.sql` idempotente

V1 cobre dois dialetos (DT-076 Fase 2):
  - **PostgreSQL**: UUID via `gen_random_uuid()`, JSONB, BIGSERIAL
  - **MySQL 8+**: UUID via `UUID()` função, JSON, BIGINT AUTO_INCREMENT

Outros dialetos (Oracle, SQLServer, SQLite) disparam warning e emitem
schema.sql portável em ANSI como best-effort; migration no framework
é skipada — GP escreve manualmente.

Inputs esperados: output de `data_model_inference.infer_data_model`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DDLArtifact:
    """Artefato gerado pelo DDL generator."""
    filename: str
    content: str
    language: str  # sql, python, java, typescript, etc.
    purpose: str   # schema, migration, seed, entity


SCHEMA_HEADER = {
    "postgresql": (
        "-- Schema gerado pelo GCA (DT-076 Fase 2) a partir do OCG.DATA_MODEL\n"
        "-- Dialect: PostgreSQL 12+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n\n"
        'CREATE EXTENSION IF NOT EXISTS "pgcrypto";\n\n'
    ),
    "mysql": (
        "-- Schema gerado pelo GCA (DT-076 Fase 2) a partir do OCG.DATA_MODEL\n"
        "-- Dialect: MySQL 8.0+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n\n"
        "SET sql_mode = 'STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION';\n\n"
    ),
}


def generate_ddl(data_model: dict[str, Any]) -> list[DDLArtifact]:
    """Gera schema.sql + seed.sql pra dialetos suportados.

    Retorna lista vazia quando engine não é suportado (callers devem
    verificar `data_model["dialect_supported"]` antes). Se a lista
    vier vazia, o CodeGen gera placeholder orientando o GP.
    """
    engine = (data_model or {}).get("engine")
    if engine not in ("postgresql", "mysql"):
        return []

    tables = data_model.get("tables") or []
    fks = data_model.get("foreign_keys") or []
    seed = data_model.get("seed_data") or []

    schema_sql = _render_schema_sql(engine, tables, fks)
    seed_sql = _render_seed_sql(engine, seed)

    return [
        DDLArtifact(
            filename="schema.sql",
            content=schema_sql,
            language="sql",
            purpose="schema",
        ),
        DDLArtifact(
            filename="seed.sql",
            content=seed_sql,
            language="sql",
            purpose="seed",
        ),
    ]


def generate_migration(
    data_model: dict[str, Any], framework: str,
) -> DDLArtifact | None:
    """Gera migration no formato do framework declarado.

    Frameworks suportados na V1 da DT-076:
      - 'fastapi' / 'alembic' → Alembic revision (Python)
      - 'spring' / 'flyway' → Flyway V1__init.sql (SQL nativo)
      - 'express' / 'knex' → Knex migration (JavaScript)
      - 'nestjs' / 'typeorm' → TypeORM migration (TypeScript)
      - 'laravel' → Laravel migration (PHP class)
      - 'aspnet' / 'efcore' → EF Core migration (C#)
      - 'go' / 'migrate' → golang-migrate sql pair

    Retorna None quando framework não suportado (CodeGen usa
    schema.sql puro como fallback).
    """
    f = (framework or "").lower().strip()
    engine = (data_model or {}).get("engine")

    # Mapas de aliases → handler
    if f in ("alembic", "fastapi", "python"):
        return _migration_alembic(data_model)
    if f in ("flyway", "spring", "java-spring", "kotlin-spring", "java", "kotlin"):
        return _migration_flyway(data_model, engine)
    if f in ("knex", "express", "nodejs-express"):
        return _migration_knex(data_model)
    if f in ("typeorm", "nestjs", "nodejs-nestjs"):
        return _migration_typeorm(data_model)
    if f in ("laravel", "php", "php-laravel"):
        return _migration_laravel(data_model)
    if f in ("efcore", "aspnet", "csharp", "c#"):
        return _migration_efcore(data_model)
    if f in ("go-migrate", "golang-migrate", "go", "go-app"):
        return _migration_go_migrate(data_model, engine)

    return None


# ---------------------------------------------------------------------------
# schema.sql renderer
# ---------------------------------------------------------------------------

def _render_schema_sql(
    engine: str, tables: list[dict[str, Any]], fks: list[dict[str, Any]],
) -> str:
    """Monta schema.sql ordenando tabelas por dependência (users antes de FKs)."""
    sorted_tables = _topo_sort_tables(tables, fks)

    parts = [SCHEMA_HEADER[engine]]
    for t in sorted_tables:
        parts.append(_render_create_table(t, engine))
        parts.append("\n")
        for idx in t.get("indexes") or []:
            parts.append(_render_create_index(t["name"], idx, engine))
        parts.append("\n")

    # FKs emitidas após todas as tables, pra evitar ordem circular.
    if fks:
        parts.append("-- Foreign keys\n")
        for fk in fks:
            parts.append(_render_fk(fk, engine))
            parts.append("\n")

    return "".join(parts)


def _render_create_table(t: dict[str, Any], engine: str) -> str:
    name = t["name"]
    cols = t.get("columns") or []
    pk = t.get("primary_key") or []
    comment = t.get("comment") or ""

    col_lines = [_render_column(c, engine) for c in cols]
    body = ",\n  ".join(col_lines)

    lines = [f"-- {comment}" if comment else f"-- Tabela {name}"]
    lines.append(f"CREATE TABLE IF NOT EXISTS {name} (")
    lines.append(f"  {body}")
    if pk:
        lines.append(f",  PRIMARY KEY ({', '.join(pk)})")
    lines.append(");")
    if comment and engine == "postgresql":
        # Postgres suporta COMMENT ON TABLE; MySQL usa inline que seria verboso.
        safe = comment.replace("'", "''")
        lines.append(f"COMMENT ON TABLE {name} IS '{safe}';")
    return "\n".join(lines) + "\n"


def _render_column(c: dict[str, Any], engine: str) -> str:
    name = c["name"]
    ctype = _dialect_type(c["type"], engine)
    nullable = c.get("nullable", False)
    default = c.get("default")
    unique = c.get("unique", False)

    parts = [name, ctype]
    if not nullable:
        parts.append("NOT NULL")
    if default is not None:
        parts.append(f"DEFAULT {_dialect_default(default, c['type'], engine)}")
    if unique:
        parts.append("UNIQUE")
    return " ".join(parts)


def _render_create_index(table: str, idx: dict[str, Any], engine: str) -> str:
    iname = idx["name"]
    cols = ", ".join(idx["columns"])
    unique = "UNIQUE " if idx.get("unique") else ""
    if engine == "postgresql":
        return f"CREATE {unique}INDEX IF NOT EXISTS {iname} ON {table} ({cols});\n"
    return f"CREATE {unique}INDEX {iname} ON {table} ({cols});\n"


def _render_fk(fk: dict[str, Any], engine: str) -> str:
    from_t = fk["from_table"]
    from_c = ", ".join(fk["from_columns"])
    to_t = fk["to_table"]
    to_c = ", ".join(fk["to_columns"])
    on_delete = fk.get("on_delete", "RESTRICT")
    constraint = f"fk_{from_t}_{to_t}"
    return (
        f"ALTER TABLE {from_t} ADD CONSTRAINT {constraint} "
        f"FOREIGN KEY ({from_c}) REFERENCES {to_t}({to_c}) "
        f"ON DELETE {on_delete};\n"
    )


def _dialect_type(canonical_type: str, engine: str) -> str:
    """Mapeia tipos canônicos pra tipos nativos do dialeto.

    Canonical (usado pelo inferencer) → dialeto:
      UUID → postgresql: UUID, mysql: CHAR(36)
      BIGSERIAL → postgresql: BIGSERIAL, mysql: BIGINT AUTO_INCREMENT
      BOOLEAN → postgresql: BOOLEAN, mysql: TINYINT(1)
      JSONB → postgresql: JSONB, mysql: JSON (já deveria ter sido normalizado upstream)
      TIMESTAMP → postgresql: TIMESTAMPTZ, mysql: TIMESTAMP
    """
    t = canonical_type.upper().strip()
    if engine == "postgresql":
        mapping = {
            "UUID": "UUID",
            "BIGSERIAL": "BIGSERIAL",
            "BOOLEAN": "BOOLEAN",
            "JSONB": "JSONB",
            "JSON": "JSONB",
            "TIMESTAMP": "TIMESTAMPTZ",
        }
        return mapping.get(t, canonical_type)
    # mysql
    mapping = {
        "UUID": "CHAR(36)",
        "BIGSERIAL": "BIGINT AUTO_INCREMENT",
        "BOOLEAN": "TINYINT(1)",
        "JSONB": "JSON",
        "TIMESTAMP": "TIMESTAMP",
    }
    # MySQL não suporta INTEGER DEFAULT em TEXT, CHAR lengths fixos
    return mapping.get(t, canonical_type)


def _dialect_default(default_val: Any, canonical_type: str, engine: str) -> str:
    """Renderiza DEFAULT dialetizado. Trata UUID, timestamp, boolean e literal."""
    t = (canonical_type or "").upper()
    s = str(default_val).strip()

    # Caso CURRENT_TIMESTAMP / NOW
    if s.upper() in ("CURRENT_TIMESTAMP", "NOW()", "NOW"):
        return "CURRENT_TIMESTAMP"

    # Booleanos
    if t == "BOOLEAN":
        val = str(default_val).lower()
        if val in ("true", "1"):
            return "TRUE" if engine == "postgresql" else "1"
        return "FALSE" if engine == "postgresql" else "0"

    # String já veio com aspas
    if s.startswith("'") and s.endswith("'"):
        return s

    # Número literal
    try:
        float(s)
        return s
    except ValueError:
        pass

    # Fallback: aspas
    return f"'{s}'"


def _topo_sort_tables(
    tables: list[dict[str, Any]], fks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ordena tabelas para que referenciadas venham antes. FK cíclica usa ordem original."""
    deps: dict[str, set[str]] = {t["name"]: set() for t in tables}
    for fk in fks:
        if fk["from_table"] in deps and fk["to_table"] in deps:
            deps[fk["from_table"]].add(fk["to_table"])

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_name = {t["name"]: t for t in tables}

    def visit(name: str, trail: tuple[str, ...] = ()) -> None:
        if name in seen:
            return
        if name in trail:
            return  # ciclo — quebra silenciosamente
        for dep in sorted(deps.get(name, ())):
            visit(dep, trail + (name,))
        seen.add(name)
        if name in by_name:
            ordered.append(by_name[name])

    for t in tables:
        visit(t["name"])

    # Append quaisquer remanescentes (segurança)
    for t in tables:
        if t["name"] not in seen:
            ordered.append(t)
    return ordered


# ---------------------------------------------------------------------------
# seed.sql renderer
# ---------------------------------------------------------------------------

def _render_seed_sql(engine: str, seed: list[dict[str, Any]]) -> str:
    parts = [
        "-- Seed idempotente gerado pelo GCA. Rode após schema.sql.\n"
        "-- Placeholders: '__REPLACE_ON_BOOT__' devem ser resolvidos pelo\n"
        "-- primeiro boot do backend (hash bcrypt real da senha admin).\n\n",
    ]
    for entry in seed:
        table = entry["table"]
        purpose = entry.get("purpose") or ""
        if purpose:
            parts.append(f"-- {purpose}\n")
        for row in entry.get("rows") or []:
            parts.append(_render_insert(engine, table, row))
    return "".join(parts)


def _render_insert(engine: str, table: str, row: dict[str, Any]) -> str:
    cols = list(row.keys())
    vals = [_sql_value(v, engine) for v in row.values()]
    col_list = ", ".join(cols)
    val_list = ", ".join(vals)
    # ON CONFLICT / IGNORE pra idempotência
    if engine == "postgresql":
        return (
            f"INSERT INTO {table} ({col_list}) VALUES ({val_list}) "
            "ON CONFLICT DO NOTHING;\n"
        )
    return f"INSERT IGNORE INTO {table} ({col_list}) VALUES ({val_list});\n"


def _sql_value(v: Any, engine: str) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        if engine == "postgresql":
            return "TRUE" if v else "FALSE"
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


# ---------------------------------------------------------------------------
# Migration renderers — um por framework
# ---------------------------------------------------------------------------

def _migration_alembic(data_model: dict[str, Any]) -> DDLArtifact:
    """Alembic migration. Usa op.execute(schema.sql) como atalho pragmático."""
    schema = _render_schema_sql(
        data_model["engine"], data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    # Escapa para inclusão como string Python (triplas aspas)
    escaped = schema.replace('"""', '\\"\\"\\"')
    content = f'''"""Initial schema generated by GCA.

Revision ID: 001_gca_init
Revises:
Create Date: (gerado automaticamente)
"""
from alembic import op

# revision identifiers
revision = "001_gca_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
{escaped}
""")


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade da migration inicial não é suportado. "
        "Rode pg_dump+drop manualmente se precisar."
    )
'''
    return DDLArtifact(
        filename="alembic/versions/001_gca_init.py",
        content=content,
        language="python",
        purpose="migration",
    )


def _migration_flyway(data_model: dict[str, Any], engine: str) -> DDLArtifact:
    """Flyway usa arquivo .sql direto — reusa schema.sql."""
    content = _render_schema_sql(
        engine, data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    return DDLArtifact(
        filename="src/main/resources/db/migration/V1__init.sql",
        content=content,
        language="sql",
        purpose="migration",
    )


def _migration_knex(data_model: dict[str, Any]) -> DDLArtifact:
    """Knex migration JS usa raw SQL pra preservar compatibilidade."""
    schema = _render_schema_sql(
        data_model["engine"], data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    escaped = schema.replace("`", "\\`")
    content = f'''/**
 * Knex migration — initial schema from GCA DATA_MODEL.
 */
exports.up = async (knex) => {{
  await knex.raw(`{escaped}`);
}};

exports.down = async () => {{
  throw new Error("Downgrade nao suportado. Drop manual se necessario.");
}};
'''
    return DDLArtifact(
        filename="migrations/001_gca_init.js",
        content=content,
        language="javascript",
        purpose="migration",
    )


def _migration_typeorm(data_model: dict[str, Any]) -> DDLArtifact:
    schema = _render_schema_sql(
        data_model["engine"], data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    escaped = schema.replace("`", "\\`")
    content = f'''import {{ MigrationInterface, QueryRunner }} from "typeorm";

export class GcaInit0001 implements MigrationInterface {{
  name = "GcaInit0001";

  public async up(queryRunner: QueryRunner): Promise<void> {{
    await queryRunner.query(`{escaped}`);
  }}

  public async down(): Promise<void> {{
    throw new Error("Downgrade nao suportado.");
  }}
}}
'''
    return DDLArtifact(
        filename="src/migrations/0001-gca-init.ts",
        content=content,
        language="typescript",
        purpose="migration",
    )


def _migration_laravel(data_model: dict[str, Any]) -> DDLArtifact:
    schema = _render_schema_sql(
        data_model["engine"], data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    escaped = schema.replace("'", "\\'")
    content = f"""<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Support\\Facades\\DB;

return new class extends Migration {{
    public function up(): void {{
        DB::unprepared('{escaped}');
    }}

    public function down(): void {{
        throw new RuntimeException('Downgrade nao suportado.');
    }}
}};
"""
    return DDLArtifact(
        filename="database/migrations/2026_04_20_000001_gca_init.php",
        content=content,
        language="php",
        purpose="migration",
    )


def _migration_efcore(data_model: dict[str, Any]) -> DDLArtifact:
    schema = _render_schema_sql(
        data_model["engine"], data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    escaped = schema.replace('"', '\\"')
    content = f'''using Microsoft.EntityFrameworkCore.Migrations;

namespace GcaApp.Migrations {{
  public partial class GcaInit : Migration {{
    protected override void Up(MigrationBuilder migrationBuilder) {{
      migrationBuilder.Sql(@"{escaped}");
    }}

    protected override void Down(MigrationBuilder migrationBuilder) {{
      throw new System.NotSupportedException("Downgrade nao suportado.");
    }}
  }}
}}
'''
    return DDLArtifact(
        filename="Migrations/20260420000001_GcaInit.cs",
        content=content,
        language="csharp",
        purpose="migration",
    )


def _migration_go_migrate(data_model: dict[str, Any], engine: str) -> DDLArtifact:
    content = _render_schema_sql(
        engine, data_model.get("tables") or [], data_model.get("foreign_keys") or [],
    )
    return DDLArtifact(
        filename="db/migrations/000001_gca_init.up.sql",
        content=content,
        language="sql",
        purpose="migration",
    )
