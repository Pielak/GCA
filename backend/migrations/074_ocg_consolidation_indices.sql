-- Migration: OCG consolidation performance indices
-- Issue: process_ingestion_complete_ocg task queries OCGIndividual + OCGGlobal without proper indices
-- Performance: -50-300ms per consolidation (queries scan full tables)

-- Index 1: OCGIndividual lookup by (project_id, document_id, status)
-- Query path: _run_process_ingestion_complete_ocg L590-600
--   SELECT * FROM ocg_individual
--   WHERE project_id=? AND document_id=? AND status != 'failed'
CREATE INDEX IF NOT EXISTS idx_ocg_individual_lookup
  ON ocg_individual(project_id, document_id, status)
  WHERE status != 'failed';

-- Index 2: OCGGlobal lookup by document_id
-- Query path: _run_process_ingestion_complete_ocg L603-608
--   SELECT * FROM ocg_global WHERE document_id=?
CREATE INDEX IF NOT EXISTS idx_ocg_global_by_document
  ON ocg_global(document_id);

-- Index 3: OCGIndividual by project_id (secondary, for project-wide queries)
-- Used in _load_persona_scores and aggregate persona scoring
CREATE INDEX IF NOT EXISTS idx_ocg_individual_by_project
  ON ocg_individual(project_id, persona_id, document_id);
