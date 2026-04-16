-- 015 — Definition of Done: registry de entregáveis declarados pelo OCG
--
-- Cada projeto tem N entregáveis declarados em OCG.DELIVERABLES (lista de
-- strings). Esta tabela materializa cada um como uma linha rastreável,
-- ligando ao kind classificado, status atual, e evidência da entrega.
--
-- Sincronizada pelo DeliverableRegistry sempre que o OCG é atualizado
-- (chamado por OCGUpdaterService após apply_deltas):
--   - DELIVERABLES adiciona item → INSERT row status='declared'
--   - DELIVERABLES remove item → UPDATE status='waived' (não DELETE para
--     preservar histórico)
--   - DELIVERABLES reordena/renomeia → matching por hash do nome
--     normalizado, atualiza ou marca como waived+novo

BEGIN;

CREATE TABLE IF NOT EXISTS project_deliverables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Identificação
    name VARCHAR(500) NOT NULL,                  -- texto original do OCG
    normalized_name VARCHAR(500) NOT NULL,       -- lowercase + trim, para matching
    category VARCHAR(40) NOT NULL DEFAULT 'other',  -- doc | code | test | config | process | other
    kind VARCHAR(60) NOT NULL DEFAULT 'other_manual',  -- ver deliverable_classifier

    -- Estado
    -- declared: presente no OCG, ainda não verificado
    -- generating: auto-generator em andamento
    -- present: existe evidência mas não verificado
    -- verified: verificado e válido
    -- waived: removido do OCG / marcado como não aplicável
    -- missing: verificação rodou e não encontrou
    status VARCHAR(20) NOT NULL DEFAULT 'declared',

    -- Evidência
    evidence_type VARCHAR(30),     -- file | git_commit | llm_doc | manual | external | none
    evidence_ref VARCHAR(500),     -- caminho/url/uuid conforme evidence_type
    verification_method VARCHAR(60), -- nome do verifier que rodou (ex: 'git_file_exists')

    -- Audit
    last_verified_at TIMESTAMP WITH TIME ZONE,
    verified_by UUID REFERENCES users(id) ON DELETE SET NULL,  -- só preenchido em manual
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Mesmo entregável (pelo nome normalizado) só pode existir uma vez por projeto.
    -- Se o nome muda, criamos novo + waiveramos o antigo.
    CONSTRAINT uq_deliverable_per_project UNIQUE (project_id, normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_deliverables_project_status
    ON project_deliverables(project_id, status);
CREATE INDEX IF NOT EXISTS idx_deliverables_kind
    ON project_deliverables(kind);

COMMENT ON TABLE project_deliverables IS
    'Definition of Done: cada item esperado de OCG.DELIVERABLES como linha rastreável com status + evidência.';

COMMIT;
