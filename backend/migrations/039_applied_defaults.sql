-- MVP M02 — decisões automáticas do domain_defaults_resolver.
-- Cada gap que o Arguidor identifica passa pelo resolver. Se o gap tem
-- default canônico em domínio público (LGPD, CC, CPC, CLT, defaults
-- técnicos usuais), grava aqui em vez de virar pergunta no M01.

CREATE TABLE applied_defaults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gap_id VARCHAR(20) NOT NULL,
    category VARCHAR(40) NOT NULL,
    decision_key VARCHAR(160) NOT NULL,
    decision_value TEXT NOT NULL,
    source_citation VARCHAR(400) NOT NULL,
    rationale TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    contested_at TIMESTAMPTZ,
    contested_by UUID REFERENCES users(id) ON DELETE SET NULL,
    contested_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, decision_key)
);

CREATE INDEX ix_applied_defaults_project_category
    ON applied_defaults (project_id, category);
CREATE INDEX ix_applied_defaults_project_contested
    ON applied_defaults (project_id, contested_at)
    WHERE contested_at IS NOT NULL;

COMMENT ON TABLE applied_defaults IS
    'M02 — decisões automáticas aplicadas ao OCG pelo domain_defaults_resolver.';
COMMENT ON COLUMN applied_defaults.category IS
    'legal|security|technical|compliance|architecture';
COMMENT ON COLUMN applied_defaults.decision_key IS
    'Chave canônica da decisão. Única por projeto — re-aplicação atualiza em vez de duplicar.';
