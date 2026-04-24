-- MVP M01 — iterações de Questões em Aberto customizadas.
-- Cada iteração gera 4-7 perguntas focadas nos pilares P1..P7 com score < 75
-- enquanto overall < 90. Respostas viram ingested_documents normais (não há
-- tabela de respostas — o pipeline canônico Arguidor→OCG Updater processa).

CREATE TABLE custom_questionnaire_iterations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    iteration INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- status: 'pending' | 'answered' | 'converged' | 'infeasible' | 'superseded'
    target_pillars JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Ex: ["P3_scope", "P4_quality"]
    questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- [{id, type, text, context, pillar, options?, required, max_chars?}]
    pdf_blob BYTEA,
    answer_document_id UUID REFERENCES ingested_documents(id) ON DELETE SET NULL,
    ocg_version_before INT,
    ocg_version_after INT,
    overall_before NUMERIC(5,2),
    overall_after NUMERIC(5,2),
    converged BOOLEAN NOT NULL DEFAULT FALSE,
    not_applicable_ratio NUMERIC(4,3),
    convergence_threshold NUMERIC(4,2) NOT NULL DEFAULT 1.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, iteration)
);

CREATE INDEX ix_custom_q_iter_project_status
    ON custom_questionnaire_iterations (project_id, status);
CREATE INDEX ix_custom_q_iter_answer_doc
    ON custom_questionnaire_iterations (answer_document_id)
    WHERE answer_document_id IS NOT NULL;

COMMENT ON TABLE custom_questionnaire_iterations IS
    'M01 — histórico de iterações de questionário customizado por projeto.';
COMMENT ON COLUMN custom_questionnaire_iterations.status IS
    'pending|answered|converged|infeasible|superseded';
COMMENT ON COLUMN custom_questionnaire_iterations.target_pillars IS
    'Lista dos pilares P1..P7 com score < 75 no momento da geração.';
