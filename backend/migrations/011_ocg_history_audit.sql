-- 011 — OCG Delta Log: autor, trigger, snapshot, document_id nullable
BEGIN;

-- Torna document_id opcional (updates sem doc passam a ser logados)
ALTER TABLE ocg_delta_log ALTER COLUMN document_id DROP NOT NULL;

-- Autor da mudança (NULL = update automático/sistema)
ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS changed_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- Origem da mudança: document_ingestion | manual_edit | pillar_agent | propagation | rollback | system
ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(50) NOT NULL DEFAULT 'document_ingestion';

-- Snapshot pós-mudança do OCG completo, usado para rollback
ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS ocg_snapshot TEXT;

CREATE INDEX IF NOT EXISTS idx_ocg_delta_trigger ON ocg_delta_log(project_id, trigger_source);
CREATE INDEX IF NOT EXISTS idx_ocg_delta_version ON ocg_delta_log(project_id, ocg_version_to);

COMMIT;
