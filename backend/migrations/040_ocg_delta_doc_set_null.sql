-- Fix 2026-04-24: DELETE de ingested_documents falha com 500 quando há
-- ocg_delta_log referenciando o documento. FK original não declara
-- ON DELETE, então PG recusa pra preservar integridade.
--
-- Decisão: histórico de OCG é evidência de auditoria — não deve ser
-- apagado quando o doc-trigger é removido. Usar SET NULL preserva o
-- delta (version_from/to, change_summary) e marca document_id como null
-- (gerou "indefinido" se o doc sumiu).

ALTER TABLE ocg_delta_log
    DROP CONSTRAINT IF EXISTS ocg_delta_log_document_id_fkey;

ALTER TABLE ocg_delta_log
    ADD CONSTRAINT ocg_delta_log_document_id_fkey
    FOREIGN KEY (document_id)
    REFERENCES ingested_documents(id)
    ON DELETE SET NULL;
