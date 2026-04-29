-- Migration 058: Discrepancy detection and resolution
-- Tracks conflicts between persona evaluations and how team resolves them

CREATE TABLE discrepancies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    technical_questionnaire_id UUID NOT NULL REFERENCES technical_questionnaires(id) ON DELETE CASCADE,

    -- Campo em conflito: "escopo", "arquitetura.stack", etc
    field_path VARCHAR(200) NOT NULL,

    -- Personas envolvidas: ["gp", "qa", "dev_sr"]
    conflicting_personas JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Valores em conflito: {"gp": "crítico", "qa": "baixa"}
    conflicting_values JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Categorização
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
    category VARCHAR(50),

    -- Status da resolução
    status VARCHAR(20) NOT NULL DEFAULT 'unresolved',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    detected_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Contexto/anotações
    context TEXT,
    resolution_notes TEXT
);

CREATE INDEX idx_discrepancy_project ON discrepancies(project_id);
CREATE INDEX idx_discrepancy_questionnaire ON discrepancies(technical_questionnaire_id);
CREATE INDEX idx_discrepancy_status ON discrepancies(technical_questionnaire_id, status);


CREATE TABLE resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    discrepancy_id UUID NOT NULL REFERENCES discrepancies(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Qual valor foi escolhido
    resolved_value TEXT NOT NULL,

    -- Como foi resolvido: "vote", "override", "arbitration", "compromise"
    resolution_type VARCHAR(50) NOT NULL,

    -- Detalhes de votação (se aplicável)
    vote_details JSONB DEFAULT '{}'::jsonb,

    -- Quem resolveu
    resolved_by UUID NOT NULL REFERENCES users(id),
    resolved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Justificativa
    justification TEXT
);

CREATE INDEX idx_resolution_discrepancy ON resolutions(discrepancy_id);
CREATE INDEX idx_resolution_project ON resolutions(project_id);
