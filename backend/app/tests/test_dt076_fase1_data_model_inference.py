"""DT-076 Fase 1 — Inferência do DATA_MODEL no OCG.

Cobre:
  - Núcleo comum: users + sessions sempre presentes
  - handles_pii=true → adiciona audit_log + consent
  - initiative_type 'e-commerce' → customers/products/orders/order_items
  - initiative_type 'CRM' → leads/opportunities/activities
  - initiative_type 'jurídico' → processes/tasks/attachments
  - initiative_type 'API' → api_keys/rate_limits
  - initiative_type desconhecido → fallback entities
  - Engine não suportado → warning + dialect_supported=false
  - Sem engine → tables vazio + warning específico
  - Normalização de engine (Postgres, PG, postgresql → postgresql)
  - FKs referenciam tabelas que existem
  - Seed data inclui admin inicial
"""
from __future__ import annotations

import pytest

from app.services.data_model_inference import (
    SUPPORTED_ENGINES, _normalize_engine, infer_data_model,
)


# ────────────────────────────────────────────────────────────────────────
# Núcleo comum
# ────────────────────────────────────────────────────────────────────────

def test_nucleo_inclui_users_e_sessions():
    dm = infer_data_model(
        project_profile={"initiative_type": "qualquer"},
        stack_recommendation={"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "users" in names
    assert "sessions" in names


def test_nucleo_sempre_tem_config():
    dm = infer_data_model(
        project_profile={}, stack_recommendation={"database": {"engine": "MySQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "config" in names


def test_users_tem_email_unique():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "PostgreSQL"}},
    )
    users = next(t for t in dm["tables"] if t["name"] == "users")
    email_col = next(c for c in users["columns"] if c["name"] == "email")
    assert email_col.get("unique") is True


# ────────────────────────────────────────────────────────────────────────
# LGPD/PII
# ────────────────────────────────────────────────────────────────────────

def test_handles_pii_adiciona_audit_log_e_consent():
    dm = infer_data_model(
        {"initiative_type": "generic", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "audit_log" in names
    assert "consent" in names


def test_sem_pii_nem_audit():
    dm = infer_data_model(
        {"initiative_type": "generic", "handles_pii": False},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "audit_log" not in names
    assert "consent" not in names


def test_security_controls_auditoria_tambem_adiciona_audit():
    """Sem handles_pii mas com controle 'auditoria' → ainda inclui audit_log."""
    dm = infer_data_model(
        {"initiative_type": "generic", "handles_pii": False},
        {"database": {"engine": "PostgreSQL"}},
        security_controls=["Auditoria", "HTTPS"],
    )
    names = [t["name"] for t in dm["tables"]]
    assert "audit_log" in names
    # consent só entra com PII
    assert "consent" not in names


# ────────────────────────────────────────────────────────────────────────
# initiative_type → tabelas de domínio
# ────────────────────────────────────────────────────────────────────────

def test_ecommerce_gera_customers_products_orders():
    dm = infer_data_model(
        {"initiative_type": "E-commerce B2C"},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    for expected in ("customers", "products", "orders", "order_items"):
        assert expected in names, f"{expected} ausente em e-commerce"


def test_crm_gera_leads_opportunities():
    dm = infer_data_model(
        {"initiative_type": "CRM interno"},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "leads" in names
    assert "opportunities" in names
    assert "activities" in names


def test_juridico_gera_processes_tasks():
    dm = infer_data_model(
        {"initiative_type": "Automação jurídica"},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "processes" in names
    assert "tasks" in names
    assert "attachments" in names


def test_api_gera_api_keys_rate_limits():
    dm = infer_data_model(
        {"initiative_type": "API pública de integração"},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "api_keys" in names
    assert "rate_limits" in names


def test_desconhecido_cai_em_entities_fallback():
    dm = infer_data_model(
        {"initiative_type": "algo completamente novo e único"},
        {"database": {"engine": "PostgreSQL"}},
    )
    names = [t["name"] for t in dm["tables"]]
    assert "entities" in names
    # Não deve pegar tabelas de domínio específicas
    assert "products" not in names
    assert "leads" not in names


# ────────────────────────────────────────────────────────────────────────
# Engine support
# ────────────────────────────────────────────────────────────────────────

def test_engine_postgresql_suportado():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "PostgreSQL"}},
    )
    assert dm["engine"] == "postgresql"
    assert dm["dialect_supported"] is True
    assert dm["warnings"] == []


def test_engine_mysql_suportado():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "MySQL"}},
    )
    assert dm["engine"] == "mysql"
    assert dm["dialect_supported"] is True


def test_engine_oracle_nao_suportado_gera_warning():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "Oracle 19c"}},
    )
    assert dm["engine"] == "oracle"
    assert dm["dialect_supported"] is False
    assert len(dm["warnings"]) >= 1
    assert any("Oracle" in w for w in dm["warnings"])


