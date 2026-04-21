-- MVP 19 Fase 19.1 — Classificação explícita de requisitos (RF/RNF/BR).
-- ============================================================================
-- O ERS (IEEE 830) exige que cada requisito seja classificado como Funcional,
-- Não-Funcional ou Regra de Negócio. Hoje `module_candidates` tem `module_type`
-- (feature, component) mas isso descreve a natureza do artefato, não a
-- categoria do requisito perante o padrão IEEE 830.
--
-- Novo campo `requirement_category`:
--   NULL              — ainda não classificado pelo GP (default).
--   'functional'      — requisito funcional (o que o sistema faz).
--   'non_functional'  — NFR (performance, segurança, usabilidade, etc).
--   'business_rule'   — regra de negócio de domínio.
--
-- Classificação é manual pelo GP (decisão canônica §7 MVP 19 decisão #1).
-- Whitelist é aplicação-level; banco aceita qualquer string ≤ 20 caracteres
-- para manter flexibilidade em caso de evolução futura.

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS requirement_category VARCHAR(20) NULL;

COMMENT ON COLUMN module_candidates.requirement_category IS
    'MVP 19 Fase 19.1: classificação IEEE 830 do requisito. '
    'Valores canônicos: functional | non_functional | business_rule | NULL. '
    'NULL = não classificado pelo GP. Whitelist validada na aplicação.';

CREATE INDEX IF NOT EXISTS idx_module_candidates_requirement_category
    ON module_candidates (project_id, requirement_category)
    WHERE requirement_category IS NOT NULL;
