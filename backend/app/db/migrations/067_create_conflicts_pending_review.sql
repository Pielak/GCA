-- Migration 067: Create conflicts_pending_review table
-- FASE 1 Refactor — Auditor Orchestrator
-- Stores conflicts between personas awaiting human decision (HITL)

BEGIN;

CREATE TABLE IF NOT EXISTS conflicts_pending_review (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,
    route_map_id UUID NOT NULL REFERENCES document_route_maps(id) ON DELETE CASCADE,

    -- What personas disagree on
    field_name VARCHAR(255) NOT NULL,  -- e.g., "p1_business_score", "architecture_recommendation"
    personas_involved JSONB NOT NULL,  -- list of persona tags involved
    values_by_persona JSONB NOT NULL,  -- {persona_tag: value}
    conflict_reason TEXT,

    -- Resolution status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, resolved
    resolved_value JSONB,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_justification TEXT,

    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_conflict_project ON conflicts_pending_review(project_id);
CREATE INDEX idx_conflict_status ON conflicts_pending_review(status);
CREATE INDEX idx_conflict_document ON conflicts_pending_review(document_id);

COMMIT;
