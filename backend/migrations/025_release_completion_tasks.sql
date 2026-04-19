-- MVP 7 Fase 4 — Assistente pós-release (completion tasks)
--
-- Quando uma release adiciona um campo novo obrigatório por projeto
-- (ex.: ticket pediu novo campo no questionário), o sistema cria 1
-- linha aqui por projeto afetado. O GP/Admin completa pela UI e a
-- task vira status='done'.
--
-- Status: pending | done | dismissed
--
-- Isso é estrutura pronta pra uso futuro — nenhuma release destrutiva
-- aplicada ainda precisa disso no dogfood, mas a tabela fica disponível
-- pra quando a primeira release com campo novo surgir.

BEGIN;

CREATE TABLE IF NOT EXISTS release_completion_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id UUID NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind VARCHAR(60) NOT NULL,         -- ex: "questionnaire_field", "ocg_field", "setting"
    title VARCHAR(200) NOT NULL,
    description TEXT,
    payload TEXT,                       -- JSON com spec do campo a completar
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'dismissed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    completed_by UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_release_tasks_project_status
    ON release_completion_tasks (project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_release_tasks_release
    ON release_completion_tasks (release_id, status);

COMMIT;
