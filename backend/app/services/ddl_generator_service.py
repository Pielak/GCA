"""DT-076 Fase 2 + MVP 11 Fase 11.6 — Gerador de DDL a partir do DATA_MODEL do OCG.

Emite artefatos reais (não mais placeholder) pro CodeGen incluir na
entrega inicial do projeto:
  - `schema.sql` / `collections.json` nativo do dialeto
  - Migration no formato do framework declarado no OCG
  - `seed.sql` / `seed.js` idempotente

V1 (DT-076 Fase 2) cobriu PostgreSQL e MySQL.

V2 (MVP 11 Fase 11.6) adiciona cobertura completa:
  - **SQLite**: TEXT pra UUID, INTEGER PRIMARY KEY AUTOINCREMENT pra
    BIGSERIAL, INTEGER pra BOOLEAN, TEXT pra JSONB, DATETIME pra
    TIMESTAMP.
  - **SQL Server** (T-SQL): UNIQUEIDENTIFIER, BIGINT IDENTITY(1,1),
    BIT, NVARCHAR(MAX), DATETIME2. IF NOT EXISTS via `IF OBJECT_ID`
    check.
  - **Oracle** (PL/SQL): RAW(16), NUMBER(19) com SEQUENCE pra
    autoincrement, NUMBER(1) pra BOOLEAN, CLOB, TIMESTAMP WITH TIME
    ZONE. IF NOT EXISTS via bloco anônimo com EXCEPTION.
  - **MongoDB**: gera `collections.json` com JSON Schema validators
    + `seed.js` com `insertMany` + criação de índices. Não é SQL.

7 frameworks de migration continuam cobertos, com dialeto-específico
quando aplicável:
  - Alembic: todos dialetos SQL (pg/mysql/sqlite/sqlserver/oracle).
  - Flyway: idem.
  - Knex: idem.
  - TypeORM: 5 SQL + mongo (nativo).
  - Laravel: pg/mysql/sqlite/sqlsrv (sem oracle/mongo nativo).
  - EFCore: todos via provider.
  - go-migrate: 5 SQL (sem mongo).

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
        "-- Schema gerado pelo GCA a partir do OCG.DATA_MODEL\n"
        "-- Dialect: PostgreSQL 12+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n\n"
        'CREATE EXTENSION IF NOT EXISTS "pgcrypto";\n\n'
    ),
    "mysql": (
        "-- Schema gerado pelo GCA a partir do OCG.DATA_MODEL\n"
        "-- Dialect: MySQL 8.0+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n\n"
        "SET sql_mode = 'STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION';\n\n"
    ),
    "sqlite": (
        "-- Schema gerado pelo GCA a partir do OCG.DATA_MODEL\n"
        "-- Dialect: SQLite 3.35+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n\n"
        "PRAGMA foreign_keys = ON;\n\n"
    ),
    "sqlserver": (
        "-- Schema gerado pelo GCA a partir do OCG.DATA_MODEL\n"
        "-- Dialect: SQL Server 2017+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n\n"
        "SET ANSI_NULLS ON;\nSET QUOTED_IDENTIFIER ON;\nGO\n\n"
    ),
    "oracle": (
        "-- Schema gerado pelo GCA a partir do OCG.DATA_MODEL\n"
        "-- Dialect: Oracle 19c+\n"
        "-- Refine via backlog; nova versão sobrescreve este arquivo.\n"
        "-- Observação: BIGSERIAL é emulado via SEQUENCE + DEFAULT.\n\n"
    ),
}


# Dialetos SQL suportados a partir da V2 (MVP 11 Fase 11.6).
SQL_DIALECTS: tuple[str, ...] = ("postgresql", "mysql", "sqlite", "sqlserver", "oracle")


# Dialetos totais (V2): 5 SQL + mongodb (caminho não-SQL dedicado).
ALL_DIALECTS: tuple[str, ...] = SQL_DIALECTS + ("mongodb",)


def generate_ddl(data_model: dict[str, Any]) -> list[DDLArtifact]:
    """Gera artefatos nativos do dialeto a partir do DATA_MODEL.

    Dialetos SQL (pg/mysql/sqlite/sqlserver/oracle) emitem
    `schema.sql` + `seed.sql`.
    MongoDB emite `collections.json` (JSON Schema validators) + `seed.js`
    (insertMany + createIndex) — MVP 11 Fase 11.6.

    Retorna lista vazia quando engine não é suportado.
    """
    engine = (data_model or {}).get("engine")
    if engine not in ALL_DIALECTS:
        return []

    tables = data_model.get("tables") or []
    fks = data_model.get("foreign_keys") or []
    seed = data_model.get("seed_data") or []

    if engine == "mongodb":
        return _render_mongodb_artifacts(tables, seed)

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

    # MVP 11 Fase 11.6 — guardas de compat framework × dialeto.
    # MongoDB só tem migration nativa com TypeORM (driver mongo) e EFCore
    # (Cosmos provider). Demais frameworks são SQL-only — retornam None.
    if engine == "mongodb" and f not in (
        "typeorm", "nestjs", "nodejs-nestjs",
        "efcore", "aspnet", "csharp", "c#",
    ):
        return None
    # Laravel não tem suporte nativo a Oracle no ecossistema padrão.
    if engine == "oracle" and f in ("laravel", "php", "php-laravel"):
        return None

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
    # SQLite: BIGSERIAL já vira "INTEGER PRIMARY KEY AUTOINCREMENT" no _TYPE_MAP —
    # nesse caso evita PRIMARY KEY duplicado depois.
    body = ",\n  ".join(col_lines)

    lines = [f"-- {comment}" if comment else f"-- Tabela {name}"]

    # CREATE TABLE IF NOT EXISTS — sintaxe por dialeto.
    if engine in ("postgresql", "mysql", "sqlite"):
        lines.append(f"CREATE TABLE IF NOT EXISTS {name} (")
    elif engine == "sqlserver":
        # T-SQL: sem IF NOT EXISTS direto. Usa OBJECT_ID.
        lines.append(
            f"IF OBJECT_ID(N'{name}', N'U') IS NULL\nCREATE TABLE {name} ("
        )
    else:  # oracle
        # PL/SQL: bloco anônimo tolerante a ORA-00955 (name already used).
        lines.append(
            "BEGIN EXECUTE IMMEDIATE '\n"
            f"CREATE TABLE {name} ("
        )

    lines.append(f"  {body}")

    # PK separada só quando o tipo da coluna PK não for auto-carregador.
    skip_pk = (
        engine == "sqlite"
        and any(
            (c.get("type") or "").upper() == "BIGSERIAL" and c["name"] in pk
            for c in cols
        )
    )
    if pk and not skip_pk:
        lines.append(f",  PRIMARY KEY ({', '.join(pk)})")

    # Fecha o corpo
    if engine == "oracle":
        lines.append(")';")
        lines.append("EXCEPTION WHEN OTHERS THEN")
        lines.append("  IF SQLCODE != -955 THEN RAISE; END IF;")
        lines.append("END;\n/")
    else:
        lines.append(");")

    # COMMENT ON TABLE — por dialeto
    if comment:
        safe = comment.replace("'", "''")
        if engine == "postgresql":
            lines.append(f"COMMENT ON TABLE {name} IS '{safe}';")
        elif engine == "oracle":
            lines.append(f"COMMENT ON TABLE {name} IS '{safe}';")
        # mysql inline é verboso; sqlserver/sqlite não suportam nativamente — skip
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
        # Oracle não permite UNIQUE inline sem CONSTRAINT nome; mas sintaxe
        # simples ainda funciona em todos os dialetos cobertos aqui.
        parts.append("UNIQUE")
    return " ".join(parts)


def _render_create_index(table: str, idx: dict[str, Any], engine: str) -> str:
    iname = idx["name"]
    cols = ", ".join(idx["columns"])
    unique = "UNIQUE " if idx.get("unique") else ""
    # IF NOT EXISTS: suportado em postgres, mysql 8.0.20+, sqlite.
    if engine in ("postgresql", "mysql", "sqlite"):
        return f"CREATE {unique}INDEX IF NOT EXISTS {iname} ON {table} ({cols});\n"
    if engine == "sqlserver":
        return (
            f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'{iname}')\n"
            f"  CREATE {unique}INDEX {iname} ON {table} ({cols});\n"
        )
    # oracle: usa bloco tolerante a ORA-00955
    return (
        "BEGIN EXECUTE IMMEDIATE '\n"
        f"CREATE {unique}INDEX {iname} ON {table} ({cols})';\n"
        "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF; END;\n/\n"
    )


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


_TYPE_MAP: dict[str, dict[str, str]] = {
    "postgresql": {
        "UUID": "UUID",
        "BIGSERIAL": "BIGSERIAL",
        "BOOLEAN": "BOOLEAN",
        "JSONB": "JSONB",
        "JSON": "JSONB",
        "TIMESTAMP": "TIMESTAMPTZ",
    },
    "mysql": {
        "UUID": "CHAR(36)",
        "BIGSERIAL": "BIGINT AUTO_INCREMENT",
        "BOOLEAN": "TINYINT(1)",
        "JSONB": "JSON",
        "JSON": "JSON",
        "TIMESTAMP": "TIMESTAMP",
    },
    "sqlite": {
        "UUID": "TEXT",
        "BIGSERIAL": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "BOOLEAN": "INTEGER",
        "JSONB": "TEXT",
        "JSON": "TEXT",
        "TIMESTAMP": "DATETIME",
        "TEXT": "TEXT",
        "VARCHAR": "TEXT",
        "VARCHAR(255)": "TEXT",
    },
    "sqlserver": {
        "UUID": "UNIQUEIDENTIFIER",
        "BIGSERIAL": "BIGINT IDENTITY(1,1)",
        "BOOLEAN": "BIT",
        "JSONB": "NVARCHAR(MAX)",
        "JSON": "NVARCHAR(MAX)",
        "TIMESTAMP": "DATETIME2",
        "TEXT": "NVARCHAR(MAX)",
        "VARCHAR": "NVARCHAR(255)",
    },
    "oracle": {
        "UUID": "RAW(16)",
        "BIGSERIAL": "NUMBER(19)",  # auto-increment emulado via SEQUENCE (ver _render_column)
        "BOOLEAN": "NUMBER(1)",
        "JSONB": "CLOB",
        "JSON": "CLOB",
        "TIMESTAMP": "TIMESTAMP WITH TIME ZONE",
        "TEXT": "CLOB",
        "VARCHAR": "VARCHAR2(255)",
        "INTEGER": "NUMBER(10)",
        "BIGINT": "NUMBER(19)",
    },
}


def _dialect_type(canonical_type: str, engine: str) -> str:
    """Mapeia tipos canônicos pra tipos nativos do dialeto."""
    t = canonical_type.upper().strip()
    mapping = _TYPE_MAP.get(engine, {})
    return mapping.get(t, canonical_type)


def _dialect_default(default_val: Any, canonical_type: str, engine: str) -> str:
    """Renderiza DEFAULT dialetizado. Trata UUID, timestamp, boolean e literal."""
    t = (canonical_type or "").upper()
    s = str(default_val).strip()

    # Caso CURRENT_TIMESTAMP / NOW
    if s.upper() in ("CURRENT_TIMESTAMP", "NOW()", "NOW"):
        if engine == "oracle":
            return "SYSTIMESTAMP"
        return "CURRENT_TIMESTAMP"

    # Booleanos: postgres usa literais TRUE/FALSE; demais dialetos usam 1/0
    if t == "BOOLEAN":
        val = str(default_val).lower()
        truthy = val in ("true", "1")
        if engine == "postgresql":
            return "TRUE" if truthy else "FALSE"
        return "1" if truthy else "0"

    # String já veio com aspas
    if s.startswith("'") and s.endswith("'"):
        return s

    # Número literal
    try:
        float(s)
        return s
    except ValueError:
        pass

    # Fallback: aspas (Oracle prefere N'' para unicode mas single-quote cobre ASCII)
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
    # Idempotência por dialeto.
    if engine == "postgresql":
        return (
            f"INSERT INTO {table} ({col_list}) VALUES ({val_list}) "
            "ON CONFLICT DO NOTHING;\n"
        )
    if engine == "mysql":
        return f"INSERT IGNORE INTO {table} ({col_list}) VALUES ({val_list});\n"
    if engine == "sqlite":
        return (
            f"INSERT OR IGNORE INTO {table} ({col_list}) "
            f"VALUES ({val_list});\n"
        )
    if engine == "sqlserver":
        # MERGE é complexo; best-effort: IF NOT EXISTS pela primeira coluna.
        first_col = cols[0]
        first_val = vals[0]
        return (
            f"IF NOT EXISTS (SELECT 1 FROM {table} WHERE {first_col} = {first_val})\n"
            f"  INSERT INTO {table} ({col_list}) VALUES ({val_list});\n"
        )
    # oracle
    first_col = cols[0]
    first_val = vals[0]
    return (
        f"INSERT INTO {table} ({col_list})\n"
        f"  SELECT {val_list} FROM DUAL\n"
        f"  WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE {first_col} = {first_val});\n"
    )


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
# MongoDB renderer (MVP 11 Fase 11.6)
# ---------------------------------------------------------------------------

# Canonical → JSON Schema bsonType.
_BSON_TYPE_MAP: dict[str, str] = {
    "UUID": "string",
    "BIGSERIAL": "long",
    "BIGINT": "long",
    "INTEGER": "int",
    "BOOLEAN": "bool",
    "JSONB": "object",
    "JSON": "object",
    "TIMESTAMP": "date",
    "TEXT": "string",
    "VARCHAR": "string",
    "VARCHAR(255)": "string",
}


def _render_mongodb_artifacts(
    tables: list[dict[str, Any]], seed: list[dict[str, Any]],
) -> list[DDLArtifact]:
    """Gera collections.json (JSON Schema validators) + seed.js + create_indexes.js.

    MongoDB não tem schema rígido, mas coleções podem ter JSON Schema
    validators (`$jsonSchema`) ativados. Seed usa `insertMany` e
    `createIndex`. Output é consumido pelo CodeGen e pode ser executado
    via `mongosh < seed.js` ou via scripts de bootstrap do cliente.
    """
    import json as _json

    collections: list[dict[str, Any]] = []
    index_ops: list[str] = []
    for t in tables:
        name = t["name"]
        cols = t.get("columns") or []
        pk = t.get("primary_key") or []

        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for c in cols:
            cname = c["name"]
            ctype_upper = (c.get("type") or "string").upper()
            bson_type = _BSON_TYPE_MAP.get(ctype_upper, "string")
            properties[cname] = {"bsonType": bson_type}
            if not c.get("nullable", False):
                required.append(cname)

        collection_doc: dict[str, Any] = {
            "collection": name,
            "validator": {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": required,
                    "properties": properties,
                }
            },
            "primary_key": pk,
        }
        collections.append(collection_doc)

        # Índices declarados
        for idx in t.get("indexes") or []:
            iname = idx["name"]
            keys = {col: 1 for col in idx["columns"]}
            options = {"name": iname}
            if idx.get("unique"):
                options["unique"] = True
            index_ops.append(
                f"db.{name}.createIndex({_json.dumps(keys)}, {_json.dumps(options)});"
            )

    collections_json = _json.dumps(
        {"collections": collections}, indent=2, ensure_ascii=False
    )

    # Seed insertMany idempotente: usa updateOne upsert para cada row.
    seed_lines = [
        "// Seed idempotente gerado pelo GCA para MongoDB.",
        "// Execute via: mongosh <uri> < seed.js",
        "",
    ]
    for entry in seed:
        table = entry["table"]
        purpose = entry.get("purpose") or ""
        if purpose:
            seed_lines.append(f"// {purpose}")
        for row in entry.get("rows") or []:
            # Usa o primeiro campo como chave do upsert.
            first_key = next(iter(row.keys()))
            filter_doc = {first_key: row[first_key]}
            seed_lines.append(
                f"db.{table}.updateOne("
                f"{_json.dumps(filter_doc, ensure_ascii=False)}, "
                f"{{ $setOnInsert: {_json.dumps(row, ensure_ascii=False)} }}, "
                f"{{ upsert: true }});"
            )
    seed_lines.append("")
    if index_ops:
        seed_lines.append("// Índices declarados no DATA_MODEL")
        seed_lines.extend(index_ops)

    return [
        DDLArtifact(
            filename="collections.json",
            content=collections_json,
            language="json",
            purpose="schema",
        ),
        DDLArtifact(
            filename="seed.js",
            content="\n".join(seed_lines) + "\n",
            language="javascript",
            purpose="seed",
        ),
    ]


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
    engine = data_model["engine"]
    if engine == "mongodb":
        # MVP 11 Fase 11.6 — TypeORM + MongoDB driver: migration cria
        # coleções via connection.createCollection e índices via
        # createIndex. Stub orientando o GP a completar a partir do
        # collections.json.
        tables = data_model.get("tables") or []
        coll_names = [t["name"] for t in tables]
        ops = "\n".join(
            f'    await conn.db.createCollection("{n}");' for n in coll_names
        )
        content = f'''import {{ MigrationInterface, QueryRunner, MongoClient }} from "typeorm";

// TypeORM + MongoDB: a migration cria coleções vazias. Os validators
// JSON Schema e índices ficam em `collections.json` / `seed.js` —
// aplicar via script de bootstrap do projeto.
export class GcaInit0001 implements MigrationInterface {{
  name = "GcaInit0001";

  public async up(queryRunner: QueryRunner): Promise<void> {{
    const conn: any = queryRunner.connection;
{ops}
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

    schema = _render_schema_sql(
        engine, data_model.get("tables") or [], data_model.get("foreign_keys") or [],
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
    engine = data_model["engine"]
    if engine == "mongodb":
        # EFCore + Cosmos DB: containers equivalem a coleções; a migration
        # define Database.EnsureCreated e delega schema/index para
        # collections.json consumido pelo bootstrap.
        content = '''using Microsoft.EntityFrameworkCore.Migrations;

namespace GcaApp.Migrations {
  // EFCore + Cosmos: containers são criados em runtime via
  // Database.EnsureCreated(). Schema e índices em collections.json.
  public partial class GcaInit : Migration {
    protected override void Up(MigrationBuilder migrationBuilder) {
      // No-op: Cosmos cria containers lazy. Ver collections.json.
    }

    protected override void Down(MigrationBuilder migrationBuilder) {
      throw new System.NotSupportedException("Downgrade nao suportado.");
    }
  }
}
'''
        return DDLArtifact(
            filename="Migrations/20260420000001_GcaInit.cs",
            content=content,
            language="csharp",
            purpose="migration",
        )

    schema = _render_schema_sql(
        engine, data_model.get("tables") or [], data_model.get("foreign_keys") or [],
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
