-- Migration 055: Technical Questionnaire Table
--
-- Tabela para armazenar respostas de questionários técnicos dinâmicos.
-- Diferente do Initial Questionnaire (20 perguntas fixas), os questionários
-- técnicos suportam N perguntas com visibilidade condicional e validação cruzada.
--
-- Estrutura: responses JSONB flexível que armazena {numero: resposta}
-- Schema das perguntas é definido em código (technical_questions_schema.py),
-- não em banco de dados, permitindo mudanças sem migration.
--
-- Status: draft (preenchendo), submitted (enviado), validated (personas leram)

BEGIN;

-- Criar tabela technical_questionnaires
CREATE TABLE technical_questionnaires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Respostas em formato JSONB: {"Q1": "resposta", "Q2": ["opt1", "opt2"], ...}
    responses JSONB DEFAULT '{}'::JSONB,

    -- Progresso em percentual (0-100)
    -- Calculado como: (perguntas_visíveis_preenchidas / perguntas_visíveis) * 100
    progress_percent INTEGER DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),

    -- Status do questionário
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- 'draft' | 'submitted' | 'validated'

    -- Quem preencheu/validou e quando
    submitted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    submitted_at TIMESTAMP,
    validated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    validated_at TIMESTAMP,

    -- Timestamps de auditoria
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints: se status='submitted', submitted_at deve ser não-null
    CHECK (
        (status != 'submitted' AND status != 'validated') OR
        (status IN ('submitted', 'validated') AND submitted_at IS NOT NULL)
    ),

    -- Constraint: se status='validated', validated_at deve ser não-null
    CHECK (
        (status != 'validated') OR
        (status = 'validated' AND validated_at IS NOT NULL)
    )
);

-- Índices para queries rápidas
CREATE INDEX idx_technical_questionnaire_project ON technical_questionnaires(project_id);
CREATE INDEX idx_technical_questionnaire_status ON technical_questionnaires(project_id, status);
CREATE INDEX idx_technical_questionnaire_submitted_by ON technical_questionnaires(submitted_by);

-- Comentários para documentação
COMMENT ON TABLE technical_questionnaires IS 'Questionários técnicos dinâmicos com N perguntas, visibilidade condicional e validação cruzada automática';
COMMENT ON COLUMN technical_questionnaires.responses IS 'Object JSONB com respostas: {"Q1": "valor", "Q3": ["opt1", "opt2"], ...}';
COMMENT ON COLUMN technical_questionnaires.progress_percent IS 'Percentual de progresso baseado em perguntas visíveis preenchidas';
COMMENT ON COLUMN technical_questionnaires.status IS 'draft = preenchendo; submitted = enviado; validated = validado por personas';

COMMIT;
