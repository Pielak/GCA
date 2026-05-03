-- Migration 057: PersonaResponse table for parallel persona evaluation
-- Tracks real-time evaluation of each persona during technical questionnaire validation

CREATE TABLE persona_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    technical_questionnaire_id UUID NOT NULL REFERENCES technical_questionnaires(id) ON DELETE CASCADE,

    -- Persona name: "gp", "arquiteto", "dba", "dev_sr", "qa", etc
    persona_name VARCHAR(50) NOT NULL,

    -- Status: pending, evaluating, completed, error
    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    -- Validation result
    decision TEXT,
    ocg_delta JSONB NOT NULL DEFAULT '{}',
    followup_questions JSONB,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Error handling
    error_message TEXT,

    -- IA provider tracking
    ai_provider_used VARCHAR(50),
    ai_model_used VARCHAR(100),

    -- Unique constraint: one response per persona per questionnaire
    CONSTRAINT uq_persona_response_per_questionnaire UNIQUE(technical_questionnaire_id, persona_name)
);

-- Indexes for performance
CREATE INDEX idx_persona_response_project ON persona_responses(project_id);
CREATE INDEX idx_persona_response_questionnaire ON persona_responses(technical_questionnaire_id);
CREATE INDEX idx_persona_response_status ON persona_responses(technical_questionnaire_id, status);
CREATE INDEX idx_persona_response_persona ON persona_responses(technical_questionnaire_id, persona_name);
