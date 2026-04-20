"""DT-076 Fase 1 — Inferência determinística do DATA_MODEL a partir do OCG.

Produz o bloco `DATA_MODEL` do OCG com tabelas mínimas derivadas de:
  - `STACK_RECOMMENDATION.database.engine` (motor escolhido pelo GP)
  - `PROJECT_PROFILE.initiative_type` (tipo de iniciativa)
  - `PROJECT_PROFILE.handles_pii` (se verdadeiro, inclui audit + consent)
  - `security_controls` e `compliance_checklist` quando presentes

A inferência é **determinística** (sem LLM) por design:
  - Baixa criticidade (contrato §6.2): é estrutura comum e previsível
  - Gera resultado idêntico pra mesmo input — facilita dogfood + testes
  - Pode ser enriquecida por ingestão depois (OCG delta) — é ponto de partida
  - Dá ao GP controle explícito: refina via backlog, sempre conhece o default

Saída: dict JSON-serializável pronto pra gravar em `OCG.DATA_MODEL`.
"""
from __future__ import annotations

from typing import Any


# Engines aceitos na geração de DDL (DT-076 Fase 2 — começa com PG + MySQL).
# Outros dialetos ficam em 'unsupported_engine' e o CodeGen emite placeholder.
SUPPORTED_ENGINES = ("postgresql", "mysql")

# Tamanho default para colunas string. Configurável por tabela quando faz
# sentido (email 320, password_hash 255, tokens 128).
DEFAULT_STRING_LEN = 255


