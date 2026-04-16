-- 016 — Release Bundles: artefatos de handoff de cada projeto
--
-- Cada bundle é um zip contendo:
--   MANIFEST.json — lista de deliverables verificados + evidências + sha256
--   RELEASE_NOTES.md — diff humano-legível desde o release anterior (de
--                      ocg_delta_log)
--   deliverables_status.json — snapshot completo do estado dos deliverables
--   docs/ — exports de docs versionados (ADRs, diagramas, compliance)
--
-- Versionamento: incremental por projeto (v1, v2, ...). Imutável após
-- criação — bundles antigos são preservados como histórico de release.

BEGIN;

CREATE TABLE IF NOT EXISTS project_releases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Versão incremental por projeto (1, 2, 3...). UNIQUE garante atomicidade.
    version INT NOT NULL,

    -- Status do bundle
    -- generating: zip em construção
    -- ready: zip completo e disponível para download
    -- failed: erro durante geração (ver error_message)
    status VARCHAR(20) NOT NULL DEFAULT 'generating',

    -- Localização e integridade
    file_path TEXT,                          -- /app/storage/releases/{pid}/v{N}.zip
    file_size_bytes BIGINT,
    sha256 VARCHAR(64),                      -- SHA-256 do zip (verificável)

    -- Pré-check
    readiness_pct REAL,                      -- snapshot do readiness no momento da release
    readiness_threshold REAL NOT NULL DEFAULT 90.0,

    -- Conteúdo do manifest (snapshot estruturado)
    manifest_json TEXT,                      -- JSON: {deliverables, evidence_refs, ocg_version, git_ref}
    error_message TEXT,                      -- preenchido apenas se status='failed'

    -- Audit
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_release_per_project_version UNIQUE (project_id, version),
    CONSTRAINT ck_release_status CHECK (status IN ('generating', 'ready', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_releases_project_status ON project_releases(project_id, status);
CREATE INDEX IF NOT EXISTS idx_releases_project_created ON project_releases(project_id, created_at DESC);

COMMENT ON TABLE project_releases IS
    'Release Bundles: handoffs versionados (zip + manifest + release notes) de cada projeto.';

COMMIT;
