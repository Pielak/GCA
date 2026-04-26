-- 2026-04-25: G4 — preview de app gerado em ambiente local do owner.
-- GCA não roda docker compose do app gerado direto (gca-backend não tem
-- docker.sock montado por segurança). Estratégia híbrida: backend
-- prepara comando shell, persiste sessão e o owner roda local.
-- Tabela rastreia sessões de preview pra:
--   1. Mostrar quais previews já foram preparadas pro owner.
--   2. Permitir "stop" lógico (owner declara que parou o container).
--   3. Servir histórico/auditoria de quando o preview foi rodado.

BEGIN;

CREATE TABLE IF NOT EXISTS app_preview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scaffold_run_id UUID REFERENCES scaffold_runs(id) ON DELETE SET NULL,
    port INTEGER,                            -- porta sugerida (range 9100-9999)
    status VARCHAR(20) NOT NULL DEFAULT 'prepared',
    setup_command TEXT,                      -- comando shell pronto pro owner colar
    preview_url TEXT,                        -- URL alvo após `docker compose up`
    repository_url TEXT,                     -- URL do remoto que será clonado
    notes TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stopped_at TIMESTAMPTZ,
    CONSTRAINT app_preview_sessions_status_check
        CHECK (status IN ('prepared', 'running', 'stopped', 'error'))
);

CREATE INDEX IF NOT EXISTS ix_app_preview_project_created
    ON app_preview_sessions(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_app_preview_active
    ON app_preview_sessions(project_id)
    WHERE status IN ('prepared', 'running');

COMMIT;
