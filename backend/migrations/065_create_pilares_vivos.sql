-- MVP Pilares Vivos: Consolidação Viva de Análise de 7 Personas
-- Substitui documentos estáticos por análise dinâmica regenerável

-- Tabela principal: resultado consolidado de análise das 7 personas
CREATE TABLE IF NOT EXISTS pilares_vivos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Documento consolidado com análise de cada persona
    -- Estrutura JSON: {
    --   "P4_Arquiteto": {ocg_individual_json},
    --   "P1_DBA": {ocg_individual_json},
    --   "P2_Compliance": {ocg_individual_json},
    --   "P3_Seguranca": {ocg_individual_json},
    --   "P5_Dev": {ocg_individual_json},
    --   "P6_Tester": {ocg_individual_json},
    --   "P7_QA": {ocg_individual_json}
    -- }
    documento JSONB NOT NULL,

    -- Contexto: resumo dos 87 Gatekeeper items usado para gerar
    gatekeeper_summary JSONB DEFAULT NULL,

    -- Contexto: respostas do Questionário Técnico usadas
    questionnaire_responses JSONB DEFAULT NULL,

    -- Rastreamento
    gerado_por UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gerado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    regenerado_em TIMESTAMP WITH TIME ZONE DEFAULT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint: apenas um documento "vivo" por projeto (o mais recente)
    UNIQUE(project_id)
);

-- Índices
CREATE INDEX idx_pilares_vivos_project ON pilares_vivos(project_id);
CREATE INDEX idx_pilares_vivos_gerado_por ON pilares_vivos(gerado_por);
CREATE INDEX idx_pilares_vivos_gerado_em ON pilares_vivos(gerado_em DESC);

-- Tabela histórica: versões anteriores para rastreabilidade
CREATE TABLE IF NOT EXISTS pilares_vivos_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    pilares_vivos_id UUID NOT NULL REFERENCES pilares_vivos(id) ON DELETE CASCADE,

    -- Documento da versão anterior
    documento JSONB NOT NULL,

    -- Contexto usado
    gatekeeper_summary JSONB DEFAULT NULL,
    questionnaire_responses JSONB DEFAULT NULL,

    -- Rastreamento da versão
    gerado_por UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gerado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    archived_em TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Mudanças detectadas (quais personas mudaram)
    personas_modificadas TEXT[] DEFAULT '{}',  -- ["P1_DBA", "P3_Seguranca"]
    resumo_mudancas VARCHAR(500) DEFAULT NULL
);

-- Índices
CREATE INDEX idx_pilares_history_project ON pilares_vivos_history(project_id);
CREATE INDEX idx_pilares_history_current ON pilares_vivos_history(pilares_vivos_id);
CREATE INDEX idx_pilares_history_gerado_em ON pilares_vivos_history(gerado_em DESC);
