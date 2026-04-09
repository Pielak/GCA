-- Migration 005: test_artifacts + test_execution_logs
-- Session 14 — QA Readiness + Tester Review

CREATE TABLE IF NOT EXISTS test_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_id       UUID REFERENCES module_candidates(id),
    test_type       VARCHAR(20) NOT NULL CHECK (test_type IN (
                        'unit', 'integration', 'e2e',
                        'regression', 'load', 'security'
                    )),
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    file_path       VARCHAR(500),
    content         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','edited')),
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_edited_by  UUID REFERENCES users(id),
    last_edited_at  TIMESTAMPTZ,
    version         INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_test_artifacts_project ON test_artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_test_artifacts_module ON test_artifacts(module_id);
CREATE INDEX IF NOT EXISTS idx_test_artifacts_type ON test_artifacts(test_type);
CREATE INDEX IF NOT EXISTS idx_test_artifacts_status ON test_artifacts(status);

CREATE TABLE IF NOT EXISTS test_execution_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_artifact_id    UUID NOT NULL REFERENCES test_artifacts(id) ON DELETE CASCADE,
    project_id          UUID NOT NULL REFERENCES projects(id),
    executed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_by         UUID NOT NULL REFERENCES users(id),
    status              VARCHAR(20) NOT NULL CHECK (status IN ('passed','failed','error','skipped')),
    duration_ms         INTEGER,
    output              TEXT,
    module_name         VARCHAR(255),
    function_name       VARCHAR(255),
    test_created_by     UUID NOT NULL REFERENCES users(id),
    test_edited_by      UUID REFERENCES users(id),
    test_version_at_run INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_test_exec_logs_artifact ON test_execution_logs(test_artifact_id);
CREATE INDEX IF NOT EXISTS idx_test_exec_logs_project ON test_execution_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_test_exec_logs_status ON test_execution_logs(status);
