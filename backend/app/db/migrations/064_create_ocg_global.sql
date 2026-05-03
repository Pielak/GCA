-- Migration 064: Create OCG Global table
-- Parecer consolidado de todas as 7 personas

BEGIN;

CREATE TABLE ocg_global (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,

    -- Parecer consolidado
    parecer_consolidated JSONB NOT NULL DEFAULT '{}',

    -- Metadados de consolidação
    consensus_fields JSONB NOT NULL DEFAULT '[]',
    conflicting_fields JSONB NOT NULL DEFAULT '{}',
    voting_results JSONB NOT NULL DEFAULT '{}',

    -- Rastreamento
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consolidated_at TIMESTAMP WITH TIME ZONE,
    consolidated_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Constraint: um OCG Global por documento
    CONSTRAINT uq_ocg_global_per_document UNIQUE (document_id)
);

-- Índices
CREATE INDEX idx_ocg_global_project ON ocg_global(project_id);
CREATE INDEX idx_ocg_global_document ON ocg_global(document_id);

COMMIT;
