-- Cascata canônica Backlog→Roadmap→Scaffold (2026-04-24).
-- Antes desta migration o BacklogItem perdia o vínculo com o ModuleCandidate
-- de origem ao ser criado por ingest_module_candidates — o roadmap precisava
-- ler do silo paralelo (module_candidates) pra exibir ready_for_codegen e
-- readiness_status. Agora há FK explícita: backlog é a fonte canônica e
-- enriquece via JOIN quando precisa de campos do candidato (readiness etc).
-- ON DELETE SET NULL: se um candidato for descartado, o item de backlog
-- continua existindo (perde só o enriquecimento).

ALTER TABLE backlog_items
    ADD COLUMN module_candidate_id UUID REFERENCES module_candidates(id) ON DELETE SET NULL;

CREATE INDEX ix_backlog_items_module_candidate
    ON backlog_items (module_candidate_id)
    WHERE module_candidate_id IS NOT NULL;

-- Backfill retroativo: itens que vieram do Arguidor casam por título com
-- module_candidates.name dentro do mesmo projeto. Itens duplicados (raros,
-- já que ingest_module_candidates filtra por título) ficam com o primeiro
-- match — é determinístico graças ao ORDER BY created_at ASC.
UPDATE backlog_items b
SET module_candidate_id = mc.id
FROM (
    SELECT DISTINCT ON (project_id, name)
        id, project_id, name
    FROM module_candidates
    ORDER BY project_id, name, created_at ASC
) mc
WHERE b.source = 'arguider'
  AND b.project_id = mc.project_id
  AND b.title = mc.name
  AND b.module_candidate_id IS NULL;

COMMENT ON COLUMN backlog_items.module_candidate_id IS
    'FK pro ModuleCandidate de origem (quando source=arguider). Usado pelo Roadmap e Scaffold pra ler ready_for_codegen, readiness_status, pillar_impact.';
