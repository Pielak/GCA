-- MVP 9 Fase 9.2.ext — WebFetch curado por external_reference declarado.
-- ============================================================================
-- Quando GP sabe que um item se refere a uma API/serviço público com
-- documentação online (DataJud, gov.br, Anthropic API, etc), declara
-- a URL aqui. Detalhamento (Fase 9.2) inclui o conteúdo extraído no
-- prompt do Ollama → descrição mais aderente à realidade do serviço.
--
-- Sem URL declarada, GCA NÃO navega autonomamente — curadoria
-- explícita, sem crawl. Regra dura do contrato §7 MVP 9 (9.2.ext).

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS external_reference VARCHAR(500) NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS external_reference_content TEXT NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS external_reference_fetched_at TIMESTAMPTZ NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS external_reference_fetch_error TEXT NULL;

COMMENT ON COLUMN module_candidates.external_reference IS
    'MVP 9 Fase 9.2.ext: URL de documentação pública relevante ao item '
    '(API externa, gov.br, doc oficial). NULL = sem referência. WebFetch '
    'só roda quando preenchido — sem navegação autônoma.';

COMMENT ON COLUMN module_candidates.external_reference_content IS
    'Texto extraído da URL (max 50KB). Limpo de scripts/style/nav. '
    'Cache até GP fazer refresh manual.';