def test_sem_engine_retorna_estrutura_vazia():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {}},
    )
    assert dm["engine"] is None
    assert dm["tables"] == []
    assert dm["dialect_supported"] is False
    assert any("Q31" in w for w in dm["warnings"])


def test_stack_none_nao_quebra():
    dm = infer_data_model(None, None)
    assert dm["tables"] == []
    assert dm["warnings"]


# ────────────────────────────────────────────────────────────────────────
# Normalização de engine
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("PostgreSQL", "postgresql"),
    ("Postgres", "postgresql"),
    ("postgres 15", "postgresql"),
    ("PG", "postgresql"),
    ("MySQL 8", "mysql"),
    ("MariaDB", "mysql"),
    ("SQL Server 2022", "sqlserver"),
    ("Oracle", "oracle"),
    ("SQLite", "sqlite"),
    ("MongoDB", "mongodb"),
    ("", ""),
])
def test_normalize_engine(raw, expected):
    assert _normalize_engine(raw) == expected


# ────────────────────────────────────────────────────────────────────────
# FKs são consistentes
# ────────────────────────────────────────────────────────────────────────

def test_fks_referenciam_tabelas_existentes():
    dm = infer_data_model(
        {"initiative_type": "E-commerce", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )
    table_names = {t["name"] for t in dm["tables"]}
    for fk in dm["foreign_keys"]:
        assert fk["from_table"] in table_names, (
            f"FK from_table '{fk['from_table']}' não existe")
        assert fk["to_table"] in table_names, (
            f"FK to_table '{fk['to_table']}' não existe")


def test_sessions_fk_cascade_para_users():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "PostgreSQL"}},
    )
    session_fk = next(
        fk for fk in dm["foreign_keys"]
        if fk["from_table"] == "sessions"
    )
    assert session_fk["to_table"] == "users"
    assert session_fk["on_delete"] == "CASCADE"


# ────────────────────────────────────────────────────────────────────────
# Seed data
# ────────────────────────────────────────────────────────────────────────

def test_seed_inclui_admin_inicial():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "PostgreSQL"}},
    )
    seed = dm["seed_data"]
    users_seed = next(s for s in seed if s["table"] == "users")
    assert users_seed["rows"][0]["is_admin"] is True
    assert users_seed["rows"][0]["password_hash"] == "__REPLACE_ON_BOOT__"


def test_seed_inclui_config_defaults():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "PostgreSQL"}},
    )
    seed = dm["seed_data"]
    config_seed = next(s for s in seed if s["table"] == "config")
    keys = [r["key"] for r in config_seed["rows"]]
    assert "app_name" in keys
    assert "session_timeout_minutes" in keys


# ────────────────────────────────────────────────────────────────────────
# Tipo JSON dialetizado
# ────────────────────────────────────────────────────────────────────────

def test_audit_log_usa_jsonb_em_postgres():
    dm = infer_data_model(
        {"initiative_type": "generic", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )
    audit = next(t for t in dm["tables"] if t["name"] == "audit_log")
    metadata_col = next(c for c in audit["columns"] if c["name"] == "metadata")
    assert metadata_col["type"] == "JSONB"


def test_audit_log_usa_json_em_mysql():
    dm = infer_data_model(
        {"initiative_type": "generic", "handles_pii": True},
        {"database": {"engine": "MySQL"}},
    )
    audit = next(t for t in dm["tables"] if t["name"] == "audit_log")
    metadata_col = next(c for c in audit["columns"] if c["name"] == "metadata")
    assert metadata_col["type"] == "JSON"


# ────────────────────────────────────────────────────────────────────────
# Rationale explicável
# ────────────────────────────────────────────────────────────────────────

def test_rationale_presente_e_nao_vazio():
    dm = infer_data_model(
        {"initiative_type": "E-commerce", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )
    assert len(dm["inference_rationale"]) > 0


# ────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────

def test_supported_engines_v1():
    assert set(SUPPORTED_ENGINES) == {"postgresql", "mysql"}
