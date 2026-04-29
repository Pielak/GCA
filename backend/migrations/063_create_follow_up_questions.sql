-- MVP D: Follow-up questions de personas baseado em análise inicial

CREATE TABLE IF NOT EXISTS persona_follow_up_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,
    ocg_individual_id UUID NOT NULL REFERENCES ocg_individual(id) ON DELETE CASCADE,
    persona_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    persona_name VARCHAR(100) NOT NULL,  -- "Persona - DBA", etc

    -- Pergunta e contexto
    question_text TEXT NOT NULL,  -- "Qual é a criticidade de replicação de dados?"
    context VARCHAR(500) DEFAULT NULL,  -- Motivo da pergunta baseado em análise
    question_order SMALLINT DEFAULT 0,  -- Ordem de apresentação

    -- Resposta do user
    answer_text TEXT DEFAULT NULL,  -- Resposta fornecida
    answer_provided_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    answered_by UUID DEFAULT NULL REFERENCES users(id),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, answered, refinement_complete

    -- Rastreamento
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_follow_up_project ON persona_follow_up_questions(project_id);
CREATE INDEX idx_follow_up_document ON persona_follow_up_questions(document_id);
CREATE INDEX idx_follow_up_persona ON persona_follow_up_questions(persona_id);
CREATE INDEX idx_follow_up_status ON persona_follow_up_questions(status);
CREATE INDEX idx_follow_up_ocg ON persona_follow_up_questions(ocg_individual_id);

-- Tabela para armazenar análises refinadas após Q&A
CREATE TABLE IF NOT EXISTS ocg_individual_refined (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ocg_individual_id UUID NOT NULL REFERENCES ocg_individual(id) ON DELETE CASCADE,
    refinement_iteration SMALLINT NOT NULL DEFAULT 1,  -- 1ª, 2ª, etc

    -- Parecer refinado após Q&A
    parecer_refined JSONB NOT NULL,

    -- Mudanças detectadas
    changed_fields JSONB DEFAULT NULL,  -- ["criticidade", "recomendacoes"]
    change_summary VARCHAR(500) DEFAULT NULL,

    -- Rastreamento
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(ocg_individual_id, refinement_iteration)
);

CREATE INDEX idx_ocg_refined_original ON ocg_individual_refined(ocg_individual_id);
