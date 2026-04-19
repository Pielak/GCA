-- MVP 9 Fase 9.5.2 — Vínculo upload → item do Roadmap.
-- ============================================================================
-- Quando o GP baixa um template PDF (Fase 9.5.1), preenche e faz upload na
-- aba Ingestão, precisamos saber a qual item do Roadmap o doc se refere
-- pra (a) transitar status do item para 'adicionado' quando o pipeline
-- confirma e (b) criar row em DELIVERABLES.
--
-- target_module_id é descoberto em ordem:
--   1. Form-data field explícito no upload (dropdown na UI).
--   2. Hidden AcroForm field _gca_module_id no PDF.
--   3. Metadata Subject "gca-module:{uuid}".
--   4. Footer visual "gca-module-id={uuid}" (regex).
--
-- ON DELETE SET NULL: se o módulo for excluído, o doc continua existindo
-- mas sem vínculo (audit preservado).

ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS target_module_id UUID NULL
        REFERENCES module_candidates(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ingested_documents_target_module
    ON ingested_documents (target_module_id)
    WHERE target_module_id IS NOT NULL;

COMMENT ON COLUMN ingested_documents.target_module_id IS
    'MVP 9 Fase 9.5.2: vínculo opcional com module_candidates.id. Quando '
    'preenchido, o pipeline (Arguidor + OCG updater) atualiza status do '
    'módulo para "adicionado" e cria row em project_deliverables ao '
    'completar com sucesso.';
