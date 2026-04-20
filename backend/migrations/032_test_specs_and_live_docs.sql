-- MVP 10 Fase 10.1 — TestSpec + LiveDoc reativos ao OCG.
-- ============================================================================
-- 2 tabelas novas pra camada de PLANO (spec) separada da camada de
-- EXECUÇÃO (TestArtifact/TestFile já existentes e não tocadas).
--
-- `test_specs` — plano de teste em plain text gerado por IA, granularidade
-- (module_id × spec_type). module_id=NULL para specs globais de
-- security/compliance consolidando OCG todo.
--
-- `live_docs` — doc vivo por módulo (Ollama) ou consolidado do projeto
-- (Premium). Substitui os placeholders hardcoded que existem no
-- LiveDocsPage pré-MVP10.
--
-- Stale detection: ambas gravam `ocg_version_at_generation`; Fase 10.4
-- compara com OCG atual pra marcar `status='stale'` sem regenerar.

CREATE TABLE IF NOT EXISTS test_specs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    -- NULL = spec global (security/compliance consolidando OCG inteiro)
    module_id UUID NULL REFERENCES module_candidates(id) ON DELETE CASCADE,
    spec_type VARCHAR(20) NOT NULL,  -- unit | integration | security | compliance | e2e
    content TEXT NOT NULL DEFAULT '',  -- markdown plain text
    provenance_json TEXT NULL,         -- {ocg_version, questionnaire_id, ingested_doc_ids, prompt_hash}
    ocg_version_at_generation INTEGER NULL,
    generated_at TIMESTAMPTZ NULL,
    generator_provider VARCHAR(50) NULL,  -- 'ollama' | 'anthropic' | 'openai'
    generator_model VARCHAR(100) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft | approved | rejected | stale
    approved_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ NULL,
    rejected_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    rejection_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_test_spec_unique UNIQUE (project_id, module_id, spec_type)
);

-- NULL module_id tem múltiplos specs globais (1 security + 1 compliance),
-- então uq_test_spec_unique acima tolera. Index separado pra leitura.
CREATE INDEX IF NOT EXISTS idx_test_specs_project_type
    ON test_specs (project_id, spec_type);
CREATE INDEX IF NOT EXISTS idx_test_specs_module
    ON test_specs (module_id) WHERE module_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_test_specs_status
    ON test_specs (project_id, status);

COMMENT ON TABLE test_specs IS
    'MVP 10 Fase 10.1 — plano/spec de teste em plain text gerado por LLM. '
    'Camada separada de TestArtifact (implementação concreta CRUD manual) '
    'e TestFile (blueprint pós-CodeGen).';

COMMENT ON COLUMN test_specs.module_id IS
    'NULL = spec global (security/compliance consolidando OCG). '
    'FK preenchido = spec por módulo (unit/integration/e2e).';

COMMENT ON COLUMN test_specs.status IS
    'draft: gerado, aguardando revisão GP/QA. '
    'approved: GP/QA aprovou, serve de insumo pro Tester. '
    'rejected: rejeitado com rejection_reason preenchido. '
    'stale: OCG avançou desde ocg_version_at_generation, precisa regenerar.';


CREATE TABLE IF NOT EXISTS live_docs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    -- NULL = doc consolidado do projeto (index, architecture global)
    module_id UUID NULL REFERENCES module_candidates(id) ON DELETE CASCADE,
    doc_type VARCHAR(30) NOT NULL,  -- module_doc | index | architecture
    content TEXT NOT NULL DEFAULT '',
    provenance_json TEXT NULL,
    ocg_version_at_generation INTEGER NULL,
    generated_at TIMESTAMPTZ NULL,
    generator_provider VARCHAR(50) NULL,
    generator_model VARCHAR(100) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_live_doc_unique UNIQUE (project_id, module_id, doc_type)
);

CREATE INDEX IF NOT EXISTS idx_live_docs_project_type
    ON live_docs (project_id, doc_type);
CREATE INDEX IF NOT EXISTS idx_live_docs_module
    ON live_docs (module_id) WHERE module_id IS NOT NULL;

COMMENT ON TABLE live_docs IS
    'MVP 10 Fase 10.1 — documentação viva gerada por LLM do projeto. '
    'doc_type=module_doc exige module_id; index/architecture usam NULL '
    '(consolidado). Não substitui docs em Git (README etc) — complementa.';
