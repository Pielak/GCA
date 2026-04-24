-- Migration 041: corrige FKs sem ON DELETE explícito identificadas pela auditoria DBA.
-- Sem essas correções, DELETE de arguider_analyses/usuário/documento quebra 500 em prod
-- (mesmo cenário do DT-096 resolvido parcialmente na migration 040).

-- 1. gatekeeper_items.arguider_analysis_id NOT NULL — CASCADE (gatekeeper é derivado da análise).
ALTER TABLE gatekeeper_items
  DROP CONSTRAINT IF EXISTS gatekeeper_items_arguider_analysis_id_fkey,
  ADD CONSTRAINT gatekeeper_items_arguider_analysis_id_fkey
    FOREIGN KEY (arguider_analysis_id)
    REFERENCES arguider_analyses(id)
    ON DELETE CASCADE;

-- 2. project_invites.invited_by_user_id / accepted_by_user_id — SET NULL
--    (histórico de convite sobrevive ao usuário removido).
ALTER TABLE project_invites
  DROP CONSTRAINT IF EXISTS project_invites_invited_by_user_id_fkey,
  ADD CONSTRAINT project_invites_invited_by_user_id_fkey
    FOREIGN KEY (invited_by_user_id) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE project_invites
  DROP CONSTRAINT IF EXISTS project_invites_accepted_by_user_id_fkey,
  ADD CONSTRAINT project_invites_accepted_by_user_id_fkey
    FOREIGN KEY (accepted_by_user_id) REFERENCES users(id) ON DELETE SET NULL;

-- 3. backlog_items.parent_item_id auto-ref — SET NULL
--    (delete de item-pai não apaga filhos, só desvincula).
ALTER TABLE backlog_items
  DROP CONSTRAINT IF EXISTS backlog_items_parent_item_id_fkey,
  ADD CONSTRAINT backlog_items_parent_item_id_fkey
    FOREIGN KEY (parent_item_id) REFERENCES backlog_items(id) ON DELETE SET NULL;

-- 4. ingested_documents.uploaded_by — SET NULL.
ALTER TABLE ingested_documents
  DROP CONSTRAINT IF EXISTS ingested_documents_uploaded_by_fkey,
  ADD CONSTRAINT ingested_documents_uploaded_by_fkey
    FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL;

-- 5. arguider_analyses.project_id — FK explícita (hoje é nullable=False SEM FK).
--    Qualquer project_id inválido passa pelo banco, só pega no ORM — risco de órfão silencioso.
--    Adicionar constraint idempotente.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_name = 'arguider_analyses'
      AND constraint_type = 'FOREIGN KEY'
      AND constraint_name = 'arguider_analyses_project_id_fkey'
  ) THEN
    ALTER TABLE arguider_analyses
      ADD CONSTRAINT arguider_analyses_project_id_fkey
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
  END IF;
END $$;

-- 6. module_candidates.arguider_analysis_id — CASCADE (idem gatekeeper_items).
ALTER TABLE module_candidates
  DROP CONSTRAINT IF EXISTS module_candidates_arguider_analysis_id_fkey,
  ADD CONSTRAINT module_candidates_arguider_analysis_id_fkey
    FOREIGN KEY (arguider_analysis_id)
    REFERENCES arguider_analyses(id)
    ON DELETE CASCADE;
