-- Migration 068: Create table for chunks with errors during auditoria
-- Purpose: Isolate failed chunks for quarantine and human review (HITL)
-- Enables per-chunk fallback instead of document-level failure cascade

CREATE TABLE chunk_errors_pending_review (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,
    chunk_id VARCHAR(64) NOT NULL,
    error_type VARCHAR(30) NOT NULL,  -- json_invalid | timeout | llm_refusal | schema_validation | unknown
    error_message TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    recovery_attempted BOOLEAN NOT NULL DEFAULT FALSE,
    suggested_fallback TEXT,  -- Sugestão de fallback para resolução
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | resolved | escalated
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    resolution_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunk_error_project ON chunk_errors_pending_review(project_id);
CREATE INDEX idx_chunk_error_document ON chunk_errors_pending_review(document_id);
CREATE INDEX idx_chunk_error_status ON chunk_errors_pending_review(status);
