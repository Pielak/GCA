-- MVP 7 — Entrega versionada preservando dados do usuário
-- Contrato §7 MVP 7.
--
-- Modelo: cada release é declarada em backend/releases/<tag>.yaml
-- (shipada com o código). Ao startup, release_service detecta novas
-- e aplica as não-destrutivas automaticamente; destrutivas ficam
-- status='pending' aguardando ação explícita de Admin.

BEGIN;

-- Release aplicada (ou pendente) na instância.
CREATE TABLE IF NOT EXISTS releases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tag VARCHAR(40) NOT NULL UNIQUE,          -- ex: "v0.8.0"
    title VARCHAR(200) NOT NULL,
    body TEXT,
    is_destructive BOOLEAN NOT NULL DEFAULT FALSE,
    -- status: pending | applied | rolled_back
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'rolled_back')),
    declared_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    applied_by UUID REFERENCES users(id) ON DELETE SET NULL,
    git_commit_hash VARCHAR(64),
    -- source_yaml: nome do arquivo YAML shipado (auditoria)
    source_yaml VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_releases_status_declared
    ON releases (status, declared_at DESC);

-- Itens de changelog dentro da release.
-- kind: mvp, mvp_emenda, ticket, feature, fix, schema_change
-- affected_roles: lista JSON ['admin', 'gp', 'dev', 'tester', 'qa', 'all']
CREATE TABLE IF NOT EXISTS release_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id UUID NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    kind VARCHAR(40) NOT NULL,
    ref_id VARCHAR(60),         -- ex: "MVP6-E", "DT-063", ticket UUID
    title VARCHAR(300) NOT NULL,
    description TEXT,
    affected_roles TEXT NOT NULL DEFAULT '["all"]',  -- JSON
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_items_release
    ON release_items (release_id, display_order);

-- Log de eventos da release (aplicação, snapshot pre-release, rollback,
-- conclusão de completion_task no futuro).
CREATE TABLE IF NOT EXISTS release_application_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id UUID NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    event_type VARCHAR(60) NOT NULL,       -- applied | snapshot_taken | rolled_back | completion_task_created | completion_task_fulfilled
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    -- metadata: JSON livre (snapshot_id, etc)
    metadata TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_release_log_release_created
    ON release_application_log (release_id, created_at ASC);

COMMIT;
