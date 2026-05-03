-- MVP C: Tabela para armazenar OCG Individual (parecer de cada persona)

CREATE TABLE IF NOT EXISTS ocg_individual (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,
    persona_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona_type VARCHAR(50) NOT NULL,  -- "Persona - DBA", "Persona - Compliance", etc

    -- Resultado da análise (JSON estruturado)
    parecer JSONB NOT NULL,  -- { titulo, analise, riscos, recomendacoes, criticidade, etc }

    -- Rastreamento
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint: uma análise por persona por documento
    UNIQUE(project_id, document_id, persona_id)
);

CREATE INDEX idx_ocg_individual_project ON ocg_individual(project_id);
CREATE INDEX idx_ocg_individual_document ON ocg_individual(document_id);
CREATE INDEX idx_ocg_individual_persona ON ocg_individual(persona_id);

-- MVP C: Tabela para detecção de conflitos entre personas

CREATE TABLE IF NOT EXISTS persona_discrepancies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,

    -- Campo específico onde há conflito (ex: "stack_backend", "database_type")
    field_name VARCHAR(255) NOT NULL,

    -- Personas em conflito (JSON array de persona_types)
    conflicting_personas JSONB NOT NULL,  -- ["Persona - DBA", "Persona - Dev"]

    -- Valores conflitantes propostos
    values_proposed JSONB NOT NULL,  -- { "Persona - DBA": "PostgreSQL", "Persona - Dev": "MongoDB" }

    -- Resolução (se usuário já escolheu)
    resolution_status VARCHAR(20) DEFAULT 'open',  -- open | resolved | accepted
    resolved_value VARCHAR(255) DEFAULT NULL,
    resolved_by UUID DEFAULT NULL REFERENCES users(id),
    resolved_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,

    -- Rastreamento
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_persona_discrepancies_project ON persona_discrepancies(project_id);
CREATE INDEX idx_persona_discrepancies_document ON persona_discrepancies(document_id);
CREATE INDEX idx_persona_discrepancies_status ON persona_discrepancies(resolution_status);
