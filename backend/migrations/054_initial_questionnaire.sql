-- Migration 054: Initial Questionnaire Table
--
-- Tabela para armazenar respostas do questionário inicial (20 perguntas)
-- que cada projeto preenche antes das personas gerarem questionnaires dinâmicos.
--
-- Estrutura: seções A-E com 20 perguntas, status de submissão/validação,
-- attachments por pergunta, rastreamento de quem preencheu/validou e quando.

BEGIN;

-- Criar tabela initial_questionnaires
CREATE TABLE initial_questionnaires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Seção A: Contexto do Projeto (4 perguntas)
    q1_name VARCHAR(255),
    q1_objective TEXT,
    q2_type VARCHAR(50),  -- 'novo_sistema' | 'refactor' | 'feature_nova' | 'manutencao'
    q3_users TEXT,
    q3_volume INTEGER,
    q4_months INTEGER,
    q4_target_date DATE,

    -- Seção B: Requisitos Funcionais (5 perguntas)
    q5_flows TEXT,
    q6_integrations JSONB DEFAULT '[]'::JSONB,  -- array de strings
    q6_integrations_detail TEXT,
    q7_frequency VARCHAR(50),  -- 'centenas_dia' | 'milhares_dia' | 'dezenas_milhares' | 'centenas_milhares_hora'
    q8_reports TEXT,
    q9_rules TEXT,

    -- Seção C: Requisitos Não-Funcionais (6 perguntas)
    q10_performance VARCHAR(50),
    q11_uptime VARCHAR(20),  -- '99' | '99.5' | '99.9' | '99.99' | '99.999'
    q12_sensitive_data JSONB DEFAULT '[]'::JSONB,  -- array de strings
    q13_scalability VARCHAR(50),  -- 'estavel' | 'modesto' | 'agressivo' | 'exponencial'
    q14_compliance JSONB DEFAULT '[]'::JSONB,  -- array de strings
    q15_longevity VARCHAR(50),  -- 'mvp_curto' | 'medio_prazo' | 'longo_prazo' | 'permanente'

    -- Seção D: Contexto Técnico (3 perguntas)
    q16_stack TEXT,
    q17_existing_infra TEXT,
    q18_constraints TEXT,

    -- Seção E: Visão do GCA (2 perguntas)
    q19_gca_expectations JSONB DEFAULT '[]'::JSONB,  -- array de strings
    q20_risks TEXT,

    -- Attachments: {question_id: [file_urls]}
    question_images JSONB DEFAULT '{}'::JSONB,

    -- Status e timestamps
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- 'draft' | 'submitted' | 'validated'
    submitted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    submitted_at TIMESTAMP,
    validated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    validated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraint: apenas 1 por projeto
    UNIQUE(project_id),

    -- Constraint: se status='submitted', submitted_at deve ser não-null
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
CREATE INDEX idx_initial_questionnaire_project ON initial_questionnaires(project_id);
CREATE INDEX idx_initial_questionnaire_status ON initial_questionnaires(status);
CREATE INDEX idx_initial_questionnaire_submitted_by ON initial_questionnaires(submitted_by);

-- Comentários para documentação
COMMENT ON TABLE initial_questionnaires IS 'Questionário inicial com 20 perguntas (seções A-E) que todo projeto preenche antes das personas gerarem questionnaires dinâmicos';
COMMENT ON COLUMN initial_questionnaires.status IS 'draft = preenchendo; submitted = enviado; validated = validado por personas';
COMMENT ON COLUMN initial_questionnaires.q6_integrations IS 'Array JSON de integrações: ["sms", "google_calendar", etc]';
COMMENT ON COLUMN initial_questionnaires.q12_sensitive_data IS 'Array JSON de dados sensíveis: ["dados_pessoais", "dados_saude", etc]';
COMMENT ON COLUMN initial_questionnaires.q14_compliance IS 'Array JSON de compliance: ["lgpd", "gdpr", "hipaa", etc]';
COMMENT ON COLUMN initial_questionnaires.q19_gca_expectations IS 'Array JSON: ["codigo_completo", "documentacao", etc]';
COMMENT ON COLUMN initial_questionnaires.question_images IS 'Object JSON: {"q1": ["url1", "url2"], "q3": ["url3"]}';

COMMIT;
