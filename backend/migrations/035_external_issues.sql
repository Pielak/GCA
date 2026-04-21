-- MVP 20 Fase 20.1a — Foundation do Issue Tracker Bridge.
-- ============================================================================
-- Vínculo entre `module_candidates` aprovados do GCA e issues em trackers
-- externos do cliente (Jira, Trello, e futuros Linear/Asana/GitHub Issues).
--
-- Decisão binária #1 do MVP 20: config é POR PROJETO, não instância-wide.
-- Decisão binária #2: status mapping configurável por projeto → o campo
-- `status_canonical` guarda o estado CANÔNICO do GCA ({todo, in_progress,
-- review, done, cancelled}); a tradução do status específico do provider
-- (ex: "Em análise pelo jurídico" do Jira) vive na config do projeto.
--
-- Compartimentalização §2.2: todas as queries filtram por project_id;
-- issue do projeto A nunca aparece em tracker do projeto B.
--
-- Idempotência: UNIQUE (project_id, provider, external_id) — webhook
-- duplicado não gera row nova.

CREATE TABLE IF NOT EXISTS external_issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_candidate_id UUID NULL REFERENCES module_candidates(id) ON DELETE SET NULL,

    provider VARCHAR(20) NOT NULL,
    external_id VARCHAR(200) NOT NULL,
    url TEXT NULL,

    title VARCHAR(500) NOT NULL,
    status_canonical VARCHAR(20) NOT NULL DEFAULT 'todo',
    status_raw VARCHAR(100) NULL,
    priority VARCHAR(20) NULL,

    provider_specific JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    synced_at TIMESTAMPTZ NULL,
    closed_at TIMESTAMPTZ NULL
);

-- Idempotência de webhook: mesmo issue externo no mesmo projeto = linha única.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_external_issue_provider_external_id
    ON external_issues (project_id, provider, external_id);

-- Consultas comuns.
CREATE INDEX IF NOT EXISTS idx_external_issues_project
    ON external_issues (project_id);

CREATE INDEX IF NOT EXISTS idx_external_issues_module_candidate
    ON external_issues (module_candidate_id)
    WHERE module_candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_external_issues_status
    ON external_issues (project_id, status_canonical);

COMMENT ON COLUMN external_issues.provider IS
    'Provider canônico: jira | trello | linear | asana | github (V1 aceita apenas jira, trello).';

COMMENT ON COLUMN external_issues.external_id IS
    'ID nativo do provider: Jira key (ex: PROJ-123), Trello card id, etc.';

COMMENT ON COLUMN external_issues.status_canonical IS
    'Estado CANÔNICO do GCA: todo | in_progress | review | done | cancelled. '
    'Mapeamento do status_raw (específico do provider) vive em projeto.settings.';

COMMENT ON COLUMN external_issues.status_raw IS
    'Último status retornado pelo provider — preserva naming específico '
    '(ex: "In Analysis by Legal" do Jira). Pra debug e auditoria.';

COMMENT ON COLUMN external_issues.provider_specific IS
    'Payload JSON com campos específicos que o adapter do provider quer '
    'preservar mas que não cabem no schema canônico (epic_key, sprint_id, '
    'list_id, labels, assignee_id, etc).';
