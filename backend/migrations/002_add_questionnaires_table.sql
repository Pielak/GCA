-- Migration: Add questionnaires table for technical stack analysis
-- Date: 2026-04-06
-- Purpose: Persist questionnaire submissions and analysis results

-- Create questionnaires table
CREATE TABLE IF NOT EXISTS questionnaires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gp_email VARCHAR(255) NOT NULL,

    -- Submitted responses (JSON)
    responses TEXT NOT NULL,

    -- Analysis results
    adherence_score INTEGER,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    approved BOOLEAN DEFAULT FALSE NOT NULL,

    -- Validation results (JSON)
    validations TEXT,
    observations TEXT,
    restrictions TEXT,
    highlighted_fields TEXT,

    -- Metadata
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    analyzed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_questionnaires_project_id ON questionnaires(project_id);
CREATE INDEX IF NOT EXISTS idx_questionnaires_gp_email ON questionnaires(gp_email);
CREATE INDEX IF NOT EXISTS idx_questionnaires_status ON questionnaires(status);
CREATE INDEX IF NOT EXISTS idx_questionnaires_approved ON questionnaires(approved);
CREATE INDEX IF NOT EXISTS idx_questionnaires_submitted_at ON questionnaires(submitted_at);
CREATE INDEX IF NOT EXISTS idx_questionnaires_adherence_score ON questionnaires(adherence_score);

-- Add table comment
COMMENT ON TABLE questionnaires IS 'Technical questionnaire submissions with intelligent analysis results';
COMMENT ON COLUMN questionnaires.id IS 'Unique questionnaire identifier';
COMMENT ON COLUMN questionnaires.project_id IS 'FK to projects table';
COMMENT ON COLUMN questionnaires.gp_email IS 'Project manager email for notifications';
COMMENT ON COLUMN questionnaires.responses IS 'Original questionnaire responses (JSON)';
COMMENT ON COLUMN questionnaires.adherence_score IS 'Architecture adherence score (0-100)';
COMMENT ON COLUMN questionnaires.status IS 'Analysis status: pending, incomplete, ok';
COMMENT ON COLUMN questionnaires.approved IS 'Approval status (score >= 85%)';
COMMENT ON COLUMN questionnaires.validations IS 'Analysis validation results (JSON: conflicts, gaps, incompatibilities)';
COMMENT ON COLUMN questionnaires.observations IS 'Human-readable observations from analysis';
COMMENT ON COLUMN questionnaires.restrictions IS 'Compliance and security restrictions';
COMMENT ON COLUMN questionnaires.highlighted_fields IS 'Fields with issues (JSON array)';
COMMENT ON COLUMN questionnaires.submitted_at IS 'When questionnaire was submitted';
COMMENT ON COLUMN questionnaires.analyzed_at IS 'When analysis was completed';
