-- Migration 073 — F4.2 Chunker estrutural: parent_document_id (sub-ingestões)
--
-- Permite que documentos > 256k chars sejam divididos em sub-IngestedDocuments.
-- Cada filho aponta para o pai via parent_document_id (FK self-referencial).
-- ON DELETE CASCADE: deletar o pai remove os filhos automaticamente (hard-delete).
-- Soft-delete do pai é propagado manualmente via revert_document_propagation
-- (CO-1: propagação de deleted_at para filhos na mesma transação).
--
-- Idempotência: ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS +
-- DROP COLUMN IF EXISTS + DROP INDEX IF EXISTS.
-- Rollback (DOWN) pode ser aplicado após UP sem erro. Reaplicar UP após
-- DOWN também funciona sem erro. Testado em schema vazio — DDL puro, < 2s.

BEGIN;

-- UP: adiciona coluna FK self-referencial e índice parcial ------------------

ALTER TABLE ingested_documents
  ADD COLUMN IF NOT EXISTS parent_document_id UUID
    REFERENCES ingested_documents(id) ON DELETE CASCADE;

-- Índice parcial: só filhos (parent_document_id IS NOT NULL) — evita overhead
-- em queries de listagem do pai. Consultas de filhos de um pai específico são
-- frequentes na resolução do callback (F4.2.4) e no watchdog (F4.2.5).
CREATE INDEX IF NOT EXISTS idx_ingested_docs_parent
  ON ingested_documents (parent_document_id)
  WHERE parent_document_id IS NOT NULL;

COMMIT;

-- DOWN: reverter (executar manualmente — fora de BEGIN/COMMIT pra ser explícito)
-- DROP INDEX IF EXISTS idx_ingested_docs_parent;
-- ALTER TABLE ingested_documents DROP COLUMN IF EXISTS parent_document_id;