def infer_data_model(
    project_profile: dict[str, Any] | None,
    stack_recommendation: dict[str, Any] | None,
    *,
    security_controls: list[str] | None = None,
) -> dict[str, Any]:
    """Gera bloco DATA_MODEL do OCG a partir do profile + stack.

    Retorna sempre um dict válido — quando não é possível inferir, retorna
    estrutura mínima com `tables=[]` e um warning explicando o motivo.
    """
    profile = project_profile or {}
    stack = stack_recommendation or {}
    controls = set((c or "").lower() for c in (security_controls or []))

    database = stack.get("database") or {}
    engine_raw = (database.get("engine") or "").strip()
    engine = _normalize_engine(engine_raw)
    warnings: list[str] = []

    if not engine_raw:
        warnings.append(
            "PROJECT sem database engine escolhido no questionário. "
            "Modelo de dados não gerado. Defina Q31 (primary_database) pra habilitar."
        )
        return {
            "engine": None,
            "engine_raw": engine_raw,
            "dialect_supported": False,
            "tables": [],
            "foreign_keys": [],
            "seed_data": [],
            "warnings": warnings,
            "inference_rationale": [],
        }

    if engine not in SUPPORTED_ENGINES:
        warnings.append(
            f"Engine '{engine_raw}' não suportado pela geração automática "
            f"(MVP V1 cobre {SUPPORTED_ENGINES}). Schema precisa ser escrito "
            f"manualmente até suporte ao dialeto."
        )

    initiative = (profile.get("initiative_type") or "").strip().lower()
    handles_pii = bool(profile.get("handles_pii"))
    criticality = (profile.get("criticality_level") or "").strip().lower()

    rationale: list[str] = []
    tables: list[dict[str, Any]] = []
    foreign_keys: list[dict[str, Any]] = []
    seed_data: list[dict[str, Any]] = []

    # --- Núcleo comum a todo sistema: users + sessions ---
    tables.append(_table_users(engine))
    tables.append(_table_sessions(engine))
    foreign_keys.append({
        "from_table": "sessions",
        "from_columns": ["user_id"],
        "to_table": "users",
        "to_columns": ["id"],
        "on_delete": "CASCADE",
    })
    rationale.append(
        "Tabelas users e sessions são núcleo comum — toda aplicação com "
        "autenticação precisa. Incluídas por padrão."
    )

    # --- Audit log quando há controles de compliance/auditoria ---
    if handles_pii or "auditoria" in controls or "audit" in controls or "lgpd" in controls:
        tables.append(_table_audit_log(engine))
        foreign_keys.append({
            "from_table": "audit_log",
            "from_columns": ["user_id"],
            "to_table": "users",
            "to_columns": ["id"],
            "on_delete": "SET NULL",
        })
        rationale.append(
            "audit_log incluída por handles_pii=true ou controles de "
            "auditoria/LGPD declarados. Rastreio de quem fez o quê é "
            "mandatório pra compliance."
        )

    # --- Tabela de consentimento LGPD quando handles_pii ---
    if handles_pii:
        tables.append(_table_consent(engine))
        foreign_keys.append({
            "from_table": "consent",
            "from_columns": ["user_id"],
            "to_table": "users",
            "to_columns": ["id"],
            "on_delete": "CASCADE",
        })
        rationale.append(
            "consent incluída por handles_pii=true. LGPD art. 8 exige "
            "registro explícito de consentimento do titular."
        )

    # --- Configurações do sistema (sempre) ---
    tables.append(_table_config(engine))
    rationale.append(
        "config como tabela chave-valor genérica pra feature flags e "
        "parâmetros operacionais por instância."
    )

    # --- Tabelas por initiative_type ---
    domain_tables, domain_fks, domain_rationale = _tables_by_initiative(
        initiative, engine,
    )
    tables.extend(domain_tables)
    foreign_keys.extend(domain_fks)
    rationale.extend(domain_rationale)

    # --- Seed data mínimo ---
    seed_data.append({
        "table": "users",
        "purpose": "Usuário admin inicial. Senha deve ser trocada no primeiro login.",
        "rows": [{
            "email": "admin@localhost",
            "password_hash": "__REPLACE_ON_BOOT__",
            "full_name": "Administrador",
            "is_active": True,
            "is_admin": True,
        }],
    })
    seed_data.append({
        "table": "config",
        "purpose": "Configurações default do sistema.",
        "rows": [
            {"key": "app_name", "value": "TBD", "description": "Nome da aplicação"},
            {"key": "session_timeout_minutes", "value": "60", "description": "Timeout de sessão"},
        ],
    })

    return {
        "engine": engine,
        "engine_raw": engine_raw,
        "dialect_supported": engine in SUPPORTED_ENGINES,
        "tables": tables,
        "foreign_keys": foreign_keys,
        "seed_data": seed_data,
        "warnings": warnings,
        "inference_rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Tabelas comuns
# ---------------------------------------------------------------------------

def _col(name: str, ctype: str, *, nullable: bool = False, default=None,
         unique: bool = False, comment: str | None = None) -> dict[str, Any]:
    c: dict[str, Any] = {"name": name, "type": ctype, "nullable": nullable}
    if default is not None:
        c["default"] = default
    if unique:
        c["unique"] = True
    if comment:
        c["comment"] = comment
    return c


def _table_users(engine: str) -> dict[str, Any]:
    return {
        "name": "users",
        "comment": "Usuários da aplicação. Senha armazenada com bcrypt.",
        "columns": [
            _col("id", "UUID", comment="Identificador único"),
            _col("email", "VARCHAR(320)", unique=True, comment="Login do usuário"),
            _col("password_hash", "VARCHAR(255)", comment="bcrypt hash"),
            _col("full_name", "VARCHAR(255)"),
            _col("is_active", "BOOLEAN", default=True),
            _col("is_admin", "BOOLEAN", default=False),
            _col("created_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
            _col("updated_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
        ],
        "primary_key": ["id"],
        "indexes": [
            {"name": "idx_users_email", "columns": ["email"], "unique": True},
            {"name": "idx_users_active", "columns": ["is_active"]},
        ],
    }


def _table_sessions(engine: str) -> dict[str, Any]:
    return {
        "name": "sessions",
        "comment": "Sessões ativas. Rotação de token em cada login.",
        "columns": [
            _col("id", "UUID"),
            _col("user_id", "UUID"),
            _col("token_hash", "VARCHAR(128)", unique=True),
            _col("ip_address", "VARCHAR(45)", nullable=True),
            _col("user_agent", "VARCHAR(255)", nullable=True),
            _col("expires_at", "TIMESTAMP"),
            _col("created_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
        ],
        "primary_key": ["id"],
        "indexes": [
            {"name": "idx_sessions_user", "columns": ["user_id"]},
            {"name": "idx_sessions_expires", "columns": ["expires_at"]},
        ],
    }


def _table_audit_log(engine: str) -> dict[str, Any]:
    json_type = "JSONB" if engine == "postgresql" else "JSON"
    return {
        "name": "audit_log",
        "comment": "Trilha de auditoria imutável. Append-only.",
        "columns": [
            _col("id", "BIGSERIAL" if engine == "postgresql" else "BIGINT"),
            _col("user_id", "UUID", nullable=True,
                 comment="Pode ser NULL se ação foi sistêmica"),
            _col("action", "VARCHAR(100)", comment="create, update, delete, login, etc."),
            _col("entity", "VARCHAR(100)", comment="Nome da entidade afetada"),
            _col("entity_id", "VARCHAR(100)", nullable=True),
            _col("metadata", json_type, nullable=True,
                 comment="Dados adicionais (diff, contexto)"),
            _col("ip_address", "VARCHAR(45)", nullable=True),
            _col("created_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
        ],
        "primary_key": ["id"],
        "indexes": [
            {"name": "idx_audit_user", "columns": ["user_id"]},
            {"name": "idx_audit_entity", "columns": ["entity", "entity_id"]},
            {"name": "idx_audit_created", "columns": ["created_at"]},
        ],
    }


def _table_consent(engine: str) -> dict[str, Any]:
    return {
        "name": "consent",
        "comment": "Registro de consentimento LGPD. Art. 8 — titular.",
        "columns": [
            _col("id", "UUID"),
            _col("user_id", "UUID"),
            _col("purpose", "VARCHAR(255)", comment="Finalidade do tratamento"),
            _col("granted", "BOOLEAN", default=False),
            _col("granted_at", "TIMESTAMP", nullable=True),
            _col("revoked_at", "TIMESTAMP", nullable=True),
            _col("version", "VARCHAR(30)", comment="Versão da política aceita"),
        ],
        "primary_key": ["id"],
        "indexes": [
            {"name": "idx_consent_user", "columns": ["user_id"]},
            {"name": "idx_consent_purpose", "columns": ["purpose"]},
        ],
    }


def _table_config(engine: str) -> dict[str, Any]:
    return {
        "name": "config",
        "comment": "Configurações chave-valor por instância.",
        "columns": [
            _col("key", "VARCHAR(100)"),
            _col("value", "TEXT", nullable=True),
            _col("description", "VARCHAR(500)", nullable=True),
            _col("updated_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
        ],
        "primary_key": ["key"],
        "indexes": [],
    }


# ---------------------------------------------------------------------------
# Tabelas específicas do initiative_type
# ---------------------------------------------------------------------------

def _tables_by_initiative(
    initiative: str, engine: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Mapeia initiative_type pra tabelas específicas de domínio.

    Mínimo viável — GP refina via backlog depois. Objetivo é sair do zero
    com DDL que faz sentido pro tipo de projeto declarado.
    """
    i = initiative
    tables: list[dict[str, Any]] = []
    fks: list[dict[str, Any]] = []
    rationale: list[str] = []
    json_type = "JSONB" if engine == "postgresql" else "JSON"

    if any(kw in i for kw in ("e-commerce", "ecommerce", "loja", "marketplace")):
        tables.extend([
            _generic_entity("customers", engine, extra=[
                _col("phone", "VARCHAR(30)", nullable=True),
                _col("document", "VARCHAR(30)", nullable=True),
            ]),
            _generic_entity("products", engine, extra=[
                _col("sku", "VARCHAR(100)", unique=True),
                _col("price_cents", "BIGINT"),
                _col("stock", "INTEGER", default=0),
            ]),
            _generic_entity("orders", engine, extra=[
                _col("customer_id", "UUID"),
                _col("total_cents", "BIGINT"),
                _col("status", "VARCHAR(30)", default="'pending'"),
            ]),
            {
                "name": "order_items",
                "comment": "Itens de um pedido.",
                "columns": [
                    _col("id", "UUID"),
                    _col("order_id", "UUID"),
                    _col("product_id", "UUID"),
                    _col("quantity", "INTEGER"),
                    _col("unit_price_cents", "BIGINT"),
                ],
                "primary_key": ["id"],
                "indexes": [{"name": "idx_order_items_order", "columns": ["order_id"]}],
            },
        ])
        fks.extend([
            {"from_table": "orders", "from_columns": ["customer_id"],
             "to_table": "customers", "to_columns": ["id"], "on_delete": "RESTRICT"},
            {"from_table": "order_items", "from_columns": ["order_id"],
             "to_table": "orders", "to_columns": ["id"], "on_delete": "CASCADE"},
            {"from_table": "order_items", "from_columns": ["product_id"],
             "to_table": "products", "to_columns": ["id"], "on_delete": "RESTRICT"},
        ])
        rationale.append("initiative_type sugere e-commerce — adicionadas "
                         "tabelas customers, products, orders e order_items.")
        return tables, fks, rationale

    if any(kw in i for kw in ("crm", "vendas", "pipeline comercial")):
        tables.extend([
            _generic_entity("leads", engine, extra=[
                _col("email", "VARCHAR(320)"),
                _col("phone", "VARCHAR(30)", nullable=True),
                _col("stage", "VARCHAR(30)", default="'new'"),
            ]),
            _generic_entity("opportunities", engine, extra=[
                _col("lead_id", "UUID"),
                _col("amount_cents", "BIGINT"),
                _col("probability", "INTEGER", default=0),
                _col("close_date", "DATE", nullable=True),
            ]),
            _generic_entity("activities", engine, extra=[
                _col("lead_id", "UUID", nullable=True),
                _col("opportunity_id", "UUID", nullable=True),
                _col("kind", "VARCHAR(30)", comment="call, email, meeting"),
                _col("notes", "TEXT", nullable=True),
            ]),
        ])
        fks.extend([
            {"from_table": "opportunities", "from_columns": ["lead_id"],
             "to_table": "leads", "to_columns": ["id"], "on_delete": "RESTRICT"},
            {"from_table": "activities", "from_columns": ["lead_id"],
             "to_table": "leads", "to_columns": ["id"], "on_delete": "CASCADE"},
        ])
        rationale.append("initiative_type sugere CRM — adicionadas "
                         "leads, opportunities, activities.")
        return tables, fks, rationale

    if any(kw in i for kw in ("processo", "bpm", "workflow", "jurídic", "juridic")):
        tables.extend([
            _generic_entity("processes", engine, extra=[
                _col("title", "VARCHAR(255)"),
                _col("status", "VARCHAR(30)", default="'open'"),
                _col("priority", "VARCHAR(20)", default="'medium'"),
                _col("assigned_to", "UUID", nullable=True),
                _col("metadata", json_type, nullable=True),
            ]),
            _generic_entity("tasks", engine, extra=[
                _col("process_id", "UUID"),
                _col("title", "VARCHAR(255)"),
                _col("status", "VARCHAR(30)", default="'pending'"),
                _col("due_date", "DATE", nullable=True),
                _col("completed_at", "TIMESTAMP", nullable=True),
            ]),
            _generic_entity("attachments", engine, extra=[
                _col("process_id", "UUID", nullable=True),
                _col("task_id", "UUID", nullable=True),
                _col("filename", "VARCHAR(255)"),
                _col("storage_path", "VARCHAR(500)"),
                _col("size_bytes", "BIGINT"),
                _col("mime_type", "VARCHAR(100)"),
            ]),
        ])
        fks.extend([
            {"from_table": "tasks", "from_columns": ["process_id"],
             "to_table": "processes", "to_columns": ["id"], "on_delete": "CASCADE"},
            {"from_table": "processes", "from_columns": ["assigned_to"],
             "to_table": "users", "to_columns": ["id"], "on_delete": "SET NULL"},
        ])
        rationale.append("initiative_type sugere gestão de processos — "
                         "adicionadas processes, tasks, attachments.")
        return tables, fks, rationale

    if any(kw in i for kw in ("api", "portal", "integração", "integracao")):
        tables.extend([
            _generic_entity("api_keys", engine, extra=[
                _col("name", "VARCHAR(100)"),
                _col("key_hash", "VARCHAR(128)", unique=True),
                _col("owner_user_id", "UUID", nullable=True),
                _col("expires_at", "TIMESTAMP", nullable=True),
                _col("revoked_at", "TIMESTAMP", nullable=True),
            ]),
            _generic_entity("rate_limits", engine, extra=[
                _col("api_key_id", "UUID"),
                _col("window_start", "TIMESTAMP"),
                _col("request_count", "INTEGER", default=0),
                _col("limit_per_window", "INTEGER"),
            ]),
        ])
        fks.append({
            "from_table": "rate_limits", "from_columns": ["api_key_id"],
            "to_table": "api_keys", "to_columns": ["id"], "on_delete": "CASCADE",
        })
        rationale.append("initiative_type sugere API/portal — adicionadas "
                         "api_keys e rate_limits.")
        return tables, fks, rationale

    # Fallback genérico — entidade polimórfica
    tables.append({
        "name": "entities",
        "comment": "Entidade polimórfica — refinar em tabelas específicas "
                   "conforme domínio do projeto se consolida.",
        "columns": [
            _col("id", "UUID"),
            _col("kind", "VARCHAR(100)", comment="Tipo da entidade"),
            _col("title", "VARCHAR(255)"),
            _col("payload", json_type, nullable=True),
            _col("created_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
            _col("updated_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
        ],
        "primary_key": ["id"],
        "indexes": [{"name": "idx_entities_kind", "columns": ["kind"]}],
    })
    rationale.append(
        f"initiative_type '{initiative or '(não declarado)'}' não matcheou "
        "padrão conhecido — usei entidade polimórfica genérica. Refine via "
        "backlog."
    )
    return tables, [], rationale


def _generic_entity(
    name: str, engine: str, *, extra: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Template de entidade de domínio: id + timestamps + colunas extras."""
    base = [
        _col("id", "UUID"),
        _col("created_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
        _col("updated_at", "TIMESTAMP", default="CURRENT_TIMESTAMP"),
    ]
    cols = [base[0]] + (extra or []) + base[1:]
    return {
        "name": name,
        "comment": f"Entidade {name} derivada do initiative_type.",
        "columns": cols,
        "primary_key": ["id"],
        "indexes": [],
    }


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def _normalize_engine(raw: str) -> str:
    """Mapeia variações de nomenclatura pra engines canônicos.

    Q31 vem como string livre ou opção do PDF. Diferentes GPs podem escrever
    'Postgres', 'PostgreSQL', 'postgresql', 'PG'. Normaliza pra uso interno.
    """
    r = raw.strip().lower()
    if not r:
        return ""
    if any(kw in r for kw in ("postgres", "postgis", "pg ")) or r == "pg":
        return "postgresql"
    if "mysql" in r or "mariadb" in r:
        return "mysql"
    if "sqlserver" in r or "sql server" in r or "mssql" in r:
        return "sqlserver"
    if "oracle" in r:
        return "oracle"
    if "sqlite" in r:
        return "sqlite"
    if "mongo" in r:
        return "mongodb"
    return r
