-- MVP 9 Fase 9.2 — Cache de detalhamento on-demand por item.
-- ============================================================================
-- O endpoint GET /projects/{id}/modules/{mid}/details invoca Ollama (LLM
-- local, baixa criticidade conforme §6.2) pra gerar:
--   - what_it_is (descrição técnica)
--   - prerequisites
--   - missing_inputs (o que falta na ingestão pra elaborar)
--   - input_examples
--   - suggested_template_sections (insumo pra Fase 9.5.1 montar PDF)
--
-- Sem cache, cada clique do GP no item dispararia Ollama (~3-5s + watt).
-- Esta coluna persiste o JSON pro modal abrir instantaneamente; regeneração
-- só com refresh explícito.

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS details_json TEXT NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS details_generated_at TIMESTAMPTZ NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS details_provider VARCHAR(50) NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS details_model VARCHAR(100) NULL;

COMMENT ON COLUMN module_candidates.details_json IS
    'MVP 9 Fase 9.2: cache do detalhamento gerado por LLM local. JSON com '
    'what_it_is, prerequisites, missing_inputs, input_examples, '
    'suggested_template_sections. NULL = nunca gerado.';

COMMENT ON COLUMN module_candidates.details_generated_at IS
    'Quando o details_json foi gerado. Permite invalidar cache antigo se '
    'OCG ou prompt evoluir.';
