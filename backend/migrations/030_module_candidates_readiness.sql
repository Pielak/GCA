-- MVP 9 Fase 9.3 — Orquestração premium: readiness_status + DAG.
-- ============================================================================
-- Após item virar `adicionado` (Fase 9.5.2), provider premium avalia se
-- tem informação suficiente pra entrar no escopo do CodeGen (MVP 3).
-- Resultado vai pra estas colunas; UI mostra chip + lista de gaps.
--
-- Política §6.2: avaliação é alta criticidade — Premium obrigatório.

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS readiness_status VARCHAR(30) NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS readiness_gaps TEXT NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS readiness_evaluated_at TIMESTAMPTZ NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS readiness_provider VARCHAR(50) NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS readiness_model VARCHAR(100) NULL;

ALTER TABLE module_candidates
    ADD COLUMN IF NOT EXISTS dependencies_inferred TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_module_candidates_readiness
    ON module_candidates (project_id, readiness_status)
    WHERE readiness_status IS NOT NULL;

COMMENT ON COLUMN module_candidates.readiness_status IS
    'MVP 9 Fase 9.3: avaliação Premium do estado do item. Valores: '
    'ready_for_codegen | partial | needs_input | unknown. NULL = nunca avaliado.';

COMMENT ON COLUMN module_candidates.readiness_gaps IS
    'JSON list de strings curtas (até 8 itens) descrevendo o que ainda '
    'falta saber pro CodeGen iniciar. Vazio quando readiness_status=ready_for_codegen.';

COMMENT ON COLUMN module_candidates.dependencies_inferred IS
    'JSON list de UUIDs ou names de outros módulos que este depende. '
    'Inferido pelo Premium a partir do contexto. Separado de `dependencies` '
    'que pode ter origem manual.';
