-- MVP 19 Fase 19.3 — Glossário vivo por projeto.
-- ============================================================================
-- Termos específicos do domínio do projeto (siglas da empresa, entidades de
-- negócio, produtos, serviços) extraídos automaticamente do corpus já
-- processado pelo pipeline (documentos ingeridos + respostas do Arguidor +
-- descrições dos módulos + OCG.PROJECT_PROFILE) — NÃO re-extrai arquivos.
--
-- Ciclo de vida:
--   candidate  — extraído automaticamente; GP ainda não revisou.
--   approved   — GP validou; aparece na seção 1.3 do ERS.
--   rejected   — GP descartou (falso positivo, ruído); não aparece.
--
-- Extração é idempotente via UNIQUE(project_id, LOWER(term)).
-- Classificação é responsabilidade do GP (sem IA decidindo sozinho).

CREATE TABLE IF NOT EXISTS project_glossary_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    term VARCHAR(200) NOT NULL,
    definition TEXT NOT NULL DEFAULT '',
    source VARCHAR(30) NOT NULL DEFAULT 'ingested_doc',
    status VARCHAR(20) NOT NULL DEFAULT 'candidate',
    source_reference TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    approved_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ NULL,
    rejected_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    rejected_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotência canônica da extração: mesmo termo no mesmo projeto = linha única.
-- Case-insensitive (LOWER no índice) porque "API" e "api" são o mesmo termo.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_glossary_project_term
    ON project_glossary_terms (project_id, LOWER(term));

CREATE INDEX IF NOT EXISTS idx_glossary_project_status
    ON project_glossary_terms (project_id, status);

COMMENT ON COLUMN project_glossary_terms.source IS
    'Origem do candidato: ingested_doc | arguider_response | module_description | ocg_profile | manual';

COMMENT ON COLUMN project_glossary_terms.status IS
    'MVP 19 Fase 19.3: candidate (extraído, pendente de revisão) | '
    'approved (GP validou; entra na seção 1.3 do ERS) | '
    'rejected (GP descartou — não volta a aparecer na extração).';

COMMENT ON COLUMN project_glossary_terms.source_reference IS
    'Contexto curto de onde o termo foi extraído (ex: nome do documento, '
    'primeira frase onde apareceu). Uso apenas exibição na UI para o GP '
    'revisar com contexto.';
