-- Migration 021 — Backup automatizado por projeto.
-- DT (nova): backups com retenção de 10 últimos por projeto, scheduler
-- diário às 12:00, rollback Admin OU GP.
--
-- Tabela project_backups: 1 linha por backup gerado.
--   - status: running, completed, failed
--   - trigger_source: scheduled (cron 12:00), manual_gp (GP do projeto),
--     manual_admin (Admin clicou), startup_catchup (recuperação após
--     servidor down)
--   - file_path: caminho RELATIVO ao volume gca-backups (sem leading /)
--   - manifest_json: lista de tabelas + contagens + sha256 por tabela
--
-- Coluna projects.last_backup_at: cache para UI evitar JOIN/aggregate
-- na lista de projetos.

CREATE TABLE IF NOT EXISTS project_backups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    trigger_source  VARCHAR(40) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',
    file_path       VARCHAR(500),
    size_bytes      BIGINT NOT NULL DEFAULT 0,
    sha256          VARCHAR(64),
    manifest_json   TEXT,
    error_message   TEXT,
    -- Quando este backup foi usado pra restaurar o projeto, registrar
    -- pra audit ("rollback realizado a partir deste backup").
    restored_at     TIMESTAMPTZ,
    restored_by     UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_project_backups_project ON project_backups(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_backups_status ON project_backups(status) WHERE status = 'running';

-- Cache pra UI: timestamp do último backup completo do projeto.
-- Atualizado pelo service ao fim de cada backup com sucesso.
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS last_backup_at TIMESTAMPTZ;
