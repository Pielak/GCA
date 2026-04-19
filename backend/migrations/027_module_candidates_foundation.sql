-- MVP 9 Fase 9.1.1 — Foundation generator (Fase 1 do Roadmap nasce do OCG)
-- ============================================================================
-- A Fase 1 — Fundação do Roadmap precisa existir antes da primeira ingestão.
-- Itens são derivados do OCG (questionário aprovado) — não dependem de
-- ArguiderAnalysis. Hoje a FK arguider_analysis_id é NOT NULL, bloqueando.
--
-- Mudanças:
--   1. arguider_analysis_id vira NULLABLE (foundation modules não têm análise)
--   2. nova coluna `source` distingue origem: 'arguider' vs 'ocg_foundation'
--   3. index parcial em source='ocg_foundation' acelera idempotência
--      (RoadmapFoundationService consulta "tem foundation pra esse projeto?")
--
-- Compatibilidade: rows antigas mantém arguider_analysis_id (NOT NULL antes,
-- continuam preenchidas) e ganham source='arguider' default.

ALTER TABLE module_candidates
    ALTER COLUMN arguider_analysis_id DROP NOT NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS source VARCHAR(30) NOT NULL DEFAULT 'arguider';

-- Backfill explícito pras rows existentes (idempotente — DEFAULT já cobre,
-- mas garantimos pra deixar legado claro no audit)
UPDATE module_candidates
   SET source = 'arguider'
 WHERE source IS NULL OR source = '';

CREATE INDEX IF NOT EXISTS idx_module_candidates_foundation
    ON module_candidates (project_id)
    WHERE source = 'ocg_foundation';

CREATE INDEX IF NOT EXISTS idx_module_candidates_source
    ON module_candidates (project_id, source);

COMMENT ON COLUMN module_candidates.source IS
    'Origem do item: arguider (gerado por análise de doc) ou ocg_foundation '
    '(gerado pelo Foundation generator a partir do OCG, MVP 9 Fase 9.1.1).';

COMMENT ON COLUMN module_candidates.arguider_analysis_id IS
    'NULL quando source=ocg_foundation (item nasceu do OCG sem ingestão). '
    'Preenchido para source=arguider.';
