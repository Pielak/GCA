-- Migration: Add OCG tables for agent pipeline
-- Date: 2026-04-07
-- Description: Adds OCG (Objeto Contexto Global) tables to store multi-agent analysis results

-- Create OCG table
CREATE TABLE IF NOT EXISTS ocg (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    questionnaire_id UUID UNIQUE NOT NULL,
    project_id UUID,

    -- Pillar scores (0-100)
    p1_business_score FLOAT,
    p2_rules_score FLOAT,
    p3_features_score FLOAT,
    p4_nfr_score FLOAT,
    p5_architecture_score FLOAT,
    p6_data_score FLOAT,
    p7_security_score FLOAT,

    -- Composite score
    overall_score FLOAT,
    status VARCHAR(50) NOT NULL DEFAULT 'READY',
    is_blocking BOOLEAN NOT NULL DEFAULT FALSE,

    -- Full OCG as JSON
    ocg_data TEXT NOT NULL,

    -- Audit trail
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    generated_by UUID,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewed_by UUID,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Foreign keys
    CONSTRAINT fk_ocg_questionnaire_id FOREIGN KEY (questionnaire_id) REFERENCES questionnaires(id) ON DELETE CASCADE,
    CONSTRAINT fk_ocg_project_id FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CONSTRAINT fk_ocg_generated_by FOREIGN KEY (generated_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_ocg_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Create indexes for OCG table
CREATE INDEX IF NOT EXISTS idx_ocg_questionnaire_id ON ocg(questionnaire_id);
CREATE INDEX IF NOT EXISTS idx_ocg_project_id ON ocg(project_id);
CREATE INDEX IF NOT EXISTS idx_ocg_overall_score ON ocg(overall_score);
CREATE INDEX IF NOT EXISTS idx_ocg_status ON ocg(status);
CREATE INDEX IF NOT EXISTS idx_ocg_is_blocking ON ocg(is_blocking);
CREATE INDEX IF NOT EXISTS idx_ocg_generated_at ON ocg(generated_at);

-- Create OCG Analysis Log table
CREATE TABLE IF NOT EXISTS ocg_analysis_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocg_id UUID NOT NULL,

    -- Agent metadata
    agent_name VARCHAR(50) NOT NULL,
    agent_input_hash VARCHAR(64),
    agent_output_hash VARCHAR(64),

    -- Performance metrics
    tokens_used INTEGER,
    latency_ms INTEGER,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Foreign key
    CONSTRAINT fk_analysis_log_ocg_id FOREIGN KEY (ocg_id) REFERENCES ocg(id) ON DELETE CASCADE
);

-- Create indexes for OCG Analysis Log table
CREATE INDEX IF NOT EXISTS idx_analysis_log_ocg_id ON ocg_analysis_log(ocg_id);
CREATE INDEX IF NOT EXISTS idx_analysis_log_agent_name ON ocg_analysis_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_analysis_log_created_at ON ocg_analysis_log(created_at);

-- Grant permissions (if needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ocg TO gca;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ocg_analysis_log TO gca;
